"""GATE 4 — with L1 only, no agents, roll-forward must tie across a 10-day run."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from sbe.db.connection import get_connection
from sbe.engine.l2_break_ledger import open_break, try_late_arrival_close, write_off_break
from sbe.engine.l5_rollforward import RollForwardBreak, check_and_certify, compute_rollforward
from sbe.money import ties


SEED = "test-rollforward"
START = date(2026, 3, 10)


def test_rollforward_ties_l1_only_ten_day_run(tmp_path):
    db = tmp_path / "rf.db"
    conn = get_connection(str(db))

    # Seed a carry-forward open from a synthetic "day 0" so day 1 has a non-zero opening.
    prior = START - timedelta(days=1)
    open_break(
        conn,
        "MERCH_0001",
        "LEDGER_ONLY",
        Decimal("-2500.00"),
        prior,
        seed=SEED,
        match_key="PRIOR-UTR",
        ground_truth_archetype="T2_PERIOD_BOUNDARY",
    )

    for i in range(10):
        run_date = START + timedelta(days=i)

        # Late credit closes the prior open on day 1 (and only then).
        if i == 0:
            closed = try_late_arrival_close(
                conn,
                {
                    "seed": SEED,
                    "merchant_id": "MERCH_0001",
                    "amount": Decimal("2500.00"),
                    "match_key": "PRIOR-UTR",
                },
                run_date,
            )
            assert closed is not None

        # New residual each day
        open_break(
            conn,
            f"MERCH_{i+2:04d}",
            "AMOUNT_MISMATCH",
            Decimal(f"-{100 + i}.50"),
            run_date,
            seed=SEED,
            match_key=f"DAY-{i}",
            ground_truth_archetype="FEE_PLUS_GST",
        )

        # Materiality write-off every other day
        if i % 2 == 0:
            tiny = open_break(
                conn,
                f"MERCH_{50+i:04d}",
                "BANK_ONLY",
                Decimal("0.50"),
                run_date,
                seed=SEED,
                match_key=f"TINY-{i}",
                ground_truth_archetype="MATERIALITY",
            )
            write_off_break(conn, tiny, run_date, reason="materiality")

        # Resolve one older open (not same-day) starting day 3
        if i >= 2:
            older_key = f"DAY-{i-2}"
            row = conn.execute(
                "SELECT break_id, amount_delta, merchant_id FROM breaks "
                "WHERE seed=? AND match_key=? AND status='OPEN'",
                (SEED, older_key),
            ).fetchone()
            if row:
                try_late_arrival_close(
                    conn,
                    {
                        "seed": SEED,
                        "merchant_id": row[2],
                        "amount": abs(Decimal(row[1])),
                        "match_key": older_key,
                    },
                    run_date,
                )

        cert = check_and_certify(conn, run_date, seed=SEED)
        assert cert["ties"] is True
        assert cert["status"] == "TIED"
        assert ties(
            cert["opening_count"],
            cert["new_count"],
            cert["resolved_count"],
            cert["written_off_count"],
            cert["closing_count"],
        )
        assert ties(
            cert["opening_value"],
            cert["new_value"],
            cert["resolved_value"],
            cert["written_off_value"],
            cert["closing_value"],
        )

    # 10 certificates published
    run_rows = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE seed=? AND ties=1", (SEED,)
    ).fetchone()[0]
    assert run_rows == 10
    conn.close()


def test_rollforward_break_raises_with_figures(tmp_path):
    db = tmp_path / "rf_break.db"
    conn = get_connection(str(db))
    # Manually poison the ledger: insert a closing open without counting it as new
    # by opening on day1 then corrupting first_seen — easier: call compute and force fail
    open_break(
        conn, "MERCH_0001", "LEDGER_ONLY", Decimal("-10.00"), START, seed=SEED, match_key="X"
    )
    # Corrupt amount so value side could still tie on counts; instead delete via raw SQL
    # Simulate inconsistency by inserting a phantom OPEN without going through open_break counters —
    # easiest path: open two, then manually UPDATE one first_seen into the future so opening math breaks.
    conn.execute(
        "UPDATE breaks SET first_seen_run = ? WHERE match_key = ?",
        ((START + timedelta(days=5)).isoformat(), "X"),
    )
    conn.commit()
    with pytest.raises(RollForwardBreak) as ei:
        check_and_certify(conn, START, seed=SEED)
    assert "ROLL_FORWARD_BREAK" in str(ei.value)
    assert ei.value.figures["ties"] is False
    conn.close()
