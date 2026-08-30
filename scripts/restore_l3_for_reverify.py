"""Restore L3 verdicts from audit_log and clear L4 fields for re-verify after precompute fix."""
from __future__ import annotations

import sqlite3
import sys

from sbe.scoring.harness import l3_investigated_break_ids


def main(seed: str = "2001") -> None:
    path = f"runs/sbe_{seed}.db"
    conn = sqlite3.connect(path)
    l3_ids = l3_investigated_break_ids(conn, seed)
    restored = 0
    for bid in l3_ids:
        row = conn.execute(
            """
            SELECT new_value FROM audit_log
             WHERE break_id = ? AND who = 'l3_investigator' AND what = 'verdict'
             ORDER BY at DESC LIMIT 1
            """,
            (bid,),
        ).fetchone()
        if not row:
            continue
        l3_verdict = row[0]
        conn.execute(
            """
            UPDATE breaks
               SET verdict = ?,
                   verifier_decision = NULL,
                   verifier_reason = NULL,
                   verifier_model = NULL
             WHERE break_id = ? AND seed = ?
            """,
            (l3_verdict, bid, seed),
        )
        restored += 1
    conn.commit()
    print(f"restored_l3_and_cleared_l4 n={restored} seed={seed}")
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2001")
