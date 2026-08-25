"""
L2 — break ledger (BUILD_PLAN Phase 2, GATE 2 — the hardest engineering here,
not the agents. Build and test this before writing a single agent prompt).

Owns: persistent break_id allocation, ageing bucket computation, idempotent
re-runs, and late-arrival auto-close.

GATE 2 is a written test, not a manual check:
  - re-running the same date must produce byte-identical `breaks` table state
  - a break opened on day N must auto-close on day N+k when the late credit
    arrives, without creating a spurious second break
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sbe.money import ZERO, money

VALID_SIDES = {"BANK_ONLY", "LEDGER_ONLY", "SETTLEMENT_ONLY", "AMOUNT_MISMATCH"}


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _fmt_date(value) -> str:
    return _as_date(value).isoformat()


def ageing_bucket(age_days: int) -> str:
    """ARCHITECTURE.md §9.2 buckets: 0-2d / 3-7d / 8-30d / 30d+."""
    if age_days <= 2:
        return "0-2d"
    if age_days <= 7:
        return "3-7d"
    if age_days <= 30:
        return "8-30d"
    return "30d+"


def make_fingerprint(
    *,
    seed: str,
    merchant_id: str,
    side: str,
    amount_delta: Decimal,
    first_seen_run: str,
    match_key: str | None = None,
) -> str:
    """Deterministic natural key — same inputs always reopen the same break."""
    raw = "|".join(
        [
            seed,
            merchant_id,
            side,
            f"{money(amount_delta):.2f}",
            first_seen_run,
            match_key or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _next_break_id(conn: sqlite3.Connection, run_date) -> str:
    d = _as_date(run_date)
    # ARCHITECTURE example: BRK-2026-0318-0042
    prefix = f"BRK-{d.strftime('%Y')}-{d.strftime('%m%d')}-"
    row = conn.execute(
        "SELECT break_id FROM breaks WHERE break_id LIKE ? ORDER BY break_id DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    if row is None:
        seq = 1
    else:
        seq = int(str(row[0]).rsplit("-", 1)[-1]) + 1
    return f"{prefix}{seq:04d}"


def append_audit(
    conn: sqlite3.Connection,
    break_id: str,
    who: str,
    what: str,
    prior_value: str | None,
    new_value: str | None,
    at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (break_id, who, what, prior_value, new_value, at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (break_id, who, what, prior_value, new_value, at or datetime.utcnow().isoformat(timespec="seconds")),
    )


def open_break(
    conn: sqlite3.Connection,
    merchant_id: str,
    side: str,
    amount_delta: Decimal,
    run_date,
    *,
    seed: str = "1001",
    match_key: str | None = None,
    ground_truth_archetype: str | None = None,
) -> str:
    """Allocates a new break_id or returns the existing one for an idempotent re-run."""
    if side not in VALID_SIDES:
        raise ValueError(f"invalid side {side!r}; expected one of {sorted(VALID_SIDES)}")

    run_s = _fmt_date(run_date)
    delta = money(amount_delta)
    fp = make_fingerprint(
        seed=seed,
        merchant_id=merchant_id,
        side=side,
        amount_delta=delta,
        first_seen_run=run_s,
        match_key=match_key,
    )

    existing = conn.execute(
        "SELECT break_id, status FROM breaks WHERE seed = ? AND fingerprint = ?",
        (seed, fp),
    ).fetchone()
    if existing is not None:
        # Idempotent re-run: do not mutate; return the stable id.
        return existing[0]

    break_id = _next_break_id(conn, run_date)
    age = 0
    bucket = ageing_bucket(age)
    conn.execute(
        """
        INSERT INTO breaks (
            break_id, seed, fingerprint, first_seen_run, last_updated_run,
            status, merchant_id, side, amount_delta, match_key,
            age_days, ageing_bucket, residual_unexplained,
            ground_truth_archetype
        ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            break_id,
            seed,
            fp,
            run_s,
            run_s,
            merchant_id,
            side,
            f"{delta:.2f}",
            match_key,
            age,
            bucket,
            f"{abs(delta):.2f}",
            ground_truth_archetype,
        ),
    )
    append_audit(
        conn,
        break_id,
        who="l2_break_ledger",
        what="open_break",
        prior_value=None,
        new_value=json.dumps(
            {
                "status": "OPEN",
                "side": side,
                "amount_delta": f"{delta:.2f}",
                "match_key": match_key,
            }
        ),
        at=run_s,
    )
    conn.commit()
    return break_id


def age_breaks(conn: sqlite3.Connection, as_of_date, *, seed: str | None = None) -> None:
    """Recomputes age_days / ageing_bucket for all OPEN breaks as of a given run date."""
    as_of = _as_date(as_of_date)
    if seed is None:
        rows = conn.execute(
            "SELECT break_id, first_seen_run FROM breaks WHERE status = 'OPEN'"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT break_id, first_seen_run FROM breaks WHERE status = 'OPEN' AND seed = ?",
            (seed,),
        ).fetchall()

    for break_id, first_seen in rows:
        age = (as_of - _as_date(first_seen)).days
        if age < 0:
            age = 0
        bucket = ageing_bucket(age)
        conn.execute(
            """
            UPDATE breaks
               SET age_days = ?, ageing_bucket = ?, last_updated_run = ?
             WHERE break_id = ?
            """,
            (age, bucket, _fmt_date(as_of), break_id),
        )
    conn.commit()


