"""
Shared interface every archetype module implements (BUILD_PLAN Phase 1).

self_check is not optional decoration: it is the generator's own roll-forward,
and raising here at construction time is what turns a silent generator bug
into a loud one at generation time instead of three hours into prompt-tuning
against a broken oracle (BUILD_PLAN Risk R1).
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Callable

from sbe.money import ZERO

Lifecycle = Literal["SAME_DAY", "MULTI_DAY"]


@dataclass
class ArchetypeResult:
    rows: dict            # {"bank_statement": [...], "settlement_report": [...], "merchant_ledger": [...]}
    ground_truth: dict    # {archetype, correct_verdict, correct_residual: Decimal, lifecycle}
    self_check: Decimal   # MUST equal ZERO before this result is accepted

    def __post_init__(self):
        if self.self_check != ZERO:
            archetype = self.ground_truth.get("archetype", "UNKNOWN")
            raise ValueError(
                f"generator self_check failed for {archetype}: got {self.self_check}, "
                f"expected {ZERO} — this is a GENERATOR bug, fix it here before "
                f"suspecting the agent (BUILD_PLAN Risk R1)."
            )


# Type alias every archetype module's `generate` should match.
GenerateFn = Callable[..., ArchetypeResult]


def generate(rng, merchant: str, date, fee_schedule: dict, calendar: dict) -> ArchetypeResult:
    """Every archetype module implements this exact signature."""
    raise NotImplementedError
