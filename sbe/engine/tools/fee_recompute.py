"""
fee_recompute — the ONE authoritative fee/GST/TDS math path (BUILD_PLAN L6, Phase 3).

Imported by BOTH the generator archetypes self_check AND the investigator/
verifier tool calls. This is deliberate: if the generator and the engine
computed fees separately, a disagreement between them is indistinguishable
from an agent error (Risk R1). There must be exactly one implementation.

GATE 3: this function must reproduce every generator-computed fee exactly,
to the paise, for every archetype. If it does not, find out which of the
two is wrong before writing a single line of agent prompt.
"""
from decimal import Decimal
from pathlib import Path

import yaml

from sbe.money import money


def load_fee_schedule(path: str | None = None) -> dict:
    if path is None:
        path = str(Path(__file__).resolve().parents[3] / "reference" / "fee_schedule.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _rate(value) -> Decimal:
    return Decimal(str(value))


def _mdr_rate(method: str, fee_schedule: dict) -> Decimal:
    mdr = fee_schedule["mdr"]
    if method not in mdr:
        raise KeyError(f"unknown payment method {method!r}; known: {sorted(mdr)}")
    return _rate(mdr[method])


def recompute_fee(gross_amount: Decimal, method: str, fee_schedule: dict) -> Decimal:
    """MDR fee for a given payment method, per reference/fee_schedule.yaml."""
    gross = money(gross_amount)
    return money(gross * _mdr_rate(method, fee_schedule))


def recompute_gst_on_fee(fee_amount: Decimal, fee_schedule: dict) -> Decimal:
    return money(money(fee_amount) * _rate(fee_schedule["gst_rate"]))


def recompute_tds_194o(gross_amount: Decimal, fee_schedule: dict) -> Decimal:
    """TDS under section 194-O — deducted on GROSS, not net."""
    gross = money(gross_amount)
    rate = _rate(fee_schedule["tds_194o"]["rate"])
    return money(gross * rate)


def recompute_instant_settlement_fee(gross_amount: Decimal, fee_schedule: dict) -> Decimal:
    gross = money(gross_amount)
    surcharge = _rate(fee_schedule["instant_settlement"]["surcharge"])
    return money(gross * surcharge)


def recompute_chargeback_fee(fee_schedule: dict) -> Decimal:
    return money(fee_schedule["chargeback"]["flat_fee"])
