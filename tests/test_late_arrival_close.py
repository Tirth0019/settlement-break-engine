"""GATE 2 — a break opened day N must auto-close on day N+k without a
spurious second break."""
from datetime import date, timedelta
from decimal import Decimal

from sbe.db.connection import get_connection
from sbe.engine.l2_break_ledger import (
    count_breaks,
    ingest_day_breaks,
    open_break,
    try_late_arrival_close,
)


SEED = "test-late-arrival"
DAY1 = date(2026, 3, 18)
DAY3 = DAY1 + timedelta(days=2)


def test_break_opened_day1_closes_day3_on_late_credit(tmp_path):
    db = tmp_path / "late.db"
    conn = get_connection(str(db))

    net = Decimal("8633.33")
    opened = open_break(
        conn,
        merchant_id="MERCH_0007",
        side="LEDGER_ONLY",
        amount_delta=-net,  # bank missing the T+2 credit
        run_date=DAY1,
        seed=SEED,
        match_key="UTR-T2-DEMO",
        ground_truth_archetype="T2_PERIOD_BOUNDARY",
    )
    assert count_breaks(conn, SEED, status="OPEN") == 1

    # Day 3: late bank credit arrives — must close the Day-1 break, not open another.
    closed = try_late_arrival_close(
        conn,
        {
            "seed": SEED,
            "merchant_id": "MERCH_0007",
            "amount": net,
            "match_key": "UTR-T2-DEMO",
        },
        DAY3,
    )
    assert closed == opened

    row = conn.execute(
        "SELECT status, close_reason, residual_unexplained, last_updated_run FROM breaks WHERE break_id = ?",
        (opened,),
    ).fetchone()
    assert row[0] == "RESOLVED"
    assert row[1] == "late_arrival"
    assert row[2] == "0.00"
    assert row[3] == DAY3.isoformat()

    assert count_breaks(conn, SEED) == 1  # no spurious second break
    assert count_breaks(conn, SEED, status="OPEN") == 0
    assert count_breaks(conn, SEED, status="RESOLVED") == 1
    conn.close()


def test_late_arrival_amount_match_without_key(tmp_path):
    db = tmp_path / "late_amt.db"
    conn = get_connection(str(db))
    hold = Decimal("1200.00")
    bid = open_break(
        conn,
        "MERCH_0009",
        "AMOUNT_MISMATCH",
        -hold,
        DAY1,
        seed=SEED,
        ground_truth_archetype="ROLLING_RESERVE_HOLD",
    )
    closed = try_late_arrival_close(
        conn,
        {"seed": SEED, "merchant_id": "MERCH_0009", "amount": hold},
        DAY3,
    )
    assert closed == bid
    assert count_breaks(conn, SEED) == 1
    conn.close()


def test_ingest_day_prefers_close_over_duplicate_open(tmp_path):
    db = tmp_path / "ingest_late.db"
    conn = get_connection(str(db))
    net = Decimal("5000.00")
    open_break(
        conn,
        "MERCH_0010",
        "LEDGER_ONLY",
        -net,
        DAY1,
        seed=SEED,
        match_key="UTR-INGEST",
        ground_truth_archetype="T2_PERIOD_BOUNDARY",
    )

    result = ingest_day_breaks(
        conn,
        seed=SEED,
        run_date=DAY3,
        break_specs=[],  # nothing new to open
        late_arrivals=[
            {
                "merchant_id": "MERCH_0010",
                "amount": net,
                "match_key": "UTR-INGEST",
            }
        ],
    )
    assert len(result["closed"]) == 1
    assert count_breaks(conn, SEED) == 1
    assert count_breaks(conn, SEED, status="RESOLVED") == 1

    # Ageing after close should leave RESOLVED alone; OPEN count stays 0
    row = conn.execute(
        "SELECT age_days, ageing_bucket FROM breaks WHERE match_key = ?",
        ("UTR-INGEST",),
    ).fetchone()
    assert row is not None
    conn.close()


def test_age_breaks_updates_bucket(tmp_path):
    from sbe.engine.l2_break_ledger import age_breaks

    db = tmp_path / "age.db"
    conn = get_connection(str(db))
    bid = open_break(
        conn, "MERCH_0011", "LEDGER_ONLY", Decimal("-10.00"), DAY1, seed=SEED, match_key="AGE"
    )
    age_breaks(conn, DAY1 + timedelta(days=5), seed=SEED)
    row = conn.execute(
        "SELECT age_days, ageing_bucket FROM breaks WHERE break_id = ?", (bid,)
    ).fetchone()
    assert row[0] == 5
    assert row[1] == "3-7d"
    conn.close()
