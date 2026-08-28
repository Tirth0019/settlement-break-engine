"""reserve_schedule tool — rolling reserve hold % and release lag from the
shared fee schedule (ARCHITECTURE.md §7.1 tool table)."""
from __future__ import annotations

from typing import Any

from sbe.engine.tools.fee_recompute import load_fee_schedule


def reserve_schedule(merchant_id: str = "", fee_schedule: dict | None = None) -> dict[str, Any]:
    """Return hold pct and hold_days. Merchant overrides are not modelled yet;
    ``merchant_id`` is accepted for schema symmetry with production schedules.
    """
    del merchant_id
    schedule = fee_schedule if fee_schedule is not None else load_fee_schedule()
    rr = schedule.get("rolling_reserve") or {}
    return {
        "hold_pct": float(rr.get("pct", 0)),
        "hold_days": int(rr.get("hold_days", 0)),
        # Demo seed uses a short lag so MULTI_DAY closes fit a 10-day window;
        # the schedule hold_days is the contractual figure for analyst packets.
        "demo_release_lag_days": 3,
    }
