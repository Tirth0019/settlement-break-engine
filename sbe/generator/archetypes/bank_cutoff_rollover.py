"""
Archetype: BANK_CUTOFF_ROLLOVER
Lifecycle: SAME_DAY

Txn after IST bank cutoff rolls value_date to next banking day; date join
keyed on calendar day is off by one for a slice of merchants.
"""
from datetime import datetime, time, timedelta

from sbe.engine.tools.banking_calendar import apply_cutoff_rollover, resolve_settlement_date
from sbe.generator.archetypes._helpers import (
    amount_delta,
    as_date,
    bank_credit_row,
    card_settlement_amounts,
    fmt_date,
    fmt_money,
    make_utr,
    pick_gross,
    sale_and_fee_ledger,
    settlement_row,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    cal = calendar or {}
    state = (cal or {}).get("_merchant_state", "Maharashtra")
    d = as_date(date)
    # Force post-cutoff timestamp
    txn_dt = datetime.combine(d, time(19, 30))
    if cal:
        rolled = apply_cutoff_rollover(txn_dt, state, cal)
        settle_on = resolve_settlement_date(txn_dt, state, cal)
    else:
        rolled = d + timedelta(days=1)
        settle_on = rolled + timedelta(days=2)

    gross = pick_gross(rng)
    fee, fee_gst, tds, net = card_settlement_amounts(gross, fee_schedule)
    utr = make_utr(rng)

    settlement = settlement_row(
        settlement_id=f"STL-{fmt_date(settle_on).replace('-', '')}-{rng.randint(1000, 9999)}",
        utr=utr,
        merchant_id=merchant,
        settled_at=settle_on,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=tds,
    )
    bank = bank_credit_row(
        value_date=settle_on,
        posting_date=settle_on,
        narration=f"NEFT {utr} settlement",
        amount=net,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger, *_ = sale_and_fee_ledger(rng, d, gross, fee, fee_gst)

    # Naive same-calendar-day join misses bank → gap -net; full set balances
    implied_naive = amount_delta([], ledger)
    expected = money(-net)
    full = amount_delta([bank], ledger)
    self_check = money(implied_naive - expected) + money(full - ZERO)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "BANK_CUTOFF_ROLLOVER",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "txn_timestamp_ist": txn_dt.isoformat(sep=" "),
            "rolled_value_date": fmt_date(rolled),
            "settlement_date": fmt_date(settle_on),
            "cutoff_ist": (cal or {}).get("bank_cutoff_ist", "18:00"),
        },
        self_check=self_check,
    )
