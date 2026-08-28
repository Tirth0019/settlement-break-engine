"""normalise_identifier tool — reconciles UTR vs UPI RRN namespaces and
truncated bank narrations back to a canonical transaction reference
(BUILD_PLAN archetype table: UTR_TRUNCATION, UPI_RRN_VS_UTR)."""
from __future__ import annotations

import re

_UTR_RE = re.compile(r"UTR\d{10,}", re.IGNORECASE)
_RRN_RE = re.compile(r"RRN\d{9,}", re.IGNORECASE)
# Looser patterns for bank narrations chopped mid-reference (HDFC 16-char cap).
_UTR_LOOSE = re.compile(r"UTR\d{6,}", re.IGNORECASE)
_RRN_LOOSE = re.compile(r"RRN\d{6,}", re.IGNORECASE)

_MIN_PREFIX = 10  # chars incl. UTR/RRN prefix — avoid spurious short overlaps


def _extract_token(text: str) -> str:
    text = (text or "").strip().upper()
    if not text:
        return ""
    for pat in (_UTR_RE, _RRN_RE, _UTR_LOOSE, _RRN_LOOSE):
        m = pat.search(text)
        if m:
            return m.group(0).upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def normalise(raw_identifier: str, source: str = "") -> str:
    del source  # reserved for source-specific rules (UPI vs NEFT namespaces)
    return _extract_token(raw_identifier)


def identifiers_compatible(a: str, b: str) -> bool:
    """True when two strings likely refer to the same txn (truncation-safe)."""
    ta = _extract_token(a)
    tb = _extract_token(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short) >= _MIN_PREFIX and long.startswith(short):
        return True
    # Compare numeric cores after UTR/RRN prefix (handles NEFT-prefixed narrations).
    def _core(token: str) -> str:
        for prefix in ("UTR", "RRN"):
            if token.startswith(prefix):
                return token[len(prefix) :]
        return token

    ca, cb = _core(ta), _core(tb)
    if ca and cb:
        s, lng = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
        if len(s) >= 6 and lng.startswith(s):
            return True
    return False
