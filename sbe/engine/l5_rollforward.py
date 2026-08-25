"""
L5 — roll-forward + Reconciliation Certificate (BUILD_PLAN Phase 4, GATE 4).

THE control. Build this before the agents, not after — it will catch
generator and ledger bugs for the rest of the build (ROADMAP.md Day 4-5).

opening + new - resolved - written_off == closing, in BOTH count and value.
If it does not tie, the run refuses to publish and raises ROLL_FORWARD_BREAK
with the exact figures, not just "reconciliation failed".
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sbe.money import ZERO, money, ties


class RollForwardBreak(Exception):
    """Raised when the roll-forward does not tie — run must not publish."""

    def __init__(self, message: str, figures: dict):
        super().__init__(message)
        self.figures = figures


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _fmt_date(value) -> str:
    return _as_date(value).isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _abs_delta(row) -> Decimal:
    return abs(money(row["amount_delta"] if isinstance(row, dict) else row[0]))


def compute_rollforward(conn: sqlite3.Connection, run_date, *, seed: str) -> dict:
    """Compute opening/new/resolved/written_off/closing for one run date."""
    run_s = _fmt_date(run_date)
    rows = conn.execute(
        """
        SELECT break_id, first_seen_run, last_updated_run, status, amount_delta
          FROM breaks
         WHERE seed = ?
        """,
        (seed,),
    ).fetchall()

    opening_c = opening_v = ZERO
    new_c = new_v = ZERO
    resolved_c = resolved_v = ZERO
    written_c = written_v = ZERO
    closing_c = closing_v = ZERO

    # Use Decimal counters for counts too via money() so ties() works uniformly.
    opening_count = new_count = resolved_count = written_count = closing_count = 0

    for row in rows:
        break_id, first_seen, last_updated, status, amount_delta = row
        val = abs(money(amount_delta))
        first = str(first_seen)
        last = str(last_updated)

        is_new = first == run_s
        closed_today = last == run_s and status in {"RESOLVED", "WRITTEN_OFF"}
        open_now = status == "OPEN"

        # Was open at start of day?
        open_at_start = (first < run_s) and (open_now or closed_today)

        if open_at_start:
            opening_count += 1
            opening_v += val
        if is_new:
            new_count += 1
            new_v += val
        if closed_today and status == "RESOLVED":
            resolved_count += 1
            resolved_v += val
        if closed_today and status == "WRITTEN_OFF":
            written_count += 1
            written_v += val
        if open_now:
            closing_count += 1
            closing_v += val

    count_ties = ties(opening_count, new_count, resolved_count, written_count, closing_count)
    value_ties = ties(opening_v, new_v, resolved_v, written_v, closing_v)

    return {
        "seed": seed,
        "run_date": run_s,
        "opening_count": opening_count,
        "opening_value": f"{money(opening_v):.2f}",
        "new_count": new_count,
        "new_value": f"{money(new_v):.2f}",
        "resolved_count": resolved_count,
        "resolved_value": f"{money(resolved_v):.2f}",
        "written_off_count": written_count,
        "written_off_value": f"{money(written_v):.2f}",
        "closing_count": closing_count,
        "closing_value": f"{money(closing_v):.2f}",
        "count_ties": count_ties,
        "value_ties": value_ties,
        "ties": count_ties and value_ties,
    }


def check_and_certify(conn: sqlite3.Connection, run_date, *, seed: str = "1001") -> dict:
    """Returns the certificate dict if it ties; raises RollForwardBreak if not."""
    figures = compute_rollforward(conn, run_date, seed=seed)
    run_s = figures["run_date"]
    run_id = f"{seed}:{run_s}"
    created_at = _now_iso()

    if not figures["ties"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, seed, run_date,
                opening_count, opening_value, new_count, new_value,
                resolved_count, resolved_value, written_off_count, written_off_value,
                closing_count, closing_value, ties, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                run_id,
                seed,
                run_s,
                figures["opening_count"],
                figures["opening_value"],
                figures["new_count"],
                figures["new_value"],
                figures["resolved_count"],
                figures["resolved_value"],
                figures["written_off_count"],
                figures["written_off_value"],
                figures["closing_count"],
                figures["closing_value"],
                created_at,
            ),
        )
        conn.commit()
        raise RollForwardBreak(
            f"ROLL_FORWARD_BREAK seed={seed} run_date={run_s} "
            f"count_ties={figures['count_ties']} value_ties={figures['value_ties']} "
            f"opening={figures['opening_count']}/{figures['opening_value']} "
            f"new={figures['new_count']}/{figures['new_value']} "
            f"resolved={figures['resolved_count']}/{figures['resolved_value']} "
            f"written_off={figures['written_off_count']}/{figures['written_off_value']} "
            f"closing={figures['closing_count']}/{figures['closing_value']}",
            figures,
        )

    conn.execute(
        """
        INSERT OR REPLACE INTO runs (
            run_id, seed, run_date,
            opening_count, opening_value, new_count, new_value,
            resolved_count, resolved_value, written_off_count, written_off_value,
            closing_count, closing_value, ties, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            run_id,
            seed,
            run_s,
            figures["opening_count"],
            figures["opening_value"],
            figures["new_count"],
            figures["new_value"],
            figures["resolved_count"],
            figures["resolved_value"],
            figures["written_off_count"],
            figures["written_off_value"],
            figures["closing_count"],
            figures["closing_value"],
            created_at,
        ),
    )
    conn.commit()

    certificate = {
        **figures,
        "run_id": run_id,
        "title": "Reconciliation Certificate",
        "control": "opening + new - resolved - written_off = closing",
        "status": "TIED",
        "published": True,
        "created_at": created_at,
    }

    out_dir = Path("runs") / seed
    out_dir.mkdir(parents=True, exist_ok=True)
    cert_path = out_dir / f"certificate_{run_s}.json"
    cert_path.write_text(json.dumps(certificate, indent=2), encoding="utf-8")
    certificate["path"] = str(cert_path)
    return certificate
