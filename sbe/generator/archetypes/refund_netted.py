"""
Archetype: REFUND_NETTED
Lifecycle: SAME_DAY

Refund is netted inside the settlement batch; merchant ledger still expects
a separate refund credit, so bank looks short by the refund amount.
"""
from sbe.engine.tools.fee_recompute import recompute_fee, recompute_gst_on_fee
from sbe.generator.archetypes._helpers import (
    amount_delta,
    bank_credit_row,
    fmt_date,
    fmt_money,
    ledger_row,
    make_utr,
    pick_gross,
    settlement_net_components,
    settlement_row,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    gross = pick_gross(rng)
    refund = money(rng.randint(500, min(2000, int(gross) // 3)))

    fee = recompute_fee(gross, "card", fee_schedule)
    fee_gst = recompute_gst_on_fee(fee, fee_schedule)
    net = settlement_net_components(gross, fee, fee_gst, ZERO, adjustments=-refund)

    utr = make_utr(rng)
    settlement_id = f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}"
    order_id = f"ORD-{rng.randint(100000, 999999)}"

    settlement = settlement_row(
        settlement_id=settlement_id,
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=ZERO,
        adjustments=-refund,
    )
    bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"NEFT {utr} net batch incl refund",
        amount=net,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger = [
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id=order_id,
            payment_id=f"PAY-{rng.randint(100000, 999999)}",
            entry_date=date,
            entry_type="sale",
            amount=gross,
            description=f"Card sale {order_id}",
        ),
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id=order_id,
            payment_id=f"PAY-{rng.randint(100000, 999999)}",
            entry_date=date,
            entry_type="fee",
            amount=fee,
            description="PG MDR",
        ),
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id=order_id,
            payment_id=f"PAY-{rng.randint(100000, 999999)}",
            entry_date=date,
            entry_type="fee",
            amount=fee_gst,
            description="GST on PG fee",
        ),
    ]

    ledger_expected_bank = money(gross - fee - fee_gst)
    implied_delta = amount_delta([bank], ledger)
    expected_delta = money(net - ledger_expected_bank)
    self_check = money(implied_delta - expected_delta)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "REFUND_NETTED",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected_delta),
            "lifecycle": "SAME_DAY",
            "refund_amount": fmt_money(refund),
            "netted_in_settlement": True,
        },
        self_check=self_check,
    )
