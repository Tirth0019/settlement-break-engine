"""
Generator self-assertion pass (BUILD_PLAN Phase 1 GATE 1).

Run this before any agent ever sees a seed. It must be green on all three
dev seeds before Phase 2 starts. This is the generator's own roll-forward:
every archetype's self_check already passed at construction (base.py), so
this pass focuses on CROSS-archetype and cross-source consistency.
"""
from decimal import Decimal
from sbe.money import ZERO


def validate_seed(archetype_results: list) -> None:
    """
    Raises AssertionError with a specific, actionable message on first failure.
    TODO (Day 2): implement the cross-source balance check —
        sum(bank deltas) == sum(settlement deltas) == sum(ledger deltas)
    across the whole seed, not just per-archetype.
    """
    for r in archetype_results:
        assert r.self_check == ZERO, (
            f"{r.ground_truth.get('archetype')}: self_check={r.self_check}, expected {ZERO}"
        )
    # TODO: cross-source total balance assertion
    # TODO: label distribution check against configured injection rates (print, don't just assert)
    raise NotImplementedError("cross-source balance check not yet implemented — see TODOs above")
