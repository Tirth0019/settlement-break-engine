"""
Multi-day seed writer (ROADMAP Day 1-2).

Layout:
  sbe/generator/seeds/<seed>/
    manifest.json
    day_01/
      bank_statement.csv
      settlement_report.csv
      merchant_ledger.csv
      ground_truth.jsonl
    day_02/ ...
"""
from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from sbe.config import RECORD_COUNT
from sbe.engine.tools.banking_calendar import load_calendar
from sbe.engine.tools.fee_recompute import load_fee_schedule
from sbe.generator.archetypes.registry import (
    ARCHETYPE_WEIGHTS,
    DENSE_ARCHETYPE_WEIGHTS,
    HOLDOUT_ARCHETYPE_WEIGHTS,
)
from sbe.generator.validate_seed import validate_seed
from sbe.money import money

SEEDS_ROOT = Path(__file__).resolve().parent / "seeds"

MERCHANT_STATES = {
    f"MERCH_{i:04d}": ("Gujarat" if i % 3 == 0 else "Maharashtra")
    for i in range(1, 31)
}

BANK_FIELDS = [
    "value_date",
    "posting_date",
    "narration",
    "debit",
    "credit",
    "closing_balance",
    "bank_ref",
]
SETTLEMENT_FIELDS = [
    "settlement_id",
    "utr",
    "merchant_id",
    "settled_at",
    "settlement_type",
    "gross_amount",
    "fee",
    "fee_gst",
    "tds",
    "adjustments",
    "reserve_hold",
    "reserve_release",
    "net_amount",
    "txn_count",
]
LEDGER_FIELDS = [
    "entry_id",
    "order_id",
    "payment_id",
    "entry_date",
    "entry_type",
    "amount",
    "currency",
    "status",
    "description",
]


def _pick_weighted(rng: random.Random):
    names, fns, weights = zip(*ARCHETYPE_WEIGHTS)
    return rng.choices(list(zip(names, fns)), weights=weights, k=1)[0]


def _shift_dates(rows: list[dict], date_fields: list[str], new_date: date) -> list[dict]:
    out = []
    for row in rows:
        r = dict(row)
        for f in date_fields:
            if f in r and r[f]:
                r[f] = new_date.isoformat()
        out.append(r)
    return out


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _serialize_gt(gt: dict) -> dict:
    out = {}
    for k, v in gt.items():
        if hasattr(v, "quantize"):
            out[k] = f"{money(v):.2f}"
        else:
            out[k] = v
    return out


