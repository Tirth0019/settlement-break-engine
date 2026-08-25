"""GATE 2 — the hardest engineering in the project. Written test, not a
manual check, per BUILD_PLAN explicitly."""
from datetime import date
from decimal import Decimal

from sbe.db.connection import get_connection
from sbe.engine.l2_break_ledger import (
    breaks_snapshot,
    count_breaks,
    ingest_day_breaks,
    open_break,
)


DAY1 = date(2026, 3, 18)
SEED = "test-idempotency"


def _day1_specs():
    return [
        {
            "merchant_id": "MERCH_0001",
            "side": "LEDGER_ONLY",
            "amount_delta": Decimal("-1000.00"),
            "match_key": "UTR111",
            "ground_truth_archetype": "T2_PERIOD_BOUNDARY",
        },
        {
            "merchant_id": "MERCH_0002",
            "side": "AMOUNT_MISMATCH",
            "amount_delta": Decimal("-31.83"),
            "match_key": "UTR222",
            "ground_truth_archetype": "FEE_PLUS_GST",
        },
        {
            "merchant_id": "MERCH_0003",
            "side": "BANK_ONLY",
            "amount_delta": Decimal("-12472.00"),
            "match_key": None,
            "ground_truth_archetype": "CHARGEBACK_PLUS_FEE",
        },
    ]


def test_rerun_same_day_is_byte_identical(tmp_path):
    db = tmp_path / "idem.db"
    conn = get_connection(str(db))

    ingest_day_breaks(conn, seed=SEED, run_date=DAY1, break_specs=_day1_specs())
    snap1 = breaks_snapshot(conn, SEED)
    ids1 = [
        open_break(
            conn,
            s["merchant_id"],
            s["side"],
            s["amount_delta"],
            DAY1,
            seed=SEED,
            match_key=s["match_key"],
            ground_truth_archetype=s["ground_truth_archetype"],
        )
        for s in _day1_specs()
    ]
    assert count_breaks(conn, SEED) == 3

    # Full day re-ingest must not create duplicates or change serialized state.
    ingest_day_breaks(conn, seed=SEED, run_date=DAY1, break_specs=_day1_specs())
    snap2 = breaks_snapshot(conn, SEED)
    ids2 = [
        open_break(
            conn,
            s["merchant_id"],
            s["side"],
            s["amount_delta"],
            DAY1,
            seed=SEED,
            match_key=s["match_key"],
            ground_truth_archetype=s["ground_truth_archetype"],
        )
        for s in _day1_specs()
    ]

    assert ids1 == ids2
    assert snap1 == snap2
    assert count_breaks(conn, SEED) == 3
    conn.close()


def test_open_break_returns_stable_id_on_rerun(tmp_path):
    db = tmp_path / "stable.db"
    conn = get_connection(str(db))
    a = open_break(
        conn, "MERCH_0001", "LEDGER_ONLY", Decimal("-500.00"), DAY1, seed=SEED, match_key="K1"
    )
    b = open_break(
        conn, "MERCH_0001", "LEDGER_ONLY", Decimal("-500.00"), DAY1, seed=SEED, match_key="K1"
    )
    assert a == b
    assert a.startswith("BRK-2026-0318-")
    assert count_breaks(conn, SEED) == 1
    conn.close()
