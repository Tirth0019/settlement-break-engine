"""
Per-bank narration truncation rules (ARCHITECTURE.md §4.1).

Three synthetic bank profiles with 16 / 22 / 32 char narration caps so
UTR_TRUNCATION has something real to chop. Deterministic given the same rng.
"""
from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class BankProfile:
    name: str
    narration_max_len: int


BANK_PROFILES = [
    BankProfile(name="HDFC", narration_max_len=16),
    BankProfile(name="ICICI", narration_max_len=22),
    BankProfile(name="SBI", narration_max_len=32),
    BankProfile(name="AXIS", narration_max_len=22),
]


def pick_profile(rng: random.Random) -> BankProfile:
    return rng.choice(BANK_PROFILES)


def truncate_narration(narration: str, profile: BankProfile) -> str:
    return narration[: profile.narration_max_len]
