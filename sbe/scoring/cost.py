"""Cost per resolved break — tokens and rupees (BUILD_PLAN Tier 2).

Token counts are estimated from audit_log call counts × configured tokens/call
when provider usage logs are absent. Report the estimate basis explicitly.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass


# Indicative free-tier / list prices (₹ per 1k tokens) — document assumptions.
DEFAULT_RUPEE_PER_1K = {
    "l3": float(os.getenv("COST_L3_INR_PER_1K", "0.05")),  # Groq-class
    "l4": float(os.getenv("COST_L4_INR_PER_1K", "0.15")),  # Gemini-class
}
DEFAULT_TOKENS_L3 = int(os.getenv("L3_TOKENS_PER_BREAK", "4000"))
DEFAULT_TOKENS_L4 = int(os.getenv("L4_TOKENS_PER_BREAK", "1000"))


@dataclass
class CostReport:
    seed: str
    l3_breaks: int
    l4_breaks: int
    l3_tokens_est: int
    l4_tokens_est: int
    l3_inr: float
    l4_inr: float
    inr_per_l3_break: float
    inr_per_l4_break: float
    basis: str

    @property
    def total_inr(self) -> float:
        return self.l3_inr + self.l4_inr


def cost_per_resolved_break(
    token_log: list,
    rupee_per_1k_tokens: dict,
) -> float:
    """Aggregate INR / break from an explicit token log.

    ``token_log`` items: ``{"layer": "l3"|"l4", "tokens": int}``.
    Empty log → 0.0 (no ZeroDivisionError).
    """
    if not token_log:
        return 0.0
    total_inr = 0.0
    for row in token_log:
        layer = str(row.get("layer") or "l3").lower()
        tokens = int(row.get("tokens") or 0)
        rate = float(rupee_per_1k_tokens.get(layer, rupee_per_1k_tokens.get("l3", 0.0)))
        total_inr += (tokens / 1000.0) * rate
    return total_inr / len(token_log)


def estimate_seed_cost(
    conn: sqlite3.Connection,
    seed: str,
    *,
    tokens_l3: int = DEFAULT_TOKENS_L3,
    tokens_l4: int = DEFAULT_TOKENS_L4,
    rupee_per_1k: dict | None = None,
) -> CostReport:
    """Estimate L3/L4 cost from investigator + verifier call counts in audit_log."""
    rates = rupee_per_1k or DEFAULT_RUPEE_PER_1K
    l3_n = conn.execute(
        """
        SELECT COUNT(DISTINCT break_id) FROM audit_log
         WHERE who = 'l3_investigator' AND what = 'verdict'
           AND break_id IN (SELECT break_id FROM breaks WHERE seed = ?)
        """,
        (seed,),
    ).fetchone()[0]
    l4_n = conn.execute(
        """
        SELECT COUNT(1) FROM breaks
         WHERE seed = ? AND verifier_decision IS NOT NULL
        """,
        (seed,),
    ).fetchone()[0]

    l3_tok = l3_n * tokens_l3
    l4_tok = l4_n * tokens_l4
    l3_inr = (l3_tok / 1000.0) * float(rates.get("l3", 0.0))
    l4_inr = (l4_tok / 1000.0) * float(rates.get("l4", 0.0))

    return CostReport(
        seed=seed,
        l3_breaks=l3_n,
        l4_breaks=l4_n,
        l3_tokens_est=l3_tok,
        l4_tokens_est=l4_tok,
        l3_inr=l3_inr,
        l4_inr=l4_inr,
        inr_per_l3_break=(l3_inr / l3_n) if l3_n else 0.0,
        inr_per_l4_break=(l4_inr / l4_n) if l4_n else 0.0,
        basis=(
            f"estimate: {tokens_l3} tok/L3 x {l3_n}, {tokens_l4} tok/L4 x {l4_n}; "
            f"INR/1k L3={rates.get('l3')} L4={rates.get('l4')} "
            "(no provider usage log - reconcile +/-5% when available)"
        ),
    )


def format_cost_report(r: CostReport) -> str:
    return "\n".join(
        [
            f"cost seed={r.seed}",
            f"  L3 breaks={r.l3_breaks} tokens~{r.l3_tokens_est:,} "
            f"INR {r.l3_inr:.4f} (INR {r.inr_per_l3_break:.4f}/break)",
            f"  L4 breaks={r.l4_breaks} tokens~{r.l4_tokens_est:,} "
            f"INR {r.l4_inr:.4f} (INR {r.inr_per_l4_break:.4f}/break)",
            f"  total INR {r.total_inr:.4f}",
            f"  basis: {r.basis}",
        ]
    )
