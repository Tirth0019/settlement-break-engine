"""
Archetype: ROLLING_RESERVE_HOLD + ROLLING_RESERVE_RELEASE
Lifecycle: MULTI_DAY

Day 0: reserve_hold reduces bank credit vs ledger expectation.
Day +lag: reserve_release arrives with no current-period sale — closes the hold.
"""
from decimal import Decimal

from sbe.generator.archetypes._helpers import (
    amount_delta,
    bank_credit_row,
    card_settlement_amounts,
    fmt_date,
    fmt_money,
    ledger_row,
    make_utr,
    pick_gross,
    reserve_hold_amount,
    sale_and_fee_ledger,
    settlement_row,
    with_follow_up,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


# Short lag so a 10-day seed can demonstrate open→close (schedule still says 90d).
DEMO_RELEASE_LAG_DAYS = 3


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    gross = pick_gross(rng)
    fee, fee_gst, tds, net_full = card_settlement_amounts(gross, fee_schedule)
    hold = reserve_hold_amount(gross, fee_schedule)
    net_held = money(net_full - hold)

    utr = make_utr(rng)
    settlement_id = f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}"
    ledger, order_id, payment_id = sale_and_fee_ledger(rng, date, gross, fee, fee_gst)

    hold_settlement = settlement_row(
        settlement_id=settlement_id,
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=tds,
        reserve_hold=hold,
        settlement_type="standard",
    )
    hold_bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"NEFT {utr} settlement less reserve",
        amount=net_held,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )

    release_utr = make_utr(rng)
    release_settlement = settlement_row(
        settlement_id=f"{settlement_id}-REL",
        utr=release_utr,
        merchant_id=merchant,
        settled_at=date,  # placeholder; seed writer shifts by offset
        gross=ZERO,
        fee=ZERO,
        fee_gst=ZERO,
        tds=ZERO,
        reserve_release=hold,
        settlement_type="reserve_release",
        txn_count=0,
    )
    release_bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"NEFT {release_utr} reserve release",
        amount=hold,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )

    day0 = {
        "bank_statement": [hold_bank],
        "settlement_report": [hold_settlement],
        "merchant_ledger": ledger,
    }
    follow = {
        "bank_statement": [release_bank],
        "settlement_report": [release_settlement],
        "merchant_ledger": [],
    }

    implied_open = amount_delta(day0["bank_statement"], day0["merchant_ledger"])
    expected_open = money(-hold)
    # Lifecycle self-check: open gap is the hold; release later restores bank.
    lifecycle_bank = money(net_held + hold)
    lifecycle_check = money(lifecycle_bank - net_full)
    self_check = money(implied_open - expected_open) + lifecycle_check

    return ArchetypeResult(
        rows=with_follow_up(day0, DEMO_RELEASE_LAG_DAYS, follow),
        ground_truth={
            "archetype": "ROLLING_RESERVE_HOLD",
            "pair_archetype": "ROLLING_RESERVE_RELEASE",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected_open),
            "lifecycle": "MULTI_DAY",
            "closes_on_offset": DEMO_RELEASE_LAG_DAYS,
            "reserve_hold": fmt_money(hold),
            "order_id": order_id,
            "payment_id": payment_id,
        },
        self_check=self_check,
    )
