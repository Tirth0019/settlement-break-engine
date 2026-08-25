"""
L5 — roll-forward + Reconciliation Certificate (BUILD_PLAN Phase 4, GATE 4).

THE control. Build this before the agents, not after — it will catch
generator and ledger bugs for the rest of the build (ROADMAP.md Day 4-5).

opening + new - resolved - written_off == closing, in BOTH count and value.
If it does not tie, the run refuses to publish and raises ROLL_FORWARD_BREAK
with the exact figures, not just "reconciliation failed".
"""
from sbe.money import ties


class RollForwardBreak(Exception):
    pass


def check_and_certify(conn, run_date) -> dict:
    """Returns the certificate dict if it ties; raises RollForwardBreak if not."""
    raise NotImplementedError
