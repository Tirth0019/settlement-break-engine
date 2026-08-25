"""
L1 — deterministic pass (BUILD_PLAN Phase 3, GATE 3).

Exact hash-join on canonical identifier across the three sources, then
materiality write-off for anything below sbe.money.MATERIALITY_PER_BREAK,
capped at MATERIALITY_DAILY_CAP aggregate.

Target: clears 60-75% of records. If this is tuned to hit that band rather
than landing there naturally, something is wrong with the seed or the join
key — do not force it (ROADMAP.md Day 4).
"""

def run(records: list) -> dict:
    """Returns {"matched": [...], "residual": [...], "written_off": [...]}"""
    raise NotImplementedError


def hash_join_key(record: dict) -> str:
    """Canonical identifier used for the exact match. TODO: define precedence
    across UTR / settlement_id / normalised bank narration."""
    raise NotImplementedError
