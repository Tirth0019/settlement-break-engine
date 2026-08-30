"""Rate-limit detection — fail fast on daily quota, backoff on transient limits."""
from __future__ import annotations

import re


class QuotaExhaustedError(RuntimeError):
    """Daily (TPD) or account quota exhausted — do not retry the full run."""

    def __init__(self, message: str, *, reset_hint: str | None = None) -> None:
        super().__init__(message)
        self.reset_hint = reset_hint


def quota_exhausted_from_error(exc: BaseException) -> QuotaExhaustedError | None:
    """Return QuotaExhaustedError when the message indicates daily TPD exhaustion."""
    msg = str(exc).lower()
    if "429" not in msg and "rate_limit" not in msg and "rate limit" not in msg:
        return None
    if "tokens per day" not in msg and "tpd" not in msg:
        return None
    reset = None
    m = re.search(r"try again in (\d+m[\d.]*s|\d+\.?\d*s)", str(exc), re.I)
    if m:
        reset = m.group(1)
    return QuotaExhaustedError(str(exc), reset_hint=reset)
