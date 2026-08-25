"""
Archetype: UPI_RRN_VS_UTR
Lifecycle: SAME_DAY

Same money movement, different identifier namespaces (UTR on settlement, RRN on bank).
"""
from sbe.generator.archetypes._helpers import (
    amount_delta,
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
    gross = pick_gross(rng)
    # UPI zero-MDR path still has identifiable settlement
    from sbe.engine.tools.fee_recompute import recompute_fee, recompute_gst_on_fee
    from sbe.generator.archetypes._helpers import settlement_net_components

    fee = recompute_fee(gross, "upi", fee_schedule)
    fee_gst = recompute_gst_on_fee(fee, fee_schedule)
    net = settlement_net_components(gross, fee, fee_gst, ZERO)

    utr = make_utr(rng)
    rrn = f"RRN{rng.randint(10**11, 10**12 - 1)}"

    settlement = settlement_row(
        settlement_id=f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}",
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=ZERO,
        settlement_type="upi",
    )
    bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"UPI/{rrn}/CR",
        amount=net,
        bank_ref=rrn,
    )
    ledger, *_ = sale_and_fee_ledger(rng, date, gross, fee, fee_gst if fee_gst else None)

    implied = amount_delta([bank], ledger)
    expected = ZERO
    self_check = money(implied - expected)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "UPI_RRN_VS_UTR",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "utr": utr,
            "rrn": rrn,
        },
        self_check=self_check,
    )
