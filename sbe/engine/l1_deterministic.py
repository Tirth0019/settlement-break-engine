"""
L1 — deterministic pass (BUILD_PLAN Phase 3, GATE 3).

Exact hash-join on canonical identifier across the three sources, then
materiality write-off for anything below sbe.money.MATERIALITY_PER_BREAK,
capped at MATERIALITY_DAILY_CAP aggregate.

Target: clears 60-75% of records. If this is tuned to hit that band rather
than landing there naturally, something is wrong with the seed or the join
key — do not force it (ROADMAP.md Day 4).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sbe.engine.tools.normalise_identifier import normalise
from sbe.money import MATERIALITY_DAILY_CAP, MATERIALITY_PER_BREAK, ZERO, money


def hash_join_key(record: dict) -> str:
    """Canonical identifier used for the exact match.

    Precedence: explicit utr / match_key / settlement_id → narration extract →
    bank_ref → payment_id.
    """
    for field in ("utr", "match_key", "canonical_id", "settlement_id"):
        val = record.get(field)
        if val:
            key = normalise(str(val), record.get("_source", ""))
            if key:
                return key

    narration = record.get("narration") or record.get("description") or ""
    if narration:
        key = normalise(str(narration), record.get("_source", "bank_statement"))
        if key.startswith("UTR") or key.startswith("RRN"):
            return key

    for field in ("bank_ref", "payment_id", "order_id"):
        val = record.get(field)
        if val:
            key = normalise(str(val), record.get("_source", ""))
            if key:
                return key
    return ""


def _row_amount(record: dict) -> Decimal:
    """Signed bank-oriented amount: credit positive, debit negative; else amount/net."""
    if record.get("credit"):
        return money(record["credit"])
    if record.get("debit"):
        return money(-money(record["debit"]))
    if record.get("net_amount") not in (None, ""):
        return money(record["net_amount"])
    if record.get("amount") not in (None, ""):
        # Ledger: sales positive contribution already handled by caller for nets;
        # for join we treat raw amount as positive magnitude on sales.
        return money(record["amount"])
    return ZERO


def _index_by_key(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = hash_join_key(row)
        if key:
            out[key].append(row)
    return out


def run(records: list) -> dict:
    """Exact hash-join + materiality write-off.

    ``records`` is a flat list of source rows, each tagged with ``_source`` in
    {bank_statement, settlement_report, merchant_ledger}.

    Returns {"matched": [...], "residual": [...], "written_off": [...],
             "clear_rate": float, "stats": {...}}.
    """
    bank = [r for r in records if r.get("_source") == "bank_statement"]
    sett = [r for r in records if r.get("_source") == "settlement_report"]
    ledg = [r for r in records if r.get("_source") == "merchant_ledger"]

    bank_ix = _index_by_key(bank)
    sett_ix = _index_by_key(sett)
    ledg_ix = _index_by_key(ledg)

    matched: list[dict[str, Any]] = []
    residual: list[dict[str, Any]] = []
    used_bank: set[int] = set()
    used_sett: set[int] = set()

    # Prefer settlement∩bank exact amount join (CLEAN path).
    for key, sett_rows in sett_ix.items():
        bank_rows = bank_ix.get(key) or []
        for srow in sett_rows:
            s_amt = money(srow.get("net_amount") or ZERO)
            partner = None
            for brow in bank_rows:
                if id(brow) in used_bank:
                    continue
                if money(_row_amount(brow)) == s_amt:
                    partner = brow
                    break
            if partner is None:
                continue
            used_bank.add(id(partner))
            used_sett.add(id(srow))
            matched.append(
                {
                    "join_key": key,
                    "settlement": srow,
                    "bank": partner,
                    "ledger": (ledg_ix.get(key) or [None])[0],
                    "amount": f"{s_amt:.2f}",
                }
            )

    # Unmatched settlement → residual (bank short of expected net)
    for srow in sett:
        if id(srow) in used_sett:
            continue
        key = hash_join_key(srow)
        net = money(srow.get("net_amount") or ZERO)
        residual.append(
            {
                "join_key": key,
                "side": "SETTLEMENT_ONLY",
                "merchant_id": srow.get("merchant_id") or "UNKNOWN",
                "amount_delta": f"{money(-net):.2f}",
                "match_key": key or None,
                "settlement": srow,
                "bank": None,
                "ledger": None,
            }
        )

    # Unmatched bank → residual
    for brow in bank:
        if id(brow) in used_bank:
            continue
        key = hash_join_key(brow)
        amt = _row_amount(brow)
        merchant = brow.get("merchant_id") or "UNKNOWN"
        if merchant == "UNKNOWN" and key and sett_ix.get(key):
            merchant = sett_ix[key][0].get("merchant_id") or merchant
        residual.append(
            {
                "join_key": key,
                "side": "BANK_ONLY",
                "merchant_id": merchant,
                "amount_delta": f"{amt:.2f}",
                "match_key": key or None,
                "settlement": None,
                "bank": brow,
                "ledger": None,
            }
        )

    # Materiality write-off on residuals
    written_off: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    aggregate = ZERO
    for item in residual:
        delta = money(item["amount_delta"])
        abs_delta = abs(delta)
        if abs_delta > ZERO and abs_delta < MATERIALITY_PER_BREAK:
            if aggregate + abs_delta <= MATERIALITY_DAILY_CAP:
                aggregate += abs_delta
                item = dict(item)
                item["write_off_reason"] = "materiality"
                written_off.append(item)
                continue
        kept.append(item)

    total_units = len(matched) + len(kept) + len(written_off)
    clear_rate = (len(matched) + len(written_off)) / total_units if total_units else 0.0

    return {
        "matched": matched,
        "residual": kept,
        "written_off": written_off,
        "clear_rate": clear_rate,
        "stats": {
            "matched": len(matched),
            "residual": len(kept),
            "written_off": len(written_off),
            "materiality_aggregate": f"{aggregate:.2f}",
            "bank_rows": len(bank),
            "settlement_rows": len(sett),
            "ledger_rows": len(ledg),
        },
    }
