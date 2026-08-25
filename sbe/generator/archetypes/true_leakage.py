"""
Archetype: TRUE_LEAKAGE
Lifecycle: SAME_DAY

Settlement and ledger agree on expected bank credit; bank is short with no
fee/TDS/reserve explanation — must survive to NEEDS_HUMAN.
"""
from sbe.generator.archetypes._helpers import (
    amount_delta,
    bank_credit_row,
    card_settlement_amounts,
    fmt_date,
    fmt_money,
    ledger_row,
    make_utr,
    pick_gross,
    settlement_row,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    gross = pick_gross(rng)
    fee, fee_gst, _tds, net = card_settlement_amounts(gross, fee_schedule)
    leakage = money(rng.randint(100, 500))
    bank_credit = money(net - leakage)

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
        tds=_tds,
    )
    bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"NEFT {utr} settlement",
        amount=bank_credit,
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
            amount=fee_gst,
            description="GST on PG fee",
        ),
    ]

    implied_delta = amount_delta([bank], ledger)
    expected_delta = money(bank_credit - net)
    self_check = money(implied_delta - expected_delta)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "TRUE_LEAKAGE",
            "correct_verdict": "NEEDS_HUMAN",
            "correct_residual": leakage,
            "amount_delta": fmt_money(expected_delta),
            "lifecycle": "SAME_DAY",
            "leakage_amount": fmt_money(leakage),
        },
        self_check=self_check,
    )
