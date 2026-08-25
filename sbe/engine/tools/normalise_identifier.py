"""normalise_identifier tool — reconciles UTR vs UPI RRN namespaces and
truncated bank narrations back to a canonical transaction reference
(BUILD_PLAN archetype table: UTR_TRUNCATION, UPI_RRN_VS_UTR)."""
from __future__ import annotations

import re

_UTR_RE = re.compile(r"UTR\d{10,}", re.IGNORECASE)
_RRN_RE = re.compile(r"RRN\d{9,}", re.IGNORECASE)


def normalise(raw_identifier: str, source: str = "") -> str:
    text = (raw_identifier or "").strip().upper()
    if not text:
        return ""
    m = _UTR_RE.search(text)
    if m:
        return m.group(0).upper()
    m = _RRN_RE.search(text)
    if m:
        return m.group(0).upper()
    # Strip common prefixes / whitespace noise
    cleaned = re.sub(r"[^A-Z0-9]", "", text)
    return cleaned
