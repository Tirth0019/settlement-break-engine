"""
L7 — rule graduation (BUILD_PLAN Tier 2 item 2 / Tier 3).

Ship DETECTION + the declining-LLM-calls chart first — cheap, and it is the
whole differentiator. The approval/promotion-back-into-L1 workflow is Tier 3:
stub it, show the proposal in the demo, do not wire it back into L1 live
unless Tiers 0-2 are fully done and tested.
"""

def detect_graduation_candidates(resolved_breaks: list, min_occurrences: int = 20) -> list:
    """Finds archetypes resolved identically, at high confidence, with zero
    overturns, N+ times. Returns proposed-rule dicts with supporting evidence
    and an estimated LLM-call/cost reduction — NOT a promotion."""
    raise NotImplementedError


def llm_calls_by_day(conn) -> dict:
    """For the declining-calls-per-day chart used in the demo (ROADMAP.md Day 9)."""
    raise NotImplementedError
