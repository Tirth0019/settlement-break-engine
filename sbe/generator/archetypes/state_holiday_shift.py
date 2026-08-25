"""
Archetype: STATE_HOLIDAY_SHIFT
Lifecycle: SAME_DAY (relative to naive T+2)

Gujarat merchant's true settlement day is pushed by a state holiday;
Maharashtra-naive date join looks like a miss.
"""
from datetime import datetime, time, timedelta

from sbe.engine.tools.banking_calendar import (
    add_banking_days,
    is_settlement_day,
    next_settlement_day,
    resolve_settlement_date,
)
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
    # Prefer a date near a Gujarat-only holiday if calendar is present
    txn = as_date(date)
    if cal:
        # Walk backward to find a txn whose Gujarat settle ≠ Maharashtra settle
        found = None
        for delta in range(0, 40):
            candidate = txn - timedelta(days=delta)
            gj = resolve_settlement_date(candidate, "Gujarat", cal)
            mh = resolve_settlement_date(candidate, "Maharashtra", cal)
            if gj != mh:
                found = candidate
                txn = candidate
                settle_gj = gj
                settle_mh = mh
                break
        if found is None:
            settle_gj = resolve_settlement_date(txn, "Gujarat", cal)
            settle_mh = resolve_settlement_date(txn, "Maharashtra", cal)
    else:
        settle_gj = txn + timedelta(days=4)
        settle_mh = txn + timedelta(days=2)

    gross = pick_gross(rng)
    fee, fee_gst, tds, net = card_settlement_amounts(gross, fee_schedule)
    utr = make_utr(rng)

    # Settlement report uses correct Gujarat settlement date; bank posts then.
    # Naive join on MH date finds settlement but no bank → break on MH window.
    settlement = settlement_row(
        settlement_id=f"STL-{fmt_date(settle_gj).replace('-', '')}-{rng.randint(1000, 9999)}",
        utr=utr,
        merchant_id=merchant,
        settled_at=settle_gj,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=tds,
    )
    bank = bank_credit_row(
        value_date=settle_gj,
        posting_date=settle_gj,
        narration=f"NEFT {utr} settlement",
        amount=net,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger, *_ = sale_and_fee_ledger(rng, txn, gross, fee, fee_gst)

    # On the naive MH settlement date the bank row is absent → open gap = -net
    implied = amount_delta([], ledger)
    expected = money(-net)
    # Full picture (correct state) balances
    full = amount_delta([bank], ledger)
    self_check = money(implied - expected) + money(full - ZERO)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "STATE_HOLIDAY_SHIFT",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "merchant_state": "Gujarat",
            "txn_date": fmt_date(txn),
            "settlement_date_gujarat": fmt_date(settle_gj),
            "settlement_date_maharashtra_naive": fmt_date(settle_mh),
        },
        self_check=self_check,
    )
