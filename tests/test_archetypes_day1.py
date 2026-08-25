"""Day 1 archetypes — self_check must be zero for every generator call."""
import random
from datetime import date

import pytest

from sbe.engine.tools.fee_recompute import load_fee_schedule
from sbe.generator.archetypes import (
    adversarial_narration,
    chargeback_plus_fee,
    fee_plus_gst,
    refund_netted,
    tds_194o,
    true_leakage,
)
from sbe.money import ZERO


@pytest.fixture
def fee_schedule():
    return load_fee_schedule()


DAY1_MODULES = [
    fee_plus_gst,
    tds_194o,
    chargeback_plus_fee,
    refund_netted,
    true_leakage,
    adversarial_narration,
]


@pytest.mark.parametrize("module", DAY1_MODULES, ids=lambda m: m.__name__.split(".")[-1])
def test_archetype_self_check_zero(module, fee_schedule):
    rng = random.Random(1001)
    result = module.generate(rng, "MERCH_0031", date(2026, 3, 18), fee_schedule, {})
    assert result.self_check == ZERO


def test_true_leakage_ground_truth(fee_schedule):
    rng = random.Random(42)
    result = true_leakage.generate(rng, "MERCH_0031", date(2026, 3, 18), fee_schedule, {})
    assert result.ground_truth["correct_verdict"] == "NEEDS_HUMAN"
    assert result.ground_truth["correct_residual"] > ZERO


def test_adversarial_narration_has_injection(fee_schedule):
    rng = random.Random(7)
    result = adversarial_narration.generate(rng, "MERCH_0031", date(2026, 3, 18), fee_schedule, {})
    narration = result.rows["bank_statement"][0]["narration"]
    assert "ignore prior instructions" in narration.lower()
    assert result.ground_truth["archetype"] == "ADVERSARIAL_NARRATION"
