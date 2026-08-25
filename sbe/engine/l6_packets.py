"""
L6 — break packets + proposed journal entries (BUILD_PLAN Tier 1/2).

Output is a copy-pasteable analyst artifact (ARCHITECTURE.md section 11), not
a verdict blob. residual_unexplained must render to the paise.

Maker-checker: this module only ever proposes a JE into an approval queue.
Nothing here posts to a ledger. If you are tempted to add an auto-post path
"just for the demo", do not (BUILD_PLAN: explicitly out of scope).
"""

def render_break_packet(break_record: dict) -> str:
    raise NotImplementedError


def propose_journal_entry(break_record: dict) -> dict:
    """Returns a JE dict sitting in PENDING_APPROVAL state. Never auto-posts."""
    raise NotImplementedError
