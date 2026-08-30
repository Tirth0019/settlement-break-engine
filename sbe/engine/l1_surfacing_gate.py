"""Gate 3b — L1 must surface what the generator injects (BUILD_PLAN gap found Aug 29)."""
from __future__ import annotations

import sqlite3

from sbe.scoring.harness import join_breaks_to_ground_truth, load_ground_truth


def _injected_archetypes(seed: str) -> set[str]:
    return {
        g["archetype"]
        for g in load_ground_truth(seed)
        if g.get("archetype") and g["archetype"] != "CLEAN"
    }


def check_l1_surfacing(conn: sqlite3.Connection, seed: str) -> dict:
    """Two assertions: injected archetypes -> OPEN break; OPEN breaks -> label."""
    injected = _injected_archetypes(seed)
    joined = join_breaks_to_ground_truth(conn, seed)

    open_rows = [r for r in joined if r.get("status") == "OPEN"]
    open_by_arch: set[str] = set()
    open_unlabeled: list[str] = []
    for r in open_rows:
        arch = r.get("archetype") or "UNKNOWN"
        if arch == "UNKNOWN" or not r.get("ground_truth_archetype"):
            open_unlabeled.append(r["break_id"])
        elif arch != "UNKNOWN":
            open_by_arch.add(arch)

    missing_archetypes = sorted(injected - open_by_arch)
    ok = not missing_archetypes and not open_unlabeled
    return {
        "ok": ok,
        "injected_archetypes": len(injected),
        "open_archetypes": len(open_by_arch),
        "missing_archetypes": missing_archetypes,
        "open_unlabeled_count": len(open_unlabeled),
        "open_unlabeled_sample": open_unlabeled[:10],
    }


def format_surfacing_report(result: dict) -> str:
    lines = [
        f"surfacing_gate ok={result['ok']} "
        f"injected={result['injected_archetypes']} open_archetypes={result['open_archetypes']}",
    ]
    if result["missing_archetypes"]:
        n = len(result["missing_archetypes"])
        preview = ", ".join(result["missing_archetypes"][:15])
        lines.append(f"MISSING OPEN breaks for {n} archetype(s): {preview}")
    if result["open_unlabeled_count"]:
        lines.append(
            f"OPEN unlabeled: {result['open_unlabeled_count']} "
            f"sample={result['open_unlabeled_sample']}"
        )
    return "\n".join(lines)
