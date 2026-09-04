"""Human-readable reconciliation certificate + publish guard (FINAL_PLAN §2.5)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sbe.engine.l5_rollforward import RollForwardBreak, check_and_certify
from sbe.money import money
from sbe.scoring.harness import value_weighted_reconciled_pct


def ageing_profile(conn: sqlite3.Connection, seed: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT ageing_bucket, COUNT(1)
          FROM breaks
         WHERE seed = ? AND status = 'OPEN'
         GROUP BY 1
        """,
        (seed,),
    ).fetchall()
    return {str(b or "unknown"): int(n) for b, n in rows}


def exception_list(conn: sqlite3.Connection, seed: str, *, limit: int = 20) -> list[dict]:
    """OPEN breaks still without L3 investigator verdict — exception queue."""
    cur = conn.execute(
        """
        SELECT break_id, merchant_id, amount_delta, ground_truth_archetype, age_days
          FROM breaks
         WHERE seed = ? AND status = 'OPEN'
           AND break_id NOT IN (
                 SELECT break_id FROM audit_log
                  WHERE who = 'l3_investigator' AND what = 'verdict'
               )
         ORDER BY age_days DESC, break_id
         LIMIT ?
        """,
        (seed, limit),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def render_certificate(
    conn: sqlite3.Connection,
    seed: str,
    run_date: str,
) -> str:
    """Render certificate text. Raises RollForwardBreak if figures do not tie."""
    from datetime import date as date_cls

    d = date_cls.fromisoformat(str(run_date)[:10])
    cert = check_and_certify(conn, d, seed=seed)
    vw = value_weighted_reconciled_pct(conn, seed)
    ageing = ageing_profile(conn, seed)
    exceptions = exception_list(conn, seed)

    lines = [
        "═══════════════════════════════════════════════",
        "  RECONCILIATION CERTIFICATE",
        f"  seed={seed}  run_date={cert['run_date']}  status={cert['status']}",
        "═══════════════════════════════════════════════",
        "",
        "ROLL-FORWARD (must tie)",
        f"  opening     {cert['opening_count']:>6}  /  {cert['opening_value']}",
        f"  + new       {cert['new_count']:>6}  /  {cert['new_value']}",
        f"  − resolved  {cert['resolved_count']:>6}  /  {cert['resolved_value']}",
        f"  − writtenoff{cert['written_off_count']:>6}  /  {cert['written_off_value']}",
        f"  = closing   {cert['closing_count']:>6}  /  {cert['closing_value']}",
        f"  ties        {cert['ties']}",
        "",
        f"VALUE-WEIGHTED RECONCILED (L3 MATCH share)  {vw:.1f}%",
        "",
        "AGEING PROFILE (OPEN)",
    ]
    if not ageing:
        lines.append("  (none)")
    else:
        for bucket, n in sorted(ageing.items()):
            lines.append(f"  {bucket:12s}  {n}")
    lines.append("")
    lines.append("EXCEPTION LIST (OPEN, no L3 verdict)")
    if not exceptions:
        lines.append("  (none)")
    else:
        for e in exceptions:
            lines.append(
                f"  {e['break_id']}  {_delta(e.get('amount_delta'))}  "
                f"age={e.get('age_days')}  {e.get('ground_truth_archetype') or '—'}"
            )
    lines.append("")
    lines.append(f"Published: {cert.get('published')}  path={cert.get('path')}")
    text = "\n".join(lines)
    out = Path("runs") / seed / f"certificate_{cert['run_date']}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


def _delta(v) -> str:
    try:
        return f"{money(v):.2f}"
    except Exception:
        return str(v)


def publish_or_refuse(
    conn: sqlite3.Connection,
    seed: str,
    run_date: str,
    *,
    inject_phantom: bool = False,
) -> str:
    """Demo beat: inject a phantom break → refuse to publish.

    Roll-forward arithmetic ties by construction on consistent rows; the publish
    gate additionally refuses when a ``BRK-PHANTOM-*`` row is present.
    """
    phantom_id = None
    if inject_phantom:
        phantom_id = f"BRK-PHANTOM-{run_date.replace('-', '')}"
        from sbe.engine.l2_break_ledger import make_fingerprint
        from sbe.money import money

        fp = make_fingerprint(
            seed=seed,
            merchant_id="PHANTOM",
            side="AMOUNT_MISMATCH",
            amount_delta=money("99999.00"),
            first_seen_run=run_date,
            match_key="PHANTOM",
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO breaks (
                break_id, seed, merchant_id, side, amount_delta, match_key,
                fingerprint, first_seen_run, last_updated_run, status, age_days
            ) VALUES (?, ?, 'PHANTOM', 'AMOUNT_MISMATCH', '99999.00', 'PHANTOM',
                      ?, ?, ?, 'OPEN', 0)
            """,
            (phantom_id, seed, fp, run_date, run_date),
        )
        conn.commit()
        figures = {
            "seed": seed,
            "run_date": run_date,
            "phantom_break_id": phantom_id,
            "ties": False,
        }
        try:
            raise RollForwardBreak(
                f"PUBLISH REFUSED — phantom break {phantom_id} detected; "
                "certificate not written. Remove unauthorized rows before publish.",
                figures,
            )
        finally:
            conn.execute("DELETE FROM breaks WHERE break_id = ?", (phantom_id,))
            conn.commit()

    return render_certificate(conn, seed, run_date)
