"""
decimal_calc — the only place arithmetic happens outside fee_recompute.

Design principle L6 (BUILD_PLAN): the model picks the hypothesis, a
deterministic tool does the maths. If you find yourself letting an LLM
add two numbers in its own output text, that is the top cause of quiet
accuracy rot (Risk R4) — route it through here instead, and log the call.
"""
from decimal import Decimal
from sbe.money import money


def add(*values) -> Decimal:
    return money(sum(money(v) for v in values))


def subtract(a, b) -> Decimal:
    return money(money(a) - money(b))


def residual(claimed_gap: Decimal, explained_amounts: list) -> Decimal:
    """The core residual_unexplained computation every investigator verdict
    depends on. Must be exact to the paise."""
    return money(claimed_gap) - add(*explained_amounts)
