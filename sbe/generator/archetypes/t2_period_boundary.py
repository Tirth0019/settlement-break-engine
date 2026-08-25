"""
Archetype: T2_PERIOD_BOUNDARY
Lifecycle: MULTI_DAY

Correct match, wrong window — ledger/settlement expect T+0 cash; bank credit
lands on true T+2 settlement day. Classic false NO_MATCH that auto-closes.
"""
from sbe.engine.tools.banking_calendar import resolve_settlement_date
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
    with_follow_up,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    state = (calendar or {}).get("_merchant_state", "Maharashtra")
    cal = calendar or {}
    gross = pick_gross(rng)
    fee, fee_gst, tds, net = card_settlement_amounts(gross, fee_schedule)
    settle_on = resolve_settlement_date(date, state, cal) if cal else as_date(date)
    # Fallback offset if calendar empty in unit tests
    if not cal:
        from datetime import timedelta

        settle_on = as_date(date) + timedelta(days=2)
    offset = (settle_on - as_date(date)).days
    if offset < 1:
        offset = 2
        settle_on = as_date(date)
        from datetime import timedelta

        settle_on = as_date(date) + timedelta(days=offset)

    utr = make_utr(rng)
    settlement_id = f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}"
    ledger, *_ = sale_and_fee_ledger(rng, date, gross, fee, fee_gst)

    # Day 0: settlement+ledger present, bank missing → open break
    day0_settlement = settlement_row(
        settlement_id=settlement_id,
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=tds,
    )
    day0 = {
        "bank_statement": [],
        "settlement_report": [day0_settlement],
        "merchant_ledger": ledger,
    }
    late_bank = bank_credit_row(
        value_date=settle_on,
        posting_date=settle_on,
        narration=f"NEFT {utr} settlement",
        amount=net,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    follow = {
        "bank_statement": [late_bank],
        "settlement_report": [],
        "merchant_ledger": [],
    }

    implied_open = amount_delta(day0["bank_statement"], day0["merchant_ledger"])
    expected_open = money(-net)
    # After late arrival, bank catches up to ledger expected net
    lifecycle_ok = money(net - net)  # trivial; bank eventually equals net
    self_check = money(implied_open - expected_open) + lifecycle_ok

    return ArchetypeResult(
        rows=with_follow_up(day0, offset, follow),
        ground_truth={
            "archetype": "T2_PERIOD_BOUNDARY",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected_open),
            "lifecycle": "MULTI_DAY",
            "closes_on_offset": offset,
            "expected_settlement_date": fmt_date(settle_on),
            "merchant_state": state,
        },
        self_check=self_check,
    )
