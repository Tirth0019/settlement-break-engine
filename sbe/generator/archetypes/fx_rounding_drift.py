"""
Archetype: FX_ROUNDING_DRIFT
Lifecycle: SAME_DAY

Sub-rupee drift on international settlement — within materiality if tiny,
but generated as an explainable paise-level gap on the fee path.
"""
from decimal import Decimal

from sbe.engine.tools.fee_recompute import recompute_fee, recompute_gst_on_fee
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
    gross = pick_gross(rng, 8000, 40000)
    fee = recompute_fee(gross, "international", fee_schedule)
    fee_gst = recompute_gst_on_fee(fee, fee_schedule)
    exact_net = settlement_net_components(gross, fee, fee_gst, ZERO)
    # Bank posts with FX conversion rounding drift of a few paise
    drift = money(Decimal(rng.choice(["0.01", "0.02", "0.03", "-0.01", "-0.02"])))
    bank_amount = money(exact_net + drift)

    utr = make_utr(rng)
    settlement = settlement_row(
        settlement_id=f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}",
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=ZERO,
        settlement_type="international",
    )
    bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"FX NEFT {utr}",
        amount=bank_amount,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger, *_ = sale_and_fee_ledger(rng, date, gross, fee, fee_gst)

    implied = amount_delta([bank], ledger)
    expected = drift
    self_check = money(implied - expected)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "FX_ROUNDING_DRIFT",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "fx_drift": fmt_money(drift),
            "exact_net": fmt_money(exact_net),
            "bank_amount": fmt_money(bank_amount),
        },
        self_check=self_check,
    )
