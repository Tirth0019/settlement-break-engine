"""Sep 2 deliverables — cost, calibration, packets, graduation, certificate."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from sbe.db.connection import get_connection
from sbe.engine.certificate import publish_or_refuse, render_certificate
from sbe.engine.l5_rollforward import RollForwardBreak
from sbe.engine.l6_packets import propose_journal_entry, render_break_packet
from sbe.engine.l7_graduation import (
    detect_graduation_candidates,
    format_graduation_report,
    llm_calls_by_day,
)
from sbe.scoring.calibration import (
    expected_calibration_error,
    format_calibration_report,
    reliability_curve,
)
from sbe.scoring.cost import cost_per_resolved_break, estimate_seed_cost


def test_cost_zero_breaks_no_divzero():
    assert cost_per_resolved_break([], {"l3": 0.1, "l4": 0.2}) == 0.0


def test_cost_splits_l3_l4():
    log = [
        {"layer": "l3", "tokens": 4000},
        {"layer": "l3", "tokens": 4000},
        {"layer": "l4", "tokens": 1000},
    ]
    # (8k*0.05 + 1k*0.15)/1000 / 3 = (0.4+0.15)/3
    got = cost_per_resolved_break(log, {"l3": 0.05, "l4": 0.15})
    assert abs(got - (0.55 / 3)) < 1e-9


def test_estimate_seed_cost_handles_empty(tmp_path):
    conn = get_connection(str(tmp_path / "empty.db"))
    r = estimate_seed_cost(conn, "nope")
    assert r.l3_breaks == 0 and r.l4_breaks == 0
    assert r.inr_per_l3_break == 0.0
    conn.close()


def test_ece_hand_computed_six_rows():
    # 3 correct @ 0.9, 3 wrong @ 0.3 → with 3 bins:
    # high: n=3 pred=0.9 act=1.0; low: n=3 pred=0.3 act=0.0; mid empty
    conf = [0.9, 0.9, 0.9, 0.3, 0.3, 0.3]
    ok = [True, True, True, False, False, False]
    ece = expected_calibration_error(conf, ok, n_bins=3)
    # |1-0.9|*(3/6) + |0-0.3|*(3/6) = 0.05 + 0.15 = 0.20
    assert abs(ece - 0.20) < 1e-9
    bins = reliability_curve(conf, ok, n_bins=3)
    assert bins[0].n == 3
    assert bins[0].thin is True  # n<5 flagged
    report_txt = format_calibration_report(
        type("R", (), {"n": 6, "bins": bins, "ece": ece})()
    )
    assert "THIN" in report_txt
    assert "(n=6)" in report_txt


def test_graduation_fires_without_overturn_not_with():
    good = [
        {
            "break_id": f"B{i}",
            "archetype": "FEE_PLUS_GST",
            "verdict": "MATCH",
            "confidence": 0.95,
            "residual_unexplained": "0.00",
            "verifier_decision": "UPHOLD",
        }
        for i in range(5)
    ]
    props, declines = detect_graduation_candidates(good, min_occurrences=5)
    assert len(props) == 1
    assert declines == []
    assert "DETECTION ONLY" in props[0]["status"]
    assert "DETECTION ONLY" in format_graduation_report(props, declines)

    bad = [{**good[0], "break_id": "BX", "verifier_decision": "OVERTURN"}]
    props_b, declines_b = detect_graduation_candidates(
        good[:-1] + bad, min_occurrences=5
    )
    assert props_b == []
    assert any("OVERTURN" in d["reason"] for d in declines_b)
    report_b = format_graduation_report(props_b, declines_b)
    assert "RULE PROPOSALS: none" in report_b
    assert "DECLINED" in report_b
    assert "reasoned refusal" in report_b

    thin = good[:3]
    props_t, declines_t = detect_graduation_candidates(thin, min_occurrences=5)
    assert props_t == []
    assert any("below threshold" in d["reason"] for d in declines_t)


def test_llm_calls_by_day_is_cut():
    out = llm_calls_by_day(None)
    assert out["status"] == "CUT"


def test_packet_match_residual_and_mask():
    pkt = render_break_packet(
        {
            "break_id": "BRK-2026-0310-0001",
            "amount_delta": "-106.65",
            "age_days": 1,
            "merchant_id": "MERCH_0001",
            "verdict": "MATCH",
            "hypothesis": "GST omitted; PAN ABCDE1234F card 4111 1111 1111 1111",
            "residual_unexplained": "0.00",
            "confidence": 0.99,
            "verifier_decision": "UPHOLD",
            "evidence": [
                {"source": "settlement_report", "ref": "[0]", "value": "fee_gst 106.65"}
            ],
            "ground_truth_archetype": "FEE_PLUS_GST",
        }
    )
    assert "RESIDUAL UNEXPLAINED" in pkt
    assert "₹0.00" in pkt or "0.00" in pkt
    assert "settlement_report" in pkt
    assert "ABCDE1234F" not in pkt
    assert "4111" not in pkt or "CARD_REDACTED" in pkt
    je = propose_journal_entry({"break_id": "BRK-2026-0310-0001", "amount_delta": "-106.65"})
    assert je["status"] == "PENDING_APPROVAL"
    assert je["auto_post"] is False


def test_packet_needs_human_without_hypothesis():
    pkt = render_break_packet(
        {
            "break_id": "BRK-LEAK",
            "amount_delta": "-381.00",
            "verdict": "NEEDS_HUMAN",
            "hypothesis": "",
            "residual_unexplained": "-381.00",
            "evidence": [],
        }
    )
    assert "none — gap not explained" in pkt.lower() or "gap not explained" in pkt


def test_phantom_refuses_publish(tmp_path):
    from sbe.engine.l2_break_ledger import open_break

    conn = get_connection(str(tmp_path / "cert.db"))
    open_break(
        conn,
        merchant_id="M",
        side="AMOUNT_MISMATCH",
        amount_delta=Decimal("10.00"),
        run_date=date(2026, 3, 10),
        seed="c1",
        match_key="UTR-1",
    )
    text = render_certificate(conn, "c1", "2026-03-10")
    assert "closing" in text.lower()
    with pytest.raises(RollForwardBreak, match="PUBLISH REFUSED"):
        publish_or_refuse(conn, "c1", "2026-03-10", inject_phantom=True)
    n = conn.execute(
        "SELECT COUNT(1) FROM breaks WHERE break_id LIKE 'BRK-PHANTOM%'"
    ).fetchone()[0]
    assert n == 0
    conn.close()
