"""
Archetype: SPLIT_SETTLEMENT
Lifecycle: SAME_DAY

TODO (BUILD_PLAN Phase 1 / ROADMAP.md Day 1-2): implement using sbe.money
for every arithmetic step. If this archetype involves any fee, GST, or TDS
figure, call sbe.engine.tools.fee_recompute for it rather than computing it
inline here — the generator and the engine sharing one math path is what
prevents them from silently disagreeing (BUILD_PLAN Risk R1).

self_check must be Decimal("0.00"): recompute this archetype expected gap
independently of however the rows were constructed, and assert they match.
"""
from sbe.generator.archetypes.base import ArchetypeResult


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    raise NotImplementedError(
        "TODO: implement SPLIT_SETTLEMENT — see ARCHITECTURE.md section 4 and BUILD_PLAN Phase 1"
    )
