"""
Archetype: UTR_TRUNCATION
Lifecycle: SAME_DAY

Bank chops the UTR/narration at profile max length — same money, different string.
"""
from sbe.generator.bank_profiles import pick_profile, truncate_narration
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
    profile = pick_profile(rng)
    # Prefer the aggressive 16-char profile often enough for hard cases
    if rng.random() < 0.5:
        from sbe.generator.bank_profiles import BANK_PROFILES

        profile = BANK_PROFILES[0]  # HDFC 16

    gross = pick_gross(rng)
    fee, fee_gst, tds, net = card_settlement_amounts(gross, fee_schedule)
    utr = make_utr(rng)
    full_narration = f"NEFT {utr} {merchant} SETTLEMENT CREDIT"
    truncated = truncate_narration(full_narration, profile)

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
        narration=truncated,
        amount=net,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger, *_ = sale_and_fee_ledger(rng, date, gross, fee, fee_gst)

    # Amounts match; identifier mismatch is the break surface
    implied = amount_delta([bank], ledger)
    expected = ZERO
    self_check = money(implied - expected)
    assert len(truncated) <= profile.narration_max_len
    assert truncated != full_narration or len(full_narration) <= profile.narration_max_len

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "UTR_TRUNCATION",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "full_utr": utr,
            "full_narration": full_narration,
            "truncated_narration": truncated,
            "bank_profile": profile.name,
            "narration_max_len": profile.narration_max_len,
        },
        self_check=self_check,
    )
