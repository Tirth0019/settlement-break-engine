"""
L1 — deterministic pass (BUILD_PLAN Phase 3, GATE 3).

Three-way join: exact (or truncation-compatible) key match across bank,
settlement, and merchant ledger; reconcile bank↔settlement amount deltas
through fee_recompute before opening a break; emit AMOUNT_MISMATCH when
ledger net ≠ bank credit for the same txn.

Target: clears 60-75% of records. If this is tuned to hit that band rather
than landing there naturally, something is wrong with the seed or the join
key — do not force it (ROADMAP.md Day 4).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sbe.engine.tools.fee_recompute import (
    load_fee_schedule,
    recompute_fee,
    recompute_gst_on_fee,
    recompute_instant_settlement_fee,
)
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
        return money(record["amount"])
    return ZERO


def _ledger_net(rows: list[dict]) -> Decimal:
    total = ZERO
    for row in rows:
        amount = money(row["amount"])
        entry_type = row.get("entry_type") or ""
        if entry_type in {"sale", "adjustment"}:
            total += amount
        elif entry_type in {"refund", "chargeback", "fee"}:
            total -= amount
        else:
            total += amount
    return money(total)


def _settlement_net_components(
    gross: Decimal,
    fee: Decimal,
    fee_gst: Decimal,
    tds: Decimal,
    *,
    adjustments: Decimal = ZERO,
    reserve_hold: Decimal = ZERO,
    reserve_release: Decimal = ZERO,
) -> Decimal:
    return money(
        money(gross)
        - money(fee)
        - money(fee_gst)
        - money(tds)
        + money(adjustments)
        - money(reserve_hold)
        + money(reserve_release)
    )


def _payment_method(srow: dict) -> str:
    stype = (srow.get("settlement_type") or "standard").lower()
    if stype in {"upi", "card", "netbanking"}:
        return stype
    return "card"


def _fee_layers(srow: dict, fee_schedule: dict) -> dict[str, Decimal]:
    gross = money(srow.get("gross_amount") or ZERO)
    fee = money(srow.get("fee") or ZERO)
    fee_gst = money(srow.get("fee_gst") or ZERO)
    tds = money(srow.get("tds") or ZERO)
    if gross > ZERO and fee == ZERO:
        fee = recompute_fee(gross, _payment_method(srow), fee_schedule)
    if fee > ZERO and fee_gst == ZERO:
        fee_gst = recompute_gst_on_fee(fee, fee_schedule)
    instant = ZERO
    instant_gst = ZERO
    if (srow.get("settlement_type") or "").lower() == "instant" and gross > ZERO:
        instant = recompute_instant_settlement_fee(gross, fee_schedule)
        instant_gst = recompute_gst_on_fee(instant, fee_schedule)
    if gross > ZERO and tds == ZERO and money(srow.get("tds") or ZERO) == ZERO:
        stated_tds = srow.get("tds")
        if stated_tds not in (None, "", "0", "0.00"):
            tds = money(stated_tds)
        elif money(srow.get("tds") or ZERO) > ZERO:
            tds = money(srow["tds"])
    if gross > ZERO and tds == ZERO:
        # Only infer TDS when settlement row explicitly carries a non-zero slot.
        pass
    return {
        "gross": gross,
        "fee": fee,
        "fee_gst": fee_gst,
        "tds": tds,
        "instant": instant,
        "instant_gst": instant_gst,
    }


def _expected_settlement_net(srow: dict, fee_schedule: dict) -> Decimal:
    layers = _fee_layers(srow, fee_schedule)
    total_fee = money(layers["fee"])
    total_gst = money(layers["fee_gst"])
    return _settlement_net_components(
        layers["gross"],
        total_fee,
        total_gst,
        layers["tds"],
        adjustments=money(srow.get("adjustments") or ZERO),
        reserve_hold=money(srow.get("reserve_hold") or ZERO),
        reserve_release=money(srow.get("reserve_release") or ZERO),
    )


def _bank_settlement_explained(srow: dict, bank_amt: Decimal, fee_schedule: dict) -> bool:
    """True when bank credit vs settlement net is explained by known fee layers."""
    bank_amt = money(bank_amt)
    sett_net = money(srow.get("net_amount") or ZERO)
    if bank_amt == sett_net:
        return True

    layers = _fee_layers(srow, fee_schedule)
    gross = layers["gross"]
    if gross <= ZERO:
        return False

    fee = layers["fee"]
    fee_gst = layers["fee_gst"]
    tds = layers["tds"]
    instant = layers["instant"]
    instant_gst = layers["instant_gst"]

    recomputed = _expected_settlement_net(srow, fee_schedule)
    if bank_amt == recomputed:
        return True

    delta = money(abs(sett_net - bank_amt))
    explainable = {
        fee,
        fee_gst,
        tds,
        instant,
        instant_gst,
        money(fee + fee_gst),
        money(instant + instant_gst),
        money(fee_gst + instant_gst),
        money(fee + fee_gst + tds),
        money(instant + instant_gst + fee_gst),
    }
    if delta in explainable:
        return True

    # Bank may align with net omitting one known layer (timing / posting variants).
    candidates = [
        money(recomputed + fee_gst),
        money(recomputed - fee_gst),
        money(recomputed + tds),
        money(recomputed - tds),
        money(gross - fee - tds),
        money(gross - fee - fee_gst),
    ]
    return bank_amt in candidates


def _index_by_key(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = hash_join_key(row)
        if key:
            out[key].append(row)
    return out


def _bank_rows_for_key(key: str, bank_ix: dict[str, list[dict]]) -> list[dict]:
    return list(bank_ix.get(key) or [])


def _pick_bank_partner(
    srow: dict,
    key: str,
    bank_ix: dict[str, list[dict]],
    used_bank: set[int],
    fee_schedule: dict,
    *,
    unsettled_sett_for_key: int,
) -> dict | None:
    candidates = _bank_rows_for_key(key, bank_ix)
    exact: list[dict] = []
    explained: list[dict] = []
    keyed: list[dict] = []
    s_amt = money(srow.get("net_amount") or ZERO)
    for brow in candidates:
        if id(brow) in used_bank:
            continue
        keyed.append(brow)
        b_amt = _row_amount(brow)
        if b_amt == s_amt:
            exact.append(brow)
        elif _bank_settlement_explained(srow, b_amt, fee_schedule):
            explained.append(brow)
    if exact:
        return exact[0]
    if explained:
        return explained[0]
    unused_banks = len(keyed)
    if unused_banks == 1 and unsettled_sett_for_key == 1:
        return keyed[0]
    return None


def _ledger_bundle_for_settlement(
    srow: dict,
    ledger: list[dict],
    used_ledger: set[int],
    bank_partner: dict | None = None,
) -> list[dict]:
    gross = money(srow.get("gross_amount") or ZERO)
    if gross <= ZERO and bank_partner is None:
        return []

    bundles: list[list[dict]] = []
    seen_orders: set[str] = set()
    for lrow in ledger:
        order_id = lrow.get("order_id") or ""
        if not order_id or order_id in seen_orders:
            continue
        seen_orders.add(order_id)
        if any(id(r) in used_ledger for r in ledger if r.get("order_id") == order_id):
            continue
        bundle = [r for r in ledger if r.get("order_id") == order_id]
        sale_rows = [r for r in bundle if r.get("entry_type") == "sale"]
        if gross > ZERO and sale_rows:
            if money(sale_rows[0].get("amount") or ZERO) != gross:
                continue
        bundles.append(bundle)

    if not bundles:
        return []

    if bank_partner is not None:
        return min(
            bundles,
            key=lambda b: abs(money(_row_amount(bank_partner) - _ledger_net(b))),
        )

    if len(bundles) == 1:
        return bundles[0]
    return []


def run(records: list) -> dict:
    """Three-way key join + fee-aware reconcile + materiality write-off.

    ``records`` is a flat list of source rows, each tagged with ``_source`` in
    {bank_statement, settlement_report, merchant_ledger}.

    Returns {"matched": [...], "residual": [...], "written_off": [...],
             "clear_rate": float, "stats": {...}}.
    """
    bank = [r for r in records if r.get("_source") == "bank_statement"]
    sett = [r for r in records if r.get("_source") == "settlement_report"]
    ledg = [r for r in records if r.get("_source") == "merchant_ledger"]

    bank_ix = _index_by_key(bank)
    fee_schedule = load_fee_schedule()

    matched: list[dict[str, Any]] = []
    residual: list[dict[str, Any]] = []
    used_bank: set[int] = set()
    used_sett: set[int] = set()
    used_ledger: set[int] = set()

    sett_ix = _index_by_key(sett)

    for srow in sett:
        key = hash_join_key(srow)
        unsettled = sum(
            1 for r in sett_ix.get(key, [srow]) if id(r) not in used_sett
        )
        partner = _pick_bank_partner(
            srow, key, bank_ix, used_bank, fee_schedule, unsettled_sett_for_key=unsettled
        )
        if partner is None:
            continue

        ledger_bundle = _ledger_bundle_for_settlement(
            srow, ledg, used_ledger, bank_partner=partner
        )

        used_bank.add(id(partner))
        used_sett.add(id(srow))
        for lrow in ledger_bundle:
            used_ledger.add(id(lrow))

        merchant = srow.get("merchant_id") or "UNKNOWN"
        bank_amt = _row_amount(partner)
        sett_amt = money(srow.get("net_amount") or ZERO)

        if ledger_bundle:
            ledger_delta = money(bank_amt - _ledger_net(ledger_bundle))
            if ledger_delta != ZERO:
                residual.append(
                    {
                        "join_key": key,
                        "side": "AMOUNT_MISMATCH",
                        "merchant_id": merchant,
                        "amount_delta": f"{ledger_delta:.2f}",
                        "match_key": key or None,
                        "settlement": srow,
                        "bank": partner,
                        "ledger": ledger_bundle,
                    }
                )
                continue

        if bank_amt != sett_amt and not _bank_settlement_explained(
            srow, bank_amt, fee_schedule
        ):
            residual.append(
                {
                    "join_key": key,
                    "side": "AMOUNT_MISMATCH",
                    "merchant_id": merchant,
                    "amount_delta": f"{money(bank_amt - sett_amt):.2f}",
                    "match_key": key or None,
                    "settlement": srow,
                    "bank": partner,
                    "ledger": ledger_bundle or None,
                }
            )
            continue

        matched.append(
            {
                "join_key": key,
                "settlement": srow,
                "bank": partner,
                "ledger": ledger_bundle or None,
                "amount": f"{bank_amt:.2f}",
            }
        )

    # Unmatched settlement → residual
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
        if merchant == "UNKNOWN" and key:
            for srow in _bank_rows_for_key(key, sett_ix):
                merchant = srow.get("merchant_id") or merchant
                if merchant != "UNKNOWN":
                    break
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
