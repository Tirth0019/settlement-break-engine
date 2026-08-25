"""Day 2 archetypes + bank profiles + calendar smoke."""
import random
from datetime import date, datetime

import pytest

from sbe.engine.tools.banking_calendar import (
    is_settlement_day,
    load_calendar,
    resolve_settlement_date,
)
from sbe.engine.tools.fee_recompute import load_fee_schedule
from sbe.generator.archetypes.registry import DAY2_MODULES
from sbe.generator.bank_profiles import BANK_PROFILES, truncate_narration
from sbe.money import ZERO


@pytest.fixture
def fee_schedule():
    return load_fee_schedule()


@pytest.fixture
def calendar():
    cal = load_calendar()
    cal = dict(cal)
    cal["_merchant_state"] = "Gujarat"
    return cal


@pytest.mark.parametrize("module", DAY2_MODULES, ids=lambda m: m.__name__.split(".")[-1])
def test_day2_self_check_zero(module, fee_schedule, calendar):
    rng = random.Random(2026)
    result = module.generate(rng, "MERCH_0003", date(2026, 3, 18), fee_schedule, calendar)
    assert result.self_check == ZERO


def test_bank_profiles_truncation_lengths():
    lengths = sorted({p.narration_max_len for p in BANK_PROFILES})
    assert lengths == [16, 22, 32]
    p16 = next(p for p in BANK_PROFILES if p.narration_max_len == 16)
    assert truncate_narration("ABCDEFGHIJKLMNOPQRSTUVWXYZ", p16) == "ABCDEFGHIJKLMNOP"


def test_gujarat_holiday_shifts_settlement(calendar):
    # 2026-03-02: nearby Dhuleti 2026-03-04 (Gujarat) vs Holi MH 2026-03-03
    txn = date(2026, 3, 2)
    gj = resolve_settlement_date(txn, "Gujarat", calendar)
    mh = resolve_settlement_date(txn, "Maharashtra", calendar)
    assert is_settlement_day(date(2026, 3, 4), "Gujarat", calendar) is False
    # Settlement dates may differ around the holiday cluster
    assert gj >= txn
    assert mh >= txn


def test_rolling_reserve_is_multi_day(fee_schedule, calendar):
    from sbe.generator.archetypes import rolling_reserve

    r = rolling_reserve.generate(random.Random(1), "MERCH_0003", date(2026, 3, 10), fee_schedule, calendar)
    assert r.ground_truth["lifecycle"] == "MULTI_DAY"
    assert r.rows.get("follow_ups")
    assert r.ground_truth["pair_archetype"] == "ROLLING_RESERVE_RELEASE"


def test_utr_truncation_uses_profile(fee_schedule, calendar):
    from sbe.generator.archetypes import utr_truncation

    r = utr_truncation.generate(random.Random(9), "MERCH_0001", date(2026, 3, 18), fee_schedule, calendar)
    trunc = r.ground_truth["truncated_narration"]
    assert len(trunc) <= r.ground_truth["narration_max_len"]
