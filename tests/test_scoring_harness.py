"""Scoring harness — L3-only table, stratified selection, adversarial split."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sbe.db.connection import get_connection
from sbe.engine.l2_break_ledger import append_audit, open_break, try_late_arrival_close
from sbe.scoring.harness import (
    InvestigateRunReport,
    adversarial_metrics,
    format_pass1_report,
    is_l3_scored_break,
    l3_investigated_break_ids,
    per_archetype_table,
    select_open_breaks_stratified,
)

SEED = "test-scoring"


def _open(conn, *, arch_hint: str, bid_suffix: str, amt: str) -> str:
    return open_break(
        conn,
        merchant_id=f"MERCH_{bid_suffix}",
        side="AMOUNT_MISMATCH",
        amount_delta=Decimal(amt),
        run_date=date(2026, 3, 10),
        seed=SEED,
        match_key=f"UTR-{arch_hint}-{bid_suffix}",
        ground_truth_archetype=arch_hint,
    )


def test_late_arrival_verdict_not_scored_as_l3(tmp_path):
    conn = get_connection(str(tmp_path / "l2.db"))
    bid = open_break(
        conn,
        "MERCH_0001",
        "LEDGER_ONLY",
        Decimal("-100.00"),
        date(2026, 3, 10),
        seed=SEED,
        match_key="UTR-L2",
        ground_truth_archetype="T2_PERIOD_BOUNDARY",
    )
    try_late_arrival_close(
        conn,
        {"seed": SEED, "merchant_id": "MERCH_0001", "amount": Decimal("100.00"), "match_key": "UTR-L2"},
        date(2026, 3, 12),
    )
    row = conn.execute(
        "SELECT break_id, verdict, close_reason FROM breaks WHERE break_id=?", (bid,)
    ).fetchone()
    assert row[1] is None
    assert row[2] == "late_arrival"
    l3_ids = l3_investigated_break_ids(conn, SEED)
    assert not is_l3_scored_break(
        {"break_id": bid, "verdict": row[1], "close_reason": row[2]}, l3_ids
    )
    conn.close()


def test_stratified_selection_covers_arithmetic_archetypes(tmp_path):
    conn = get_connection(str(tmp_path / "strat.db"))
    for arch in ("FEE_PLUS_GST", "TDS_194O", "CHARGEBACK_PLUS_FEE", "UTR_TRUNCATION"):
        _open(conn, arch_hint=arch, bid_suffix=arch[:4], amt="-10.00")
    # filler
    for i in range(10):
        _open(conn, arch_hint="UNKNOWN", bid_suffix=f"U{i:02d}", amt=f"-{i+20}.00")

    picked = select_open_breaks_stratified(conn, SEED, limit=5).break_ids
    assert len(picked) == 5
    meta = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT break_id, ground_truth_archetype FROM breaks WHERE seed=?", (SEED,)
        ).fetchall()
    }
    picked_arch = {meta[b] for b in picked}
    assert "FEE_PLUS_GST" in picked_arch
    assert "TDS_194O" in picked_arch
    assert "CHARGEBACK_PLUS_FEE" in picked_arch
    conn.close()


def test_per_archetype_table_l3_only(tmp_path):
    conn = get_connection(str(tmp_path / "table.db"))
    l2_id = _open(conn, arch_hint="T2_PERIOD_BOUNDARY", bid_suffix="L2", amt="-50.00")
    l3_id = _open(conn, arch_hint="FEE_PLUS_GST", bid_suffix="L3", amt="-12.59")
    conn.execute(
        """
        UPDATE breaks SET status='RESOLVED', close_reason='late_arrival',
               verdict='MATCH', residual_unexplained='0.00'
         WHERE break_id=?
        """,
        (l2_id,),
    )
    conn.execute(
        """
        UPDATE breaks SET verdict='MATCH', hypothesis='fees', confidence=0.9,
               evidence_json='[]', residual_unexplained='0.00',
               tools_called_json='["decimal_calc"]'
         WHERE break_id=?
        """,
        (l3_id,),
    )
    append_audit(
        conn,
        l3_id,
        "l3_investigator",
        "verdict",
        None,
        "MATCH",
        at="2026-03-10T12:00:00",
    )
    conn.commit()
    table = per_archetype_table(conn, SEED)
    assert len(table) == 1
    assert table.iloc[0]["archetype"] == "FEE_PLUS_GST"
    assert table.iloc[0]["n"] == 1
    conn.close()


def test_pass1_cap_truncates_core_trio(tmp_path):
    conn = get_connection(str(tmp_path / "cap.db"))
    for arch in ("FEE_PLUS_GST", "TDS_194O", "CHARGEBACK_PLUS_FEE", "UTR_TRUNCATION"):
        _open(conn, arch_hint=arch, bid_suffix=arch[:4], amt="-10.00")
    plan = select_open_breaks_stratified(conn, SEED, limit=2)
    assert "TDS_194O" in plan.pass1_cap_truncated or "CHARGEBACK_PLUS_FEE" in plan.pass1_cap_truncated
    report = InvestigateRunReport(plan=plan, succeeded=[plan.break_ids[0]])
    assert report.pass1_core_complete is False
    assert "INCOMPLETE" in format_pass1_report(report)
    conn.close()


def test_adversarial_split_metrics(tmp_path):
    conn = get_connection(str(tmp_path / "adv.db"))
    bid = _open(conn, arch_hint="ADVERSARIAL_NARRATION", bid_suffix="01", amt="-100.00")
    conn.execute(
        """
        UPDATE breaks SET verdict='NEEDS_HUMAN', hypothesis='caution',
               confidence=0.5, evidence_json='[]', residual_unexplained='100.00',
               tools_called_json=?
         WHERE break_id=?
        """,
        (json.dumps(["decimal_calc"]), bid),
    )
    append_audit(conn, bid, "l3_investigator", "verdict", None, "NEEDS_HUMAN")
    conn.commit()
    m = adversarial_metrics(conn, SEED)
    assert m["n"] == 1
    assert m["resisted_injection"] == 1
    assert m["correct_verdict"] == 0  # ground truth join may lack correct_verdict
    conn.close()
