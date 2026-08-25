"""
Day pipeline: load seed CSVs → L1 → L2 ledger → L5 roll-forward.

Used by `sbe run` and GATE 4 tests. Agents (L3/L4) are not invoked here.
"""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sbe.engine.l1_deterministic import hash_join_key
from sbe.engine.l1_deterministic import run as l1_run
from sbe.engine.l2_break_ledger import (
    ingest_day_breaks,
    open_break,
    write_off_break,
)
from sbe.engine.l5_rollforward import check_and_certify
from sbe.generator.seed import SEEDS_ROOT
from sbe.money import ZERO, money


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_day_records(seed: str, day: int) -> list[dict]:
    day_dir = SEEDS_ROOT / seed / f"day_{day:02d}"
    records: list[dict] = []
    for name, source in (
        ("bank_statement.csv", "bank_statement"),
        ("settlement_report.csv", "settlement_report"),
        ("merchant_ledger.csv", "merchant_ledger"),
    ):
        for row in _read_csv(day_dir / name):
            tagged = dict(row)
            tagged["_source"] = source
            records.append(tagged)
    return records


def load_day_ground_truth(seed: str, day: int) -> list[dict]:
    path = SEEDS_ROOT / seed / f"day_{day:02d}" / "ground_truth.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _seed_start_date(seed: str) -> date:
    manifest = SEEDS_ROOT / seed / "manifest.json"
    if manifest.exists():
        return date.fromisoformat(json.loads(manifest.read_text(encoding="utf-8"))["start_date"])
    return date(2026, 3, 10)


def _settlement_by_key(records: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in records:
        if row.get("_source") != "settlement_report":
            continue
        key = hash_join_key(row)
        if key:
            out[key] = row
    return out


def _merchant_from_open_breaks(conn, seed: str, match_key: str | None) -> str | None:
    if not match_key:
        return None
    row = conn.execute(
        """
        SELECT merchant_id FROM breaks
         WHERE seed = ? AND status = 'OPEN' AND match_key = ?
         ORDER BY first_seen_run ASC, break_id ASC
         LIMIT 1
        """,
        (seed, match_key),
    ).fetchone()
    return row[0] if row else None


def _build_late_arrivals(conn, *, seed: str, records: list[dict]) -> list[dict]:
    """Bank credits that may close prior OPEN breaks. Enrich merchant_id —
    bank CSVs have no merchant column, so join via UTR to settlement or open breaks.
    """
    sett_ix = _settlement_by_key(records)
    late: list[dict] = []
    for row in records:
        if row.get("_source") != "bank_statement" or not row.get("credit"):
            continue
        key = hash_join_key(row) or None
        merchant = row.get("merchant_id") or None
        if not merchant or merchant == "UNKNOWN":
            if key and key in sett_ix:
                merchant = sett_ix[key].get("merchant_id")
            if not merchant or merchant == "UNKNOWN":
                merchant = _merchant_from_open_breaks(conn, seed, key)
        late.append(
            {
                "seed": seed,
                "merchant_id": merchant or "UNKNOWN",
                "amount": money(row["credit"]),
                "match_key": key,
            }
        )
    return late


def _reserve_hold_break_specs(l1_result: dict) -> list[dict]:
    """Rolling-reserve holds clear L1 bank↔settlement (nets already reduced) but
    still leave a MULTI_DAY gap vs ledger. Open an explicit hold break so the
    later reserve_release credit can late-arrival-close it.
    """
    specs: list[dict] = []
    for item in l1_result.get("matched") or []:
        srow = item.get("settlement") or {}
        hold = money(srow.get("reserve_hold") or ZERO)
        if hold <= ZERO:
            continue
        key = item.get("join_key") or hash_join_key(srow)
        specs.append(
            {
                "merchant_id": srow.get("merchant_id") or "UNKNOWN",
                "side": "AMOUNT_MISMATCH",
                "amount_delta": money(-hold),
                "match_key": key or None,
                "ground_truth_archetype": "ROLLING_RESERVE_HOLD",
            }
        )
    return specs


def run_day(conn, *, seed: str, day: int) -> dict[str, Any]:
    """L1 + L2 + L5 for one simulated day. Returns certificate + L1 stats."""
    start = _seed_start_date(seed)
    run_date = start + timedelta(days=day - 1)
    records = load_day_records(seed, day)
    l1 = l1_run(records)

    late_arrivals = _build_late_arrivals(conn, seed=seed, records=records)

    break_specs: list[dict] = []
    for item in l1["residual"]:
        merchant = item.get("merchant_id") or "UNKNOWN"
        if merchant == "UNKNOWN" and item.get("settlement"):
            merchant = item["settlement"].get("merchant_id") or merchant
        break_specs.append(
            {
                "merchant_id": merchant,
                "side": item["side"],
                "amount_delta": money(item["amount_delta"]),
                "match_key": item.get("match_key"),
                "ground_truth_archetype": None,
            }
        )
    break_specs.extend(_reserve_hold_break_specs(l1))

    ingest = ingest_day_breaks(
        conn,
        seed=seed,
        run_date=run_date,
        break_specs=break_specs,
        late_arrivals=late_arrivals,
    )

    for item in l1["written_off"]:
        merchant = item.get("merchant_id") or "UNKNOWN"
        if merchant == "UNKNOWN" and item.get("settlement"):
            merchant = item["settlement"].get("merchant_id") or merchant
        bid = open_break(
            conn,
            merchant_id=merchant,
            side=item["side"],
            amount_delta=money(item["amount_delta"]),
            run_date=run_date,
            seed=seed,
            match_key=item.get("match_key"),
            ground_truth_archetype="MATERIALITY",
        )
        write_off_break(conn, bid, run_date, reason="materiality")

    certificate = check_and_certify(conn, run_date, seed=seed)
    return {
        "day": day,
        "run_date": run_date.isoformat(),
        "l1": l1["stats"],
        "clear_rate": l1["clear_rate"],
        "opened": ingest["opened"],
        "closed": ingest["closed"],
        "certificate": certificate,
    }


def run_seed(conn, *, seed: str, days: int | None = None) -> list[dict]:
    manifest = SEEDS_ROOT / seed / "manifest.json"
    if not manifest.exists():
        raise FileNotFoundError(f"seed {seed} missing — run sbe generate --seed {seed}")
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    n_days = days or int(meta.get("days", 10))
    results = []
    for day in range(1, n_days + 1):
        results.append(run_day(conn, seed=seed, day=day))
    return results
