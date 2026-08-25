"""
Single source of truth for decimal/rounding discipline (BUILD_PLAN Phase 0 gate).

Every module that touches money — generator archetypes, fee_recompute, the
break ledger, the roll-forward — imports from here. Never instantiate
Decimal or round() ad hoc elsewhere; if two pieces of code round differently,
the roll-forward will not tie and you will spend an afternoon finding out why.
"""
from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")

# BUILD_PLAN L7 — materiality
MATERIALITY_PER_BREAK = Decimal("1.00")
MATERIALITY_DAILY_CAP = Decimal("500.00")


def money(value) -> Decimal:
    """Coerce any numeric input to a 2dp Decimal using the one rounding policy."""
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def is_zero(value: Decimal) -> bool:
    return money(value) == ZERO


def ties(opening, new, resolved, written_off, closing) -> bool:
    """The roll-forward control (ARCHITECTURE.md §9.1 / BUILD_PLAN Tier 0).
    opening + new - resolved - written_off == closing, exactly, in rupees.
    Call this for both count and value; this function handles either.
    """
    return money(opening) + money(new) - money(resolved) - money(written_off) == money(closing)
