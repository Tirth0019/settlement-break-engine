"""GATE 0."""
from decimal import Decimal

from sbe.money import money, ties


def test_money_rounds_half_up_to_two_places():
    assert money("1.005") == Decimal("1.01")
    assert money("1.004") == Decimal("1.00")
    assert money("2.675") == Decimal("2.68")


def test_rollforward_ties_example():
    assert ties(opening=10, new=5, resolved=3, written_off=1, closing=11)


def test_rollforward_does_not_tie_example():
    assert not ties(opening=10, new=5, resolved=3, written_off=1, closing=99)
