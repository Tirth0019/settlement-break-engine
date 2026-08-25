"""
L2 — break ledger (BUILD_PLAN Phase 2, GATE 2 — the hardest engineering here,
not the agents. Build and test this before writing a single agent prompt).

Owns: persistent break_id allocation, ageing bucket computation, idempotent
re-runs, and late-arrival auto-close.

GATE 2 is a written test, not a manual check:
  - re-running the same date must produce byte-identical `breaks` table state
  - a break opened on day N must auto-close on day N+k when the late credit
    arrives, without creating a spurious second break
"""
from decimal import Decimal


def open_break(conn, merchant_id: str, side: str, amount_delta: Decimal, run_date) -> str:
    """Allocates a new break_id or returns the existing one for an idempotent re-run."""
    raise NotImplementedError


def age_breaks(conn, as_of_date) -> None:
    """Recomputes age_days / ageing_bucket for all OPEN breaks as of a given run date."""
    raise NotImplementedError


def try_late_arrival_close(conn, incoming_record: dict, run_date) -> str | None:
    """Checks whether an incoming record closes an existing OPEN break instead
    of becoming a new one. Returns the closed break_id, or None."""
    raise NotImplementedError
