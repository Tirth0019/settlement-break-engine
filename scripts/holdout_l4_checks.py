"""§1.3 post-L4 assertions for hold-out seed 9999 (docs/FINAL_PLAN.md)."""
from __future__ import annotations

import sqlite3

SEED = "9999"
MAX_CALLS = 20


def _l3_verdict_map(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT a.break_id, a.new_value
          FROM audit_log a
          JOIN (
                SELECT break_id, MAX(audit_id) AS audit_id
                  FROM audit_log
                 WHERE who = 'l3_investigator' AND what = 'verdict'
                 GROUP BY break_id
               ) latest ON latest.audit_id = a.audit_id
          JOIN breaks b ON b.break_id = a.break_id
         WHERE b.seed = ?
        """,
        (SEED,),
    ).fetchall()
    return {bid: verdict for bid, verdict in rows if verdict}


def main() -> int:
    conn = sqlite3.connect(f"runs/sbe_{SEED}.db")
    conn.row_factory = sqlite3.Row
    l3 = _l3_verdict_map(conn)

    verified = conn.execute(
        """
        SELECT break_id, verdict, verifier_decision, verifier_reason,
               residual_unexplained
          FROM breaks
         WHERE seed = ? AND verifier_decision IS NOT NULL
        """,
        (SEED,),
    ).fetchall()
    n = len(verified)
    print(f"l4_calls n={n} max={MAX_CALLS} ok={n <= MAX_CALLS}")
    if n > MAX_CALLS:
        return 1

    abstention_blocks = [
        r
        for r in verified
        if r["verifier_decision"] == "ESCALATE"
        and r["verifier_reason"]
        and "Blocked OVERTURN to MATCH" in r["verifier_reason"]
    ]
    bad_overturn = [
        r
        for r in verified
        if r["verifier_decision"] == "OVERTURN"
        and l3.get(r["break_id"]) == "NEEDS_HUMAN"
        and r["verdict"] == "MATCH"
        and str(r["residual_unexplained"]).strip() not in ("0", "0.0", "0.00")
    ]
    print(f"abstention_guard_blocks n={len(abstention_blocks)}")
    print(f"bad_overturn_needs_human_to_match n={len(bad_overturn)}")
    if bad_overturn:
        for r in bad_overturn[:5]:
            print(f"  {r['break_id']} residual={r['residual_unexplained']}")
        return 1

    for r in verified:
        bid = r["break_id"]
        l3v = l3.get(bid)
        if l3v is None:
            continue
        if r["verifier_decision"] in ("UPHOLD", "ESCALATE") and r["verdict"] != l3v:
            print(f"L3 clobbered on {bid}: L3={l3v} break={r['verdict']} dec={r['verifier_decision']}")
            return 1
    print("l3_immutability OK (audit_log + UPHOLD/ESCALATE breaks.verdict)")

    print("L4 per-archetype:")
    for arch, dec, cnt in conn.execute(
        """
        SELECT COALESCE(ground_truth_archetype, 'UNKNOWN'), verifier_decision, COUNT(1)
          FROM breaks
         WHERE seed = ? AND verifier_decision IS NOT NULL
         GROUP BY 1, 2 ORDER BY 1, 2
        """,
        (SEED,),
    ):
        print(f"  {arch:28s} {dec:10s} {cnt}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
