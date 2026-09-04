"""
L6 — break packets + proposed journal entries (BUILD_PLAN Tier 1/2).

Output is a copy-pasteable analyst artifact (ARCHITECTURE.md §11), not a
verdict blob. residual_unexplained must render to the paise.

Maker-checker: this module only ever proposes a JE into an approval queue.
Nothing here posts to a ledger.
"""
from __future__ import annotations

import json
import re
from datetime import date


_PANISH = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_CARDISH = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def _mask_secrets(text: str) -> str:
    text = _PANISH.sub("[PAN_REDACTED]", text)
    text = _CARDISH.sub("[CARD_REDACTED]", text)
    return text


def _fmt_inr(amount) -> str:
    try:
        v = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    sign = "-" if v < 0 else ""
    return f"{sign}₹{abs(v):,.2f}"


def render_break_packet(break_record: dict) -> str:
    """Render a copy-pasteable packet. MASKS PAN/card-like tokens."""
    bid = break_record.get("break_id") or "BRK-UNKNOWN"
    delta = break_record.get("amount_delta") or "0.00"
    age = break_record.get("age_days")
    age_s = f"{age}d" if age is not None else "?"
    mid = break_record.get("merchant_id") or "MERCH_?"
    verdict = break_record.get("verdict") or "OPEN"
    residual = break_record.get("residual_unexplained")
    if residual is None:
        residual = "n/a"
    hypothesis = (break_record.get("hypothesis") or "").strip()
    confidence = break_record.get("confidence")
    verifier = break_record.get("verifier_decision")
    arch = break_record.get("ground_truth_archetype") or break_record.get("archetype")

    lines = [
        f"{bid}  ·  {_fmt_inr(delta)}  ·  Aged {age_s}  ·  {mid}",
    ]
    if arch:
        lines.append(f"ARCHETYPE  {arch}")
    lines.append("")
    lines.append("HYPOTHESIS")
    if hypothesis:
        lines.append(hypothesis)
    else:
        lines.append(
            "(none — gap not explained; escalate with source excerpts below)"
        )
    lines.append("")
    lines.append("EVIDENCE")
    evidence = break_record.get("evidence")
    if evidence is None and break_record.get("evidence_json"):
        try:
            evidence = json.loads(break_record["evidence_json"])
        except json.JSONDecodeError:
            evidence = []
    evidence = evidence or []
    if not evidence:
        lines.append("  (no structured evidence rows)")
    else:
        for e in evidence:
            if isinstance(e, dict):
                src = e.get("source") or e.get("tool") or "?"
                ref = e.get("ref") or e.get("row") or ""
                val = e.get("value") or e.get("amount") or ""
                note = e.get("note") or e.get("detail") or ""
                lines.append(f"  {src} {ref}  {val}  {note}".rstrip())
            else:
                lines.append(f"  {e}")

    lines.append("")
    lines.append(f"RESIDUAL UNEXPLAINED   {_fmt_inr(residual) if residual != 'n/a' else residual}")
    lines.append("")
    lines.append("ASK")
    if verdict == "MATCH":
        lines.append("No open ask — gap closed to the paise.")
    elif verdict == "NEEDS_HUMAN":
        lines.append(
            "Human review required: confirm whether the shortfall is a true "
            "leakage, delayed credit, or mis-keyed fee component."
        )
    else:
        lines.append("Confirm source completeness before closing.")

    conf_s = f"{float(confidence):.2f}" if confidence is not None else "n/a"
    ver_s = verifier or "NOT_VERIFIED"
    lines.append("")
    lines.append(f"CONFIDENCE {conf_s}   VERIFIER {ver_s}   VERDICT {verdict}")

    je = propose_journal_entry(break_record)
    lines.append(
        f"PROPOSED JE  {je['je_id']} ({je['status']}) — maker only; checker required"
    )
    return _mask_secrets("\n".join(lines))


def propose_journal_entry(break_record: dict) -> dict:
    """Returns a JE dict in PENDING_APPROVAL. Never auto-posts."""
    bid = break_record.get("break_id") or "UNKNOWN"
    delta = break_record.get("amount_delta") or "0.00"
    mid = break_record.get("merchant_id") or ""
    today = date.today().isoformat().replace("-", "")
    return {
        "je_id": f"JE-{today}-{bid[-4:]}",
        "status": "PENDING_APPROVAL",
        "break_id": bid,
        "merchant_id": mid,
        "dr": "Settlement suspense",
        "cr": "Bank clearing",
        "amount": str(delta).lstrip("-"),
        "narration": f"Proposed recon JE for {bid} — awaiting checker",
        "auto_post": False,
    }
