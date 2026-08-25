"""
Archetype: TDS_194O
Lifecycle: SAME_DAY

Settlement deducts TDS on gross; merchant ledger wrongly accrues TDS on net-after-MDR.
"""
from sbe.generator.archetypes._helpers import (
    amount_delta,
    bank_credit_row,
    fmt_date,
    fmt_money,
    ledger_row,
    make_utr,
    naive_tds_on_net,
    pick_gross,
    settlement_row,
    tds_settlement_amounts,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    gross = pick_gross(rng)
    fee, fee_gst, tds, net = tds_settlement_amounts(gross, fee_schedule)
    wrong_tds = naive_tds_on_net(gross, fee, fee_schedule)

    utr = make_utr(rng)
    settlement_id = f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}"
    order_id = f"ORD-{rng.randint(100000, 999999)}"
    payment_id = f"PAY-{rng.randint(100000, 999999)}"

    settlement = settlement_row(
        settlement_id=settlement_id,
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=tds,
    )
    bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"NEFT {utr} settlement",
        amount=net,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger = [
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
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id=order_id,
            payment_id=payment_id,
            entry_date=date,
            entry_type="fee",
            amount=wrong_tds,
            description="TDS §194-O booked on net-after-MDR (wrong base)",
        ),
    ]

    implied_delta = amount_delta([bank], ledger)
    expected_delta = money(net - (gross - fee - wrong_tds))
    self_check = money(implied_delta - expected_delta)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "TDS_194O",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected_delta),
            "lifecycle": "SAME_DAY",
            "tds_on_gross": fmt_money(tds),
            "tds_on_net_wrong": fmt_money(wrong_tds),
        },
        self_check=self_check,
    )
