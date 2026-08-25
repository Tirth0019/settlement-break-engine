"""
Archetype: CHARGEBACK_PLUS_FEE
Lifecycle: SAME_DAY

Chargeback principal + flat fee + GST on fee debited at bank; absent from ledger.
"""
from datetime import timedelta

from sbe.generator.archetypes._helpers import (
    amount_delta,
    as_date,
    bank_debit_row,
    chargeback_debit_total,
    fmt_date,
    fmt_money,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    cb_amount, cb_fee, cb_gst, cb_total = chargeback_debit_total(fee_schedule)
    cb_date = as_date(date) - timedelta(days=rng.randint(1, 3))

    bank = bank_debit_row(
        value_date=cb_date,
        posting_date=cb_date,
        narration=f"CHRGBK CB-{rng.randint(80000, 99999)}",
        amount=cb_total,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger: list = []

    implied_delta = amount_delta([bank], ledger)
    expected_delta = money(-cb_total)
    self_check = money(implied_delta - expected_delta)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "CHARGEBACK_PLUS_FEE",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected_delta),
            "lifecycle": "SAME_DAY",
            "chargeback_amount": fmt_money(cb_amount),
            "chargeback_fee": fmt_money(cb_fee),
            "chargeback_fee_gst": fmt_money(cb_gst),
            "chargeback_date": fmt_date(cb_date),
        },
        self_check=self_check,
    )
