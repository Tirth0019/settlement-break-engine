"""
L3 — investigator agent (BUILD_PLAN Phase 5, GATE 5).

Tool-calling LLM. Structured output only: verdict enum + hypothesis +
evidence[] + residual_unexplained + confidence. A MATCH verdict with a
non-zero residual_unexplained is a contract violation, not a warning
(BUILD_PLAN L6 / R4) — enforce this in the pydantic schema, not just by
convention.

Untrusted fields (narration, description) must be delimited and explicitly
labelled untrusted in the prompt from the FIRST version written, not
retrofitted later (ARCHITECTURE.md section 10).
"""
from pydantic import BaseModel
from typing import Literal


class Evidence(BaseModel):
    source: str
    ref: str
    value: str


class InvestigatorVerdict(BaseModel):
    break_id: str
    verdict: Literal["MATCH", "NO_MATCH", "NEEDS_HUMAN"]
    hypothesis: str
    evidence: list[Evidence]
    residual_unexplained: str  # Decimal as string; must be "0.00" if verdict == MATCH
    confidence: float
    tools_called: list[str]


def investigate(break_record: dict, tools: dict) -> InvestigatorVerdict:
    raise NotImplementedError