def generate_seed(
    seed: str,
    days: int = 10,
    start_date: date | None = None,
    *,
    dense: bool = False,
    holdout: bool = False,
    record_count: int | None = None,
    target_breaks: int | None = None,
) -> Path:
    seed_int = int(seed)
    rng = random.Random(seed_int)
    fee_schedule = load_fee_schedule()
    calendar = load_calendar()

    if start_date is None:
        # Mid-March 2026 window — includes Gujarat Dhuleti contrast nearby
        start_date = date(2026, 3, 10)

    holdout = holdout or seed == "9999"
    if record_count is not None:
        target_records = record_count
    elif target_breaks is not None:
        # Hold-out 9999: ~70% of records become labelled OPEN (seed 9999 first pass).
        target_records = max(days, int(round(target_breaks / 0.70)))
    elif holdout:
        target_records = 86
    elif dense:
        target_records = 280
    else:
        target_records = RECORD_COUNT
    if holdout:
        weights = HOLDOUT_ARCHETYPE_WEIGHTS
    elif dense:
        weights = DENSE_ARCHETYPE_WEIGHTS
    else:
        weights = ARCHETYPE_WEIGHTS

    def _pick_weighted_local():
        names, fns, wts = zip(*weights)
        return rng.choices(list(zip(names, fns)), weights=wts, k=1)[0]

    per_day = max(1, target_records // days)
    # Pad last day so total ~= target_records
    totals = [per_day] * days
    totals[-1] += target_records - sum(totals)

    day_buckets: dict[int, dict] = {
        i: {
            "bank_statement": [],
            "settlement_report": [],
            "merchant_ledger": [],
            "ground_truth": [],
        }
        for i in range(1, days + 1)
    }

    all_results = []
    label_counts: Counter = Counter()
    multi_day_manifest = []

    merchants = list(MERCHANT_STATES.keys())

    for day_idx in range(1, days + 1):
        run_date = start_date + timedelta(days=day_idx - 1)
        for _ in range(totals[day_idx - 1]):
            merchant = rng.choice(merchants)
            state = MERCHANT_STATES[merchant]
            cal = dict(calendar)
            cal["_merchant_state"] = state

            # Don't schedule MULTI_DAY opens too late to close inside the seed
            name, gen_fn = _pick_weighted_local()
            if name in {"ROLLING_RESERVE_HOLD", "T2_PERIOD_BOUNDARY"} and day_idx > days - 4:
                name, gen_fn = "CLEAN", weights[0][1]

            result = gen_fn(rng, merchant, run_date, fee_schedule, cal)
            all_results.append(result)

            gt = dict(result.ground_truth)
            gt["seed"] = seed
            gt["merchant_id"] = merchant
            gt["merchant_state"] = state
            gt["open_day"] = day_idx
            gt["open_date"] = run_date.isoformat()
            for srow in result.rows.get("settlement_report") or []:
                if srow.get("utr"):
                    gt["utr"] = srow["utr"]
                    break
            if gt.get("shared_utr") and not gt.get("utr"):
                gt["utr"] = gt["shared_utr"]
            label = gt.get("archetype", name)
            label_counts[label] += 1

            # Primary day rows
            day_buckets[day_idx]["bank_statement"].extend(result.rows.get("bank_statement") or [])
            day_buckets[day_idx]["settlement_report"].extend(result.rows.get("settlement_report") or [])
            day_buckets[day_idx]["merchant_ledger"].extend(result.rows.get("merchant_ledger") or [])

            close_offset = int(gt.get("closes_on_offset") or 0)
            if gt.get("lifecycle") == "MULTI_DAY" and close_offset:
                close_day = day_idx + close_offset
                if close_day <= days:
                    gt["close_day"] = close_day
                    gt["close_date"] = (run_date + timedelta(days=close_offset)).isoformat()
                    multi_day_manifest.append(
                        {
                            "archetype": label,
                            "merchant_id": merchant,
                            "open_day": day_idx,
                            "close_day": close_day,
                            "closes_on_offset": close_offset,
                        }
                    )
                    for fu in result.rows.get("follow_ups") or []:
                        fu_day = day_idx + int(fu["day_offset"])
                        if fu_day > days:
                            continue
                        fu_date = start_date + timedelta(days=fu_day - 1)
                        day_buckets[fu_day]["bank_statement"].extend(
                            _shift_dates(fu.get("bank_statement") or [], ["value_date", "posting_date"], fu_date)
                        )
                        day_buckets[fu_day]["settlement_report"].extend(
                            _shift_dates(fu.get("settlement_report") or [], ["settled_at"], fu_date)
                        )
                        day_buckets[fu_day]["merchant_ledger"].extend(
                            _shift_dates(fu.get("merchant_ledger") or [], ["entry_date"], fu_date)
                        )
                else:
                    gt["close_day"] = None
                    gt["truncated_follow_up"] = True

            day_buckets[day_idx]["ground_truth"].append(_serialize_gt(gt))

    validate_seed(all_results)

    out_root = SEEDS_ROOT / seed
    if out_root.exists():
        # Wipe prior generation for idempotent regenerate
        import shutil

        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    for day_idx, bucket in day_buckets.items():
        day_dir = out_root / f"day_{day_idx:02d}"
        _write_csv(day_dir / "bank_statement.csv", BANK_FIELDS, bucket["bank_statement"])
        _write_csv(day_dir / "settlement_report.csv", SETTLEMENT_FIELDS, bucket["settlement_report"])
        _write_csv(day_dir / "merchant_ledger.csv", LEDGER_FIELDS, bucket["merchant_ledger"])
        with (day_dir / "ground_truth.jsonl").open("w", encoding="utf-8") as f:
            for gt in bucket["ground_truth"]:
                f.write(json.dumps(gt) + "\n")

    manifest = {
        "seed": seed,
        "days": days,
        "start_date": start_date.isoformat(),
        "dense": dense,
        "holdout": holdout,
        "target_breaks": target_breaks,
        "record_count_target": target_records,
        "records_generated": sum(totals),
        "merchants": len(merchants),
        "label_counts": dict(sorted(label_counts.items())),
        "multi_day": multi_day_manifest,
    }
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_root


def load_seed_results_for_validate(seed: str):
    """Re-generate in-memory (deterministic) matching the written seed's manifest."""
    manifest_path = SEEDS_ROOT / seed / "manifest.json"
    dense = False
    holdout = seed == "9999"
    record_count = RECORD_COUNT
    days = 10
    start_date = date(2026, 3, 10)
    if manifest_path.exists():
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        dense = bool(meta.get("dense"))
        holdout = bool(meta.get("holdout") or seed == "9999")
        record_count = int(meta.get("record_count_target") or RECORD_COUNT)
        days = int(meta.get("days") or 10)
        if meta.get("start_date"):
            start_date = date.fromisoformat(str(meta["start_date"])[:10])

    seed_int = int(seed)
    rng = random.Random(seed_int)
    fee_schedule = load_fee_schedule()
    calendar = load_calendar()
    if holdout:
        weights = HOLDOUT_ARCHETYPE_WEIGHTS
    elif dense:
        weights = DENSE_ARCHETYPE_WEIGHTS
    else:
        weights = ARCHETYPE_WEIGHTS

    def _pick_weighted_local():
        names, fns, wts = zip(*weights)
        return rng.choices(list(zip(names, fns)), weights=wts, k=1)[0]

    per_day = max(1, record_count // days)
    totals = [per_day] * days
    totals[-1] += record_count - sum(totals)
    merchants = list(MERCHANT_STATES.keys())
    results = []
    for day_idx in range(1, days + 1):
        run_date = start_date + timedelta(days=day_idx - 1)
        for _ in range(totals[day_idx - 1]):
            merchant = rng.choice(merchants)
            state = MERCHANT_STATES[merchant]
            cal = dict(calendar)
            cal["_merchant_state"] = state
            name, gen_fn = _pick_weighted_local()
            if name in {"ROLLING_RESERVE_HOLD", "T2_PERIOD_BOUNDARY"} and day_idx > days - 4:
                name, gen_fn = "CLEAN", weights[0][1]
            results.append(gen_fn(rng, merchant, run_date, fee_schedule, cal))
    return results
