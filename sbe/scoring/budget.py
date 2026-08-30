"""L3 token budget estimation before a full investigate run."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from sbe.scoring.harness import (
    GATE5_CORE_ARITHMETIC,
    SMOKE_ARCHETYPE_ORDER,
    join_breaks_to_ground_truth,
    l3_investigated_break_ids,
)


@dataclass
class InvestigateBudget:
    seed: str
    open_eligible: int
    already_l3: int
    tokens_per_break: int
    tpd_limit: int
    estimated_tokens_full: int
    estimated_tokens_smoke: int
    max_breaks_one_day: int
    fits_full_run: bool
    smoke_archetypes_available: dict[str, int]
    recommendation: str


def _eligible_open(conn: sqlite3.Connection, seed: str) -> list[dict]:
    l3_ids = l3_investigated_break_ids(conn, seed)
    rows = join_breaks_to_ground_truth(conn, seed)
    return [
        r
        for r in rows
        if r.get("status") == "OPEN"
        and r.get("verdict") is None
        and r.get("close_reason") not in {"late_arrival", "materiality"}
        and r.get("break_id") not in l3_ids
    ]


def estimate_investigate_budget(
    conn: sqlite3.Connection,
    seed: str,
    *,
    tokens_per_break: int | None = None,
    tpd_limit: int | None = None,
) -> InvestigateBudget:
    """Compare OPEN break count × tokens/break against daily TPD before launching."""
    tpb = tokens_per_break or int(os.getenv("L3_TOKENS_PER_BREAK", "4000"))
    tpd = tpd_limit or int(os.getenv("GROQ_TPD_LIMIT", "200000"))

    eligible = _eligible_open(conn, seed)
    l3_n = len(l3_investigated_break_ids(conn, seed))
    open_n = len(eligible)
    est_full = open_n * tpb
    est_smoke = len(SMOKE_ARCHETYPE_ORDER) * tpb
    max_day = tpd // tpb if tpb else 0
    fits = est_full <= tpd

    by_arch: dict[str, int] = {}
    for r in eligible:
        arch = r.get("archetype") or "UNKNOWN"
        by_arch[arch] = by_arch.get(arch, 0) + 1
    smoke_avail = {a: by_arch.get(a, 0) for a in SMOKE_ARCHETYPE_ORDER}

    if open_n == 0:
        rec = "No eligible OPEN breaks — run pipeline first or all already L3-scored."
    elif fits:
        rec = (
            f"Full run ({open_n} breaks x ~{tpb} tok ~ {est_full:,}) fits TPD {tpd:,}. "
            "Still run `--smoke` first to validate wiring."
        )
    else:
        rec = (
            f"Full run ({open_n} x ~{tpb} ~ {est_full:,}) exceeds TPD {tpd:,}. "
            f"Max ~{max_day} breaks/day - use stratified subsample "
            f"(cap={max_day}) and report per-archetype n honestly."
        )
        missing_core = [a for a in GATE5_CORE_ARITHMETIC if smoke_avail.get(a, 0) == 0]
        if missing_core:
            rec += f" Core trio missing in pool: {', '.join(missing_core)}."

    return InvestigateBudget(
        seed=seed,
        open_eligible=open_n,
        already_l3=l3_n,
        tokens_per_break=tpb,
        tpd_limit=tpd,
        estimated_tokens_full=est_full,
        estimated_tokens_smoke=est_smoke,
        max_breaks_one_day=max_day,
        fits_full_run=fits,
        smoke_archetypes_available=smoke_avail,
        recommendation=rec,
    )


def format_budget_report(b: InvestigateBudget) -> str:
    lines = [
        f"seed={b.seed} open_eligible={b.open_eligible} already_l3={b.already_l3}",
        f"tokens_per_break~{b.tokens_per_break} tpd_limit={b.tpd_limit:,}",
        f"smoke (~{len(SMOKE_ARCHETYPE_ORDER)} breaks)~{b.estimated_tokens_smoke:,} tok",
        f"full run~{b.estimated_tokens_full:,} tok fits_tpd={b.fits_full_run} "
        f"max_breaks/day~{b.max_breaks_one_day}",
        "smoke pool: "
        + ", ".join(f"{a}={b.smoke_archetypes_available.get(a, 0)}" for a in SMOKE_ARCHETYPE_ORDER),
        b.recommendation,
    ]
    return "\n".join(lines)
