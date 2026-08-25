"""GATE 1 — must be green on all three dev seeds before Phase 2 starts."""
import random
from datetime import date

from sbe.engine.tools.banking_calendar import load_calendar
from sbe.engine.tools.fee_recompute import load_fee_schedule
from sbe.generator.archetypes.registry import ALL_MODULES, DAY1_MODULES, DAY2_MODULES, generate_clean
from sbe.generator.validate_seed import validate_seed
from sbe.money import ZERO


def test_all_archetypes_self_check_zero():
    fee_schedule = load_fee_schedule()
    calendar = load_calendar()
    calendar = dict(calendar)
    calendar["_merchant_state"] = "Gujarat"
    rng = random.Random(1001)
    results = []
    for module in ALL_MODULES:
        results.append(
            module.generate(rng, "MERCH_0003", date(2026, 3, 18), fee_schedule, calendar)
        )
    results.append(generate_clean(rng, "MERCH_0001", date(2026, 3, 18), fee_schedule, calendar))
    assert all(r.self_check == ZERO for r in results)
    assert len(DAY1_MODULES) == 6
    assert len(DAY2_MODULES) == 10


def test_cross_source_totals_balance():
    fee_schedule = load_fee_schedule()
    calendar = load_calendar()
    calendar = dict(calendar)
    calendar["_merchant_state"] = "Maharashtra"
    rng = random.Random(1002)
    results = [
        module.generate(rng, "MERCH_0002", date(2026, 3, 18), fee_schedule, calendar)
        for module in ALL_MODULES
    ]
    summary = validate_seed(results, print_distribution=False)
    assert summary["ok"] is True
    assert summary["n"] == len(ALL_MODULES)
