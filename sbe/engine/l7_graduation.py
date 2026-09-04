"""
L7 — rule graduation DETECTION only (BUILD_PLAN Tier 2 / Tier 3 cut).

Promotion workflow is out of scope. llm_calls_by_day chart is CUT — needs
multiple progressive runs; we have one hold-out freeze.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from sbe.scoring.harness import (
    is_l3_scored_break,
    join_breaks_to_ground_truth,
    l3_investigated_break_ids,
    l3_verdict_map,
)


@dataclass
class RuleProposal:
    proposal_id: str
    archetype: str
    pattern: str
    n: int
    identical_verdict: str
    zero_overturns: bool
    mean_confidence: float
    residual_ok: bool
    projected_l3_share_pct: float
    status: str = "DETECTION ONLY — promotion workflow not implemented"
    evidence_break_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "archetype": self.archetype,
            "pattern": self.pattern,
            "n": self.n,
            "identical_verdict": self.identical_verdict,
            "zero_overturns": self.zero_overturns,
            "mean_confidence": self.mean_confidence,
            "residual_ok": self.residual_ok,
            "projected_l3_share_pct": self.projected_l3_share_pct,
            "status": self.status,
            "evidence_break_ids": list(self.evidence_break_ids),
        }


_PATTERNS = {
    "FEE_PLUS_GST": "FEE_PLUS_GST — GST-on-fee omitted from merchant ledger",
    "TDS_194O": "TDS_194O — §194-O TDS on gross omitted from ledger",
    "CHARGEBACK_PLUS_FEE": "CHARGEBACK_PLUS_FEE — bank chargeback + fee not in ledger",
}


def detect_graduation_candidates(
    resolved_breaks: list,
    min_occurrences: int = 5,
) -> tuple[list[dict], list[dict]]:
    """Finds archetypes resolved identically at high confidence with zero overturns.

    ``resolved_breaks`` items need: archetype, verdict, confidence,
    residual_unexplained, verifier_decision (optional), break_id.
    Returns ``(proposals, declines)`` — proposals are NOT promotions.
    Declines explain why each high-n (or scored) archetype was refused.
    """
    by_arch: dict[str, list[dict]] = {}
    for r in resolved_breaks:
        arch = r.get("archetype") or r.get("ground_truth_archetype")
        if not arch:
            continue
        by_arch.setdefault(arch, []).append(r)

    out: list[dict] = []
    declines: list[dict] = []
    rp_i = 1
    total = max(1, len(resolved_breaks))
    for arch, rows in sorted(by_arch.items()):
        n = len(rows)
        if n < min_occurrences:
            declines.append(
                {
                    "archetype": arch,
                    "n": n,
                    "reason": f"below threshold (n={n} < min_occurrences={min_occurrences})",
                }
            )
            continue
        verdicts = {r.get("verdict") for r in rows}
        if len(verdicts) != 1 or next(iter(verdicts)) is None:
            declines.append(
                {
                    "archetype": arch,
                    "n": n,
                    "reason": (
                        f"L3 verdicts not identical "
                        f"({', '.join(sorted(str(v) for v in verdicts))})"
                    ),
                }
            )
            continue
        verdict = next(iter(verdicts))
        overturns = sum(1 for r in rows if r.get("verifier_decision") == "OVERTURN")
        if overturns:
            declines.append(
                {
                    "archetype": arch,
                    "n": n,
                    "reason": (
                        f"verifier OVERTURN on {overturns}/{n} "
                        f"— will not promote a pattern the auditor rejected"
                    ),
                }
            )
            continue  # never propose an archetype that the verifier overturned
        confs = [float(r.get("confidence") or 0.0) for r in rows]
        mean_c = sum(confs) / len(confs)
        if mean_c < 0.85:
            declines.append(
                {
                    "archetype": arch,
                    "n": n,
                    "reason": f"mean confidence {mean_c:.2f} < 0.85",
                }
            )
            continue
        residual_ok = all(
            str(r.get("residual_unexplained") or "").strip()
            in {"0", "0.0", "0.00", "0.000"}
            or r.get("residual_unexplained") is None
            for r in rows
            if r.get("verdict") == "MATCH"
        )
        if verdict == "MATCH" and not residual_ok:
            declines.append(
                {
                    "archetype": arch,
                    "n": n,
                    "reason": "MATCH rows with non-zero residual — contract incomplete",
                }
            )
            continue
        proposal = RuleProposal(
            proposal_id=f"RP-{rp_i:03d}",
            archetype=arch,
            pattern=_PATTERNS.get(arch, f"{arch} — identical L3 resolution"),
            n=len(rows),
            identical_verdict=verdict,
            zero_overturns=True,
            mean_confidence=mean_c,
            residual_ok=residual_ok if verdict == "MATCH" else True,
            projected_l3_share_pct=100.0 * len(rows) / total,
            evidence_break_ids=[r.get("break_id") for r in rows if r.get("break_id")],
        )
        out.append(proposal.as_dict())
        rp_i += 1
    return out, declines


def detect_graduation_from_db(
    conn: sqlite3.Connection,
    seed: str,
    *,
    min_occurrences: int = 5,
) -> tuple[list[dict], list[dict]]:
    """Load L3-scored rows from DB and run detection. Returns (proposals, declines)."""
    l3_ids = l3_investigated_break_ids(conn, seed)
    l3_map = l3_verdict_map(conn, seed)
    rows = []
    for r in join_breaks_to_ground_truth(conn, seed):
        if not is_l3_scored_break(r, l3_ids):
            continue
        rows.append(
            {
                "break_id": r["break_id"],
                "archetype": r.get("archetype"),
                "verdict": l3_map.get(r["break_id"]) or r.get("verdict"),
                "confidence": r.get("confidence"),
                "residual_unexplained": r.get("residual_unexplained"),
                "verifier_decision": r.get("verifier_decision"),
            }
        )
    return detect_graduation_candidates(rows, min_occurrences=min_occurrences)


def format_graduation_report(
    proposals: list[dict],
    declines: list[dict] | None = None,
) -> str:
    lines: list[str] = []
    if not proposals:
        lines.extend(
            [
                "RULE PROPOSALS: none",
                "Status: DETECTION ONLY — promotion workflow not implemented",
                "This is a reasoned refusal, not an empty stub:",
            ]
        )
    else:
        for p in proposals:
            lines.extend(
                [
                    f"RULE PROPOSAL {p['proposal_id']} · AWAITING APPROVAL",
                    f"Pattern:   {p['pattern']}",
                    f"Evidence:  {p['n']}/{p['n']} resolved identically "
                    f"({p['identical_verdict']}), zero overturns, "
                    f"mean confidence {p['mean_confidence']:.2f}",
                    f"Projected: ~{p['projected_l3_share_pct']:.0f}% of L3 volume "
                    f"on this seed → deterministic",
                    f"Status:    {p['status']}",
                    "",
                ]
            )
    if declines:
        lines.append("DECLINED (mechanism working):")
        for d in declines:
            lines.append(f"  {d['archetype']:28s} n={d['n']:<3}  {d['reason']}")
    elif not proposals:
        lines.append(
            "Note: no scored archetypes met the candidate bar "
            "(identical L3, high confidence, zero L4 overturns, n≥threshold)."
        )
    return "\n".join(lines).rstrip()


def llm_calls_by_day(conn) -> dict:
    """CUT — needs multiple runs with rules progressively removing L3 work."""
    return {
        "status": "CUT",
        "reason": (
            "llm_calls_by_day chart requires multiple progressive runs with "
            "graduated rules removing L3 volume. Agent is frozen with one "
            "hold-out run — chart not produced."
        ),
        "series": {},
    }