def try_late_arrival_close(
    conn: sqlite3.Connection,
    incoming_record: dict,
    run_date,
) -> str | None:
    """Checks whether an incoming record closes an existing OPEN break instead
    of becoming a new one. Returns the closed break_id, or None.

    Matching precedence:
      1. same seed + merchant_id + match_key (UTR / synthetic)
      2. same seed + merchant_id + amount that exactly offsets amount_delta
         (bank credit of X closes a break with amount_delta == -X)
    """
    seed = incoming_record.get("seed", "1001")
    merchant_id = incoming_record["merchant_id"]
    amount = money(incoming_record["amount"])
    match_key = incoming_record.get("match_key")
    run_s = _fmt_date(run_date)

    candidate = None
    if match_key:
        candidate = conn.execute(
            """
            SELECT break_id, amount_delta, status, match_key
              FROM breaks
             WHERE seed = ? AND merchant_id = ? AND status = 'OPEN'
               AND match_key = ?
             ORDER BY first_seen_run ASC, break_id ASC
             LIMIT 1
            """,
            (seed, merchant_id, match_key),
        ).fetchone()

    if candidate is None:
        # Amount-offset match: credit fills a negative amount_delta gap.
        target_delta = money(-amount)
        candidate = conn.execute(
            """
            SELECT break_id, amount_delta, status, match_key
              FROM breaks
             WHERE seed = ? AND merchant_id = ? AND status = 'OPEN'
               AND amount_delta = ?
             ORDER BY first_seen_run ASC, break_id ASC
             LIMIT 1
            """,
            (seed, merchant_id, f"{target_delta:.2f}"),
        ).fetchone()

    if candidate is None:
        return None

    break_id = candidate[0]
    prior_status = candidate[2]
    conn.execute(
        """
        UPDATE breaks
           SET status = 'RESOLVED',
               last_updated_run = ?,
               residual_unexplained = '0.00',
               close_reason = 'late_arrival',
               verdict = COALESCE(verdict, 'MATCH')
         WHERE break_id = ?
        """,
        (run_s, break_id),
    )
    append_audit(
        conn,
        break_id,
        who="l2_break_ledger",
        what="late_arrival_close",
        prior_value=prior_status,
        new_value=json.dumps(
            {
                "status": "RESOLVED",
                "close_reason": "late_arrival",
                "incoming_amount": f"{amount:.2f}",
                "match_key": match_key,
                "run_date": run_s,
            }
        ),
        at=run_s,
    )
    conn.commit()
    return break_id


def breaks_snapshot(conn: sqlite3.Connection, seed: str) -> str:
    """Canonical serialization of breaks for a seed — used by idempotency checks."""
    rows = conn.execute(
        """
        SELECT break_id, seed, fingerprint, first_seen_run, last_updated_run,
               status, merchant_id, side, amount_delta, match_key,
               age_days, ageing_bucket, residual_unexplained,
               ground_truth_archetype, close_reason, verdict
          FROM breaks
         WHERE seed = ?
         ORDER BY break_id
        """,
        (seed,),
    ).fetchall()
    payload = [dict(zip(
        [
            "break_id", "seed", "fingerprint", "first_seen_run", "last_updated_run",
            "status", "merchant_id", "side", "amount_delta", "match_key",
            "age_days", "ageing_bucket", "residual_unexplained",
            "ground_truth_archetype", "close_reason", "verdict",
        ],
        row,
    )) for row in rows]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def count_breaks(conn: sqlite3.Connection, seed: str, status: str | None = None) -> int:
    if status is None:
        row = conn.execute("SELECT COUNT(*) FROM breaks WHERE seed = ?", (seed,)).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) FROM breaks WHERE seed = ? AND status = ?",
            (seed, status),
        ).fetchone()
    return int(row[0])


def ingest_day_breaks(
    conn: sqlite3.Connection,
    *,
    seed: str,
    run_date,
    break_specs: list[dict[str, Any]],
    late_arrivals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    One deterministic day pass:
      1. try late-arrival closes first (so we don't open a duplicate)
      2. open remaining specs
      3. age all OPEN breaks as of run_date
    """
    closed: list[str] = []
    for incoming in late_arrivals or []:
        rec = dict(incoming)
        rec.setdefault("seed", seed)
        closed_id = try_late_arrival_close(conn, rec, run_date)
        if closed_id:
            closed.append(closed_id)

    opened: list[str] = []
    for spec in break_specs:
        bid = open_break(
            conn,
            merchant_id=spec["merchant_id"],
            side=spec["side"],
            amount_delta=money(spec["amount_delta"]),
            run_date=run_date,
            seed=seed,
            match_key=spec.get("match_key"),
            ground_truth_archetype=spec.get("ground_truth_archetype"),
        )
        opened.append(bid)

    age_breaks(conn, run_date, seed=seed)
    return {"opened": opened, "closed": closed}


def write_off_break(
    conn: sqlite3.Connection,
    break_id: str,
    run_date,
    *,
    reason: str = "materiality",
) -> None:
    """Mark an OPEN break as WRITTEN_OFF (materiality path)."""
    run_s = _fmt_date(run_date)
    row = conn.execute(
        "SELECT status FROM breaks WHERE break_id = ?", (break_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown break_id {break_id}")
    prior = row[0]
    conn.execute(
        """
        UPDATE breaks
           SET status = 'WRITTEN_OFF',
               last_updated_run = ?,
               residual_unexplained = '0.00',
               close_reason = ?,
               verdict = COALESCE(verdict, 'MATCH')
         WHERE break_id = ?
        """,
        (run_s, reason, break_id),
    )
    append_audit(
        conn,
        break_id,
        who="l1_deterministic",
        what="materiality_write_off",
        prior_value=prior,
        new_value=json.dumps({"status": "WRITTEN_OFF", "reason": reason, "run_date": run_s}),
        at=run_s,
    )
    conn.commit()
