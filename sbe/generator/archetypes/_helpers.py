"""Shared row builders and reconciliation helpers for archetype generators."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sbe.engine.tools.fee_recompute import (
    recompute_chargeback_fee,
    recompute_fee,
    recompute_gst_on_fee,
    recompute_tds_194o,
)
from sbe.money import ZERO, money


def as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def fmt_date(value) -> str:
    return as_date(value).isoformat()


def fmt_money(value: Decimal) -> str:
    return f"{money(value):.2f}"


def pick_gross(rng, low: int = 5000, high: int = 50000) -> Decimal:
    return money(rng.randint(low, high))


def make_utr(rng) -> str:
    return f"UTR{rng.randint(10**15, 10**16 - 1)}"


def settlement_net_components(
    gross: Decimal,
    fee: Decimal,
    fee_gst: Decimal,
    tds: Decimal,
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


def settlement_row(
    *,
    settlement_id: str,
    utr: str,
    merchant_id: str,
    settled_at,
    gross: Decimal,
    fee: Decimal,
    fee_gst: Decimal,
    tds: Decimal,
    adjustments: Decimal = ZERO,
    reserve_hold: Decimal = ZERO,
    reserve_release: Decimal = ZERO,
    settlement_type: str = "standard",
    txn_count: int = 1,
) -> dict[str, Any]:
    net = settlement_net_components(
        gross, fee, fee_gst, tds, adjustments, reserve_hold, reserve_release
    )
    return {
        "settlement_id": settlement_id,
        "utr": utr,
        "merchant_id": merchant_id,
        "settled_at": fmt_date(settled_at),
        "settlement_type": settlement_type,
        "gross_amount": fmt_money(gross),
        "fee": fmt_money(fee),
        "fee_gst": fmt_money(fee_gst),
        "tds": fmt_money(tds),
        "adjustments": fmt_money(adjustments),
        "reserve_hold": fmt_money(reserve_hold),
        "reserve_release": fmt_money(reserve_release),
        "net_amount": fmt_money(net),
        "txn_count": txn_count,
    }


def bank_credit_row(
    *,
    value_date,
    posting_date,
    narration: str,
    amount: Decimal,
    bank_ref: str,
    closing_balance: str = "",
) -> dict[str, Any]:
    return {
        "value_date": fmt_date(value_date),
        "posting_date": fmt_date(posting_date),
        "narration": narration,
        "debit": "",
        "credit": fmt_money(amount),
        "closing_balance": closing_balance,
        "bank_ref": bank_ref,
    }


def bank_debit_row(
    *,
    value_date,
    posting_date,
    narration: str,
    amount: Decimal,
    bank_ref: str,
    closing_balance: str = "",
) -> dict[str, Any]:
    return {
        "value_date": fmt_date(value_date),
        "posting_date": fmt_date(posting_date),
        "narration": narration,
        "debit": fmt_money(amount),
        "credit": "",
        "closing_balance": closing_balance,
        "bank_ref": bank_ref,
    }


def ledger_row(
    *,
    entry_id: str,
    order_id: str,
    payment_id: str,
    entry_date,
    entry_type: str,
    amount: Decimal,
    description: str,
    currency: str = "INR",
    status: str = "posted",
) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "order_id": order_id,
        "payment_id": payment_id,
        "entry_date": fmt_date(entry_date),
        "entry_type": entry_type,
        "amount": fmt_money(amount),
        "currency": currency,
        "status": status,
        "description": description,
    }


def bank_net(rows: list[dict]) -> Decimal:
    total = ZERO
    for row in rows:
        if row.get("credit"):
            total += money(row["credit"])
        if row.get("debit"):
            total -= money(row["debit"])
    return money(total)


def settlement_net(rows: list[dict]) -> Decimal:
    return money(sum(money(r["net_amount"]) for r in rows))


def ledger_net(rows: list[dict]) -> Decimal:
    total = ZERO
    for row in rows:
        amount = money(row["amount"])
        if row["entry_type"] in {"sale", "adjustment"}:
            total += amount
        elif row["entry_type"] in {"refund", "chargeback", "fee"}:
            total -= amount
        else:
            total += amount
    return money(total)


def amount_delta(bank_rows: list[dict], ledger_rows: list[dict]) -> Decimal:
    """Negative means bank received less than merchant ledger expects."""
    return money(bank_net(bank_rows) - ledger_net(ledger_rows))


def card_settlement_amounts(gross: Decimal, fee_schedule: dict) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    fee = recompute_fee(gross, "card", fee_schedule)
    fee_gst = recompute_gst_on_fee(fee, fee_schedule)
    tds = ZERO
    net = settlement_net_components(gross, fee, fee_gst, tds)
    return fee, fee_gst, tds, net


def chargeback_debit_total(fee_schedule: dict) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    cb_amount = money("12000.00")
    cb_fee = recompute_chargeback_fee(fee_schedule)
    cb_gst = recompute_gst_on_fee(cb_fee, fee_schedule)
    total = money(cb_amount + cb_fee + cb_gst)
    return cb_amount, cb_fee, cb_gst, total


def tds_settlement_amounts(gross: Decimal, fee_schedule: dict) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    fee = recompute_fee(gross, "card", fee_schedule)
    fee_gst = recompute_gst_on_fee(fee, fee_schedule)
    tds = recompute_tds_194o(gross, fee_schedule)
    net = settlement_net_components(gross, fee, fee_gst, tds)
    return fee, fee_gst, tds, net


def naive_tds_on_net(gross: Decimal, fee: Decimal, fee_schedule: dict) -> Decimal:
    """Wrong ledger treatment — TDS on net after MDR instead of on gross."""
    net_before_tds = money(gross - fee)
    rate = Decimal(str(fee_schedule["tds_194o"]["rate"]))
    return money(net_before_tds * rate)


def reserve_hold_amount(gross: Decimal, fee_schedule: dict) -> Decimal:
    pct = Decimal(str(fee_schedule["rolling_reserve"]["pct"]))
    return money(money(gross) * pct)


def empty_sources() -> dict:
    return {"bank_statement": [], "settlement_report": [], "merchant_ledger": []}


def with_follow_up(primary: dict, day_offset: int, follow: dict) -> dict:
    """Attach a later-day payload for MULTI_DAY archetypes."""
    out = dict(primary)
    out["follow_ups"] = [{"day_offset": day_offset, **follow}]
    return out


def flatten_result_rows(result) -> dict:
    """Collapse primary + follow_up rows for seed-wide validation."""
    bank = list(result.rows.get("bank_statement") or [])
    sett = list(result.rows.get("settlement_report") or [])
    ledg = list(result.rows.get("merchant_ledger") or [])
    for fu in result.rows.get("follow_ups") or []:
        bank.extend(fu.get("bank_statement") or [])
        sett.extend(fu.get("settlement_report") or [])
        ledg.extend(fu.get("merchant_ledger") or [])
    return {"bank_statement": bank, "settlement_report": sett, "merchant_ledger": ledg}


def settlement_row_integrity(row: dict) -> Decimal:
    """Return residual of stated net vs recomputed components (must be 0)."""
    recomputed = settlement_net_components(
        money(row["gross_amount"]),
        money(row["fee"]),
        money(row["fee_gst"]),
        money(row["tds"]),
        money(row.get("adjustments") or ZERO),
        money(row.get("reserve_hold") or ZERO),
        money(row.get("reserve_release") or ZERO),
    )
    return money(money(row["net_amount"]) - recomputed)


def sale_and_fee_ledger(rng, date, gross: Decimal, fee: Decimal, fee_gst: Decimal | None = None, *, omit_gst: bool = False):
    order_id = f"ORD-{rng.randint(100000, 999999)}"
    payment_id = f"PAY-{rng.randint(100000, 999999)}"
    rows = [
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id=order_id,
            payment_id=payment_id,
            entry_date=date,
            entry_type="sale",
            amount=gross,
            description=f"Card sale {order_id}",
        ),
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id=order_id,
            payment_id=payment_id,
            entry_date=date,
            entry_type="fee",
            amount=fee,
            description="PG MDR",
        ),
    ]
    if fee_gst is not None and not omit_gst:
        rows.append(
            ledger_row(
                entry_id=f"LE-{rng.randint(100000, 999999)}",
                order_id=order_id,
                payment_id=payment_id,
                entry_date=date,
                entry_type="fee",
                amount=fee_gst,
                description="GST on PG fee",
            )
        )
    return rows, order_id, payment_id
