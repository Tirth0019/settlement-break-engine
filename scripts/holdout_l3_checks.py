"""§1.2 post-L3 assertions for hold-out seed 9999 (docs/FINAL_PLAN.md)."""
from __future__ import annotations

import sqlite3
import sys

SEED = "9999"


def main() -> int:
    conn = sqlite3.connect(f"runs/sbe_{SEED}.db")
    conn.row_factory = sqlite3.Row

    # Checkpoint: audit_log L3 verdict == breaks.verdict
    rows = conn.execute(
        """
        SELECT a.break_id, a.new_value AS audit_verdict, b.verdict AS break_verdict
          FROM audit_log a
          JOIN breaks b ON b.break_id = a.break_id AND b.seed = ?
         WHERE a.who = 'l3_investigator' AND a.what = 'verdict'
        """,
        (SEED,),
    ).fetchall()
    mismatches = [r for r in rows if r["audit_verdict"] != r["break_verdict"]]
    print(f"checkpoint audit_vs_breaks n={len(rows)} mismatches={len(mismatches)}")
    if mismatches:
        for r in mismatches[:5]:
            print(f"  MISMATCH {r['break_id']}: audit={r['audit_verdict']} break={r['break_verdict']}")
        return 1

    # Hard assertion: MATCH with residual != 0.00
    bad = conn.execute(
        """
        SELECT break_id, verdict, residual_unexplained
          FROM breaks
         WHERE seed = ? AND verdict = 'MATCH'
           AND residual_unexplained IS NOT NULL
           AND TRIM(residual_unexplained) NOT IN ('0', '0.0', '0.00', '0.000')
        """,
        (SEED,),
    ).fetchall()
    print(f"match_residual_violations n={len(bad)}")
    if bad:
        for r in bad:
            print(f"  {r['break_id']} residual={r['residual_unexplained']}")
        return 1

    # Per-archetype n (L3 verdicted)
    print("L3 per-archetype:")
    for arch, verdict, n in conn.execute(
        """
        SELECT COALESCE(ground_truth_archetype, 'UNKNOWN'), verdict, COUNT(1)
          FROM breaks
         WHERE seed = ? AND break_id IN (
               SELECT break_id FROM audit_log
                WHERE who = 'l3_investigator' AND what = 'verdict'
             )
         GROUP BY 1, 2
         ORDER BY 1, 2
        """,
        (SEED,),
    ):
        print(f"  {arch:28s} {verdict:12s} {n}")

    total = conn.execute(
        """
        SELECT COUNT(DISTINCT break_id) FROM audit_log
         WHERE who = 'l3_investigator' AND what = 'verdict'
           AND break_id IN (SELECT break_id FROM breaks WHERE seed = ?)
        """,
        (SEED,),
    ).fetchone()[0]
    eligible = conn.execute(
        """
        SELECT COUNT(1) FROM breaks
         WHERE seed = ? AND status = 'OPEN' AND verdict IS NULL
        """,
        (SEED,),
    ).fetchone()[0]
    print(f"L3 total={total} OPEN remaining without verdict={eligible}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
