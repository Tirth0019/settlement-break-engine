"""
Per-bank narration truncation rules (ARCHITECTURE.md §4.1).

TODO (Day 1): define 3-4 synthetic bank profiles, each with a different
narration max-length (16 / 22 / 32 chars) so UTR_TRUNCATION has something
real to truncate. Keep this deterministic given the same rng seed.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BankProfile:
    name: str
    narration_max_len: int


BANK_PROFILES = [
    BankProfile(name="TODO_BANK_A", narration_max_len=16),
    BankProfile(name="TODO_BANK_B", narration_max_len=22),
    BankProfile(name="TODO_BANK_C", narration_max_len=32),
]


def truncate_narration(narration: str, profile: BankProfile) -> str:
    return narration[: profile.narration_max_len]
