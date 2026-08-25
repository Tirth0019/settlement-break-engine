"""
banking_calendar tool (BUILD_PLAN Phase 3).

State-aware settlement-day resolution. T+2 is not universally 48 hours —
a state-specific holiday shifts settlement for some merchants and not
others in the same file (ARCHITECTURE.md section 7 table). Also handles
bank-cutoff-vs-IST-midnight rollover.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import yaml


def load_calendar(path: str | None = None) -> dict:
    if path is None:
        path = str(Path(__file__).resolve().parents[3] / "reference" / "banking_calendar.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _holiday_set(merchant_state: str, calendar: dict) -> set[str]:
    national = set(calendar.get("national_holidays_2026") or [])
    state_map = calendar.get("state_holidays_2026") or {}
    state = set(state_map.get(merchant_state) or [])
    return national | state


def _is_second_or_fourth_saturday(d: date) -> bool:
    if d.weekday() != 5:
        return False
    week_of_month = (d.day - 1) // 7 + 1
    return week_of_month in {2, 4}


def is_settlement_day(value, merchant_state: str, calendar: dict) -> bool:
    d = _as_date(value)
    rules = calendar.get("rules") or {}
    if rules.get("closed_on_sundays", True) and d.weekday() == 6:
        return False
    if rules.get("closed_on_second_and_fourth_saturdays", True) and _is_second_or_fourth_saturday(d):
        return False
    if d.isoformat() in _holiday_set(merchant_state, calendar):
        return False
    return True


def next_settlement_day(value, merchant_state: str, calendar: dict) -> date:
    d = _as_date(value)
    while not is_settlement_day(d, merchant_state, calendar):
        d += timedelta(days=1)
    return d


def add_banking_days(value, n: int, merchant_state: str, calendar: dict) -> date:
    d = _as_date(value)
    remaining = n
    while remaining > 0:
        d += timedelta(days=1)
        if is_settlement_day(d, merchant_state, calendar):
            remaining -= 1
    return d


def apply_cutoff_rollover(txn_dt, merchant_state: str, calendar: dict) -> date:
    """Post-cutoff IST timestamps roll to the next settlement day."""
    if isinstance(txn_dt, datetime):
        cutoff_raw = calendar.get("bank_cutoff_ist", "18:00")
        hh, mm = map(int, str(cutoff_raw).split(":"))
        cutoff = time(hh, mm)
        d = txn_dt.date()
        if txn_dt.time() >= cutoff:
            return next_settlement_day(d + timedelta(days=1), merchant_state, calendar)
        return next_settlement_day(d, merchant_state, calendar)
    return next_settlement_day(txn_dt, merchant_state, calendar)


def resolve_settlement_date(txn_date, merchant_state: str, calendar: dict, *, after_cutoff: bool = False):
    """Applies T+2 plus any state-specific holiday shift plus bank-cutoff rollover."""
    rules = calendar.get("rules") or {}
    lag = int(rules.get("standard_settlement_lag_banking_days", 2))
    if isinstance(txn_date, datetime):
        start = apply_cutoff_rollover(txn_date, merchant_state, calendar)
    else:
        start = _as_date(txn_date)
        if after_cutoff:
            start = next_settlement_day(start + timedelta(days=1), merchant_state, calendar)
        else:
            start = next_settlement_day(start, merchant_state, calendar)
    return add_banking_days(start, lag, merchant_state, calendar)
