"""
Archetype: INSTANT_SETTLEMENT_FEE
Lifecycle: SAME_DAY

Instant (T+0) surcharge on top of MDR+GST; ledger books standard T+2 fees only.
"""
from sbe.engine.tools.fee_recompute import (
    recompute_fee,
    recompute_gst_on_fee,
    recompute_instant_settlement_fee,
)
from sbe.generator.archetypes._helpers import (
    amount_delta,
    bank_credit_row,
    fmt_date,
    fmt_money,
    make_utr,
    pick_gross,
    sale_and_fee_ledger,
    settlement_net_components,
    settlement_row,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    gross = pick_gross(rng)
    fee = recompute_fee(gross, "card", fee_schedule)
    fee_gst = recompute_gst_on_fee(fee, fee_schedule)
    instant = recompute_instant_settlement_fee(gross, fee_schedule)
    instant_gst = recompute_gst_on_fee(instant, fee_schedule)
    net = settlement_net_components(gross, money(fee + instant), money(fee_gst + instant_gst), ZERO)

    utr = make_utr(rng)
    settlement = settlement_row(
        settlement_id=f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}",
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=money(fee + instant),
        fee_gst=money(fee_gst + instant_gst),
        tds=ZERO,
        settlement_type="instant",
    )
    bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"IMPS {utr} instant settle",
        amount=net,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger, *_ = sale_and_fee_ledger(rng, date, gross, fee, fee_gst)

    missing = money(instant + instant_gst)
    implied = amount_delta([bank], ledger)
    expected = money(-missing)
    self_check = money(implied - expected)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "INSTANT_SETTLEMENT_FEE",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "instant_surcharge": fmt_money(instant),
            "instant_surcharge_gst": fmt_money(instant_gst),
        },
        self_check=self_check,
    )
