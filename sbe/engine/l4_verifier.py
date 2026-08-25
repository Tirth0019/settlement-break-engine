"""
L4 — verifier agent (BUILD_PLAN Phase 6, GATE 6).

MUST be a different model family from L3 (config.py enforces this at import
time). MUST receive raw source rows, not just the investigator narrative
(BUILD_PLAN L4) — narrative-only input means it can only critique the story,
not check the arithmetic.

GATE 6: net accuracy lift must be positive. If it is ~0, first confirm this
function is actually being called with raw rows and an actually-different
model before touching any prompt (Risk R3).
"""
from pydantic import BaseModel
from typing import Literal


class VerifierDecision(BaseModel):
    break_id: str
    decision: Literal["UPHELD", "OVERTURN", "ESCALATE"]
    new_verdict: str | None
    reason: str
    model: str


def verify(investigator_verdict, raw_source_rows: dict) -> VerifierDecision:
    """Independently re-runs fee_recompute rather than trusting the
    investigators reported figure (BUILD_PLAN Phase 6)."""
    raise NotImplementedError
