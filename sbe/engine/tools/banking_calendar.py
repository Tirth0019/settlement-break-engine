"""
banking_calendar tool (BUILD_PLAN Phase 3).

State-aware settlement-day resolution. T+2 is not universally 48 hours —
a state-specific holiday shifts settlement for some merchants and not
others in the same file (ARCHITECTURE.md section 7 table). Also handles
bank-cutoff-vs-IST-midnight rollover.
"""
import yaml


def load_calendar(path: str = "reference/banking_calendar.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def is_settlement_day(date, merchant_state: str, calendar: dict) -> bool:
    raise NotImplementedError


def resolve_settlement_date(txn_date, merchant_state: str, calendar: dict):
    """Applies T+2 plus any state-specific holiday shift plus bank-cutoff rollover."""
    raise NotImplementedError
