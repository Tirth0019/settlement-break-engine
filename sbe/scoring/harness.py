"""
Scoring harness (BUILD_PLAN Phase 4/GATE 4 onward).

Joins ground_truth (kept out of agent-visible payloads everywhere else)
back against the breaks table. This is the ONLY module allowed to read
ground_truth_archetype for anything other than generation.
"""
import pandas as pd


def per_archetype_table(conn, seed: str) -> pd.DataFrame:
    """Returns columns: archetype, n, correct, acc, verifier_lift — raw
    counts alongside percentages (BUILD_PLAN section 9.5: "84/97 beats 86.6%")."""
    raise NotImplementedError


def value_weighted_reconciled_pct(conn, seed: str) -> float:
    raise NotImplementedError


def leakage_recall(conn, seed: str) -> float:
    """% of TRUE_LEAKAGE breaks that correctly survived to NEEDS_HUMAN —
    one of the three headline numbers the project lives or dies on."""
    raise NotImplementedError


def net_accuracy_lift(conn, seed: str) -> tuple[float, float]:
    """Returns (net_lift, false_overturn_rate). Never report overturn rate alone."""
    raise NotImplementedError
