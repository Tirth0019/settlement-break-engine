"""
Registry of archetype modules + CLEAN exact-match generator for L1 fodder.
"""
from __future__ import annotations

from sbe.generator.archetypes import (
    adversarial_narration,
    bank_cutoff_rollover,
    chargeback_plus_fee,
    duplicate_utr,
    fee_plus_gst,
    fx_rounding_drift,
    instant_settlement_fee,
    refund_netted,
    rolling_reserve,
    split_settlement,
    state_holiday_shift,
    t2_period_boundary,
    tds_194o,
    true_leakage,
    upi_rrn_vs_utr,
    utr_truncation,
)
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


def generate_clean(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    gross = pick_gross(rng)
    fee, fee_gst, tds, net = card_settlement_amounts(gross, fee_schedule)
    utr = make_utr(rng)
    settlement = settlement_row(
        settlement_id=f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}",
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
    ledger, *_ = sale_and_fee_ledger(rng, date, gross, fee, fee_gst)
    implied = amount_delta([bank], ledger)
    self_check = money(implied - ZERO)
    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "CLEAN",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(ZERO),
            "lifecycle": "SAME_DAY",
        },
        self_check=self_check,
    )


# Weight table — CLEAN dominates so L1 clear rate can land ~60-75%.
# TRUE_LEAKAGE target: ~8% of all records (ROADMAP Day 1 / BUILD_PLAN R5), not 3%.
ARCHETYPE_WEIGHTS: list[tuple[str, object, float]] = [
    ("CLEAN", generate_clean, 0.54),
    ("FEE_PLUS_GST", fee_plus_gst.generate, 0.05),
    ("TDS_194O", tds_194o.generate, 0.04),
    ("CHARGEBACK_PLUS_FEE", chargeback_plus_fee.generate, 0.03),
    ("REFUND_NETTED", refund_netted.generate, 0.03),
    ("TRUE_LEAKAGE", true_leakage.generate, 0.08),
    ("ADVERSARIAL_NARRATION", adversarial_narration.generate, 0.02),
    ("ROLLING_RESERVE_HOLD", rolling_reserve.generate, 0.03),
    ("T2_PERIOD_BOUNDARY", t2_period_boundary.generate, 0.03),
    ("INSTANT_SETTLEMENT_FEE", instant_settlement_fee.generate, 0.03),
    ("SPLIT_SETTLEMENT", split_settlement.generate, 0.03),
    ("STATE_HOLIDAY_SHIFT", state_holiday_shift.generate, 0.02),
    ("BANK_CUTOFF_ROLLOVER", bank_cutoff_rollover.generate, 0.02),
    ("UTR_TRUNCATION", utr_truncation.generate, 0.02),
    ("UPI_RRN_VS_UTR", upi_rrn_vs_utr.generate, 0.01),
    ("DUPLICATE_UTR", duplicate_utr.generate, 0.01),
    ("FX_ROUNDING_DRIFT", fx_rounding_drift.generate, 0.01),
]

DAY1_MODULES = [
    fee_plus_gst,
    tds_194o,
    chargeback_plus_fee,
    refund_netted,
    true_leakage,
    adversarial_narration,
]

DAY2_MODULES = [
    rolling_reserve,
    t2_period_boundary,
    instant_settlement_fee,
    split_settlement,
    state_holiday_shift,
    bank_cutoff_rollover,
    utr_truncation,
    upi_rrn_vs_utr,
    duplicate_utr,
    fx_rounding_drift,
]

ALL_MODULES = DAY1_MODULES + DAY2_MODULES
