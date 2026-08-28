"""query_bank / query_settlement / query_ledger — read-only lookups the
investigator and verifier call to pull related rows for a given break.
Kept as plain deterministic queries; never LLM-interpreted."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sbe.engine.tools.normalise_identifier import identifiers_compatible, normalise
from sbe.generator.seed import SEEDS_ROOT
from sbe.money import money


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _in_range(d: date, date_range: tuple) -> bool:
    start, end = date_range
    return _as_date(start) <= d <= _as_date(end)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass
class SourceStore:
    """In-memory index of seed CSVs for query_* tools (sources are not in SQLite)."""

    seed: str
    bank: list[dict] = field(default_factory=list)
    settlement: list[dict] = field(default_factory=list)
    ledger: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, seed: str, seeds_root: Path | None = None) -> SourceStore:
        root = seeds_root or SEEDS_ROOT
        seed_dir = root / seed
        store = cls(seed=seed)
        if not seed_dir.exists():
            return store

        for day_dir in sorted(seed_dir.glob("day_*")):
            if not day_dir.is_dir():
                continue
            day_tag = day_dir.name
            for row in _read_csv(day_dir / "bank_statement.csv"):
                tagged = dict(row)
                tagged["_source"] = "bank_statement"
                tagged["_day"] = day_tag
                store.bank.append(tagged)
            for row in _read_csv(day_dir / "settlement_report.csv"):
                tagged = dict(row)
                tagged["_source"] = "settlement_report"
                tagged["_day"] = day_tag
                store.settlement.append(tagged)
            for row in _read_csv(day_dir / "merchant_ledger.csv"):
                tagged = dict(row)
                tagged["_source"] = "merchant_ledger"
                tagged["_day"] = day_tag
                store.ledger.append(tagged)

        store._enrich_bank_merchants()
        store._enrich_ledger_merchants()
        return store

    def _enrich_bank_merchants(self) -> None:
        """Attach merchant_id to bank rows via UTR / truncated-narration join."""
        by_utr: dict[str, str] = {}
        for s in self.settlement:
            key = normalise(str(s.get("utr") or ""))
            if key:
                by_utr[key] = s["merchant_id"]
        for b in self.bank:
            if b.get("merchant_id"):
                continue
            narr = str(b.get("narration") or "")
            key = normalise(narr)
            mid = by_utr.get(key)
            if mid:
                b["merchant_id"] = mid
                continue
            for utr, merchant in by_utr.items():
                if identifiers_compatible(narr, utr):
                    b["merchant_id"] = merchant
                    break
            # Amount fallback against settlement nets on same posting date
            if not b.get("merchant_id") and b.get("credit"):
                credit = money(b["credit"])
                post = b.get("posting_date") or b.get("value_date")
                for s in self.settlement:
                    if money(s.get("net_amount") or 0) != credit:
                        continue
                    if post and s.get("settled_at") and str(s["settled_at"])[:10] != str(post)[:10]:
                        continue
                    b["merchant_id"] = s["merchant_id"]
                    break

    def _enrich_ledger_merchants(self) -> None:
        """Stamp merchant_id onto ledger rows when the CSV lacks the column.

        Match sale/fee amounts to settlement gross/fee/fee_gst/tds for the
        same calendar day — good enough for seed data density.
        """
        # Build amount → merchants per date from settlements
        by_date_amt: dict[tuple[str, str], set[str]] = {}
        for s in self.settlement:
            d = str(s.get("settled_at") or "")[:10]
            mid = s["merchant_id"]
            for field in ("gross_amount", "fee", "fee_gst", "tds", "net_amount", "reserve_hold", "reserve_release"):
                val = s.get(field)
                if val in (None, "", "0.00"):
                    continue
                key = (d, f"{money(val):.2f}")
                by_date_amt.setdefault(key, set()).add(mid)

        for row in self.ledger:
            if row.get("merchant_id"):
                continue
            d = str(row.get("entry_date") or "")[:10]
            amt = f"{money(row.get('amount') or 0):.2f}"
            merchants = by_date_amt.get((d, amt)) or set()
            if len(merchants) == 1:
                row["merchant_id"] = next(iter(merchants))


def query_settlement(merchant_id: str, date_range: tuple, sources: Any) -> list[dict]:
    store = _as_store(sources)
    out = []
    for row in store.settlement:
        if row.get("merchant_id") != merchant_id:
            continue
        if not _in_range(_as_date(row["settled_at"]), date_range):
            continue
        out.append(dict(row))
    return out


def query_bank(merchant_id: str, date_range: tuple, sources: Any) -> list[dict]:
    store = _as_store(sources)
    # Ensure enrichment ran
    if store.bank and not any(b.get("merchant_id") for b in store.bank[:5]):
        store._enrich_bank_merchants()

    out = []
    for row in store.bank:
        d = _as_date(row.get("posting_date") or row.get("value_date"))
        if not _in_range(d, date_range):
            continue
        if row.get("merchant_id") and row["merchant_id"] != merchant_id:
            continue
        if not row.get("merchant_id"):
            # Include unmatched-in-range rows only when merchant filter is wildcard
            if merchant_id not in {"*", "ANY", ""}:
                continue
        out.append(dict(row))
    return out


def query_ledger(merchant_id: str, date_range: tuple, sources: Any) -> list[dict]:
    store = _as_store(sources)
    if store.ledger and not any(r.get("merchant_id") for r in store.ledger[:5]):
        store._enrich_ledger_merchants()

    out = []
    for row in store.ledger:
        if not _in_range(_as_date(row["entry_date"]), date_range):
            continue
        if row.get("merchant_id") and row["merchant_id"] != merchant_id:
            continue
        if not row.get("merchant_id") and merchant_id not in {"*", "ANY", ""}:
            continue
        out.append(dict(row))
    return out


def _as_store(sources: Any) -> SourceStore:
    if isinstance(sources, SourceStore):
        return sources
    # Back-compat: some call sites may still pass a sqlite connection — ignore
    # and require an attached store attribute.
    store = getattr(sources, "source_store", None)
    if isinstance(store, SourceStore):
        return store
    raise TypeError(
        "query_* tools require a SourceStore (seed CSVs); pass SourceStore.load(seed)"
    )
