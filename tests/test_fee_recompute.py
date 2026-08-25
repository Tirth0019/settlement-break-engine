"""GATE 3 — fee_recompute must match reference/fee_schedule.yaml."""
from decimal import Decimal

from sbe.engine.tools.fee_recompute import (
    load_fee_schedule,
    recompute_chargeback_fee,
    recompute_fee,
    recompute_gst_on_fee,
    recompute_instant_settlement_fee,
    recompute_tds_194o,
)
from sbe.money import money


def test_recompute_fee_card():
    fs = load_fee_schedule()
    assert recompute_fee(Decimal("10000"), "card", fs) == money("200.00")


def test_recompute_gst_on_fee():
    fs = load_fee_schedule()
    assert recompute_gst_on_fee(Decimal("200.00"), fs) == money("36.00")


def test_recompute_tds_on_gross_not_net():
    fs = load_fee_schedule()
    gross = Decimal("10000")
    tds = recompute_tds_194o(gross, fs)
    assert tds == money("10.00")
    assert tds != money((gross - Decimal("200")) * Decimal("0.001"))


def test_recompute_instant_settlement_fee():
    fs = load_fee_schedule()
    assert recompute_instant_settlement_fee(Decimal("10000"), fs) == money("30.00")


def test_recompute_chargeback_fee():
    fs = load_fee_schedule()
    assert recompute_chargeback_fee(fs) == money("400.00")
