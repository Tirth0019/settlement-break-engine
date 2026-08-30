"""Smoke selection, budget estimate, L3 fallback wiring."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sbe.db.connection import get_connection
from sbe.engine.l2_break_ledger import open_break
from sbe.engine.l3_investigator import investigate
from sbe.scoring.budget import estimate_investigate_budget
from sbe.scoring.harness import (
    SMOKE_ARCHETYPE_ORDER,
    select_open_breaks_smoke,
    select_open_breaks_stratified,
)

SEED = "test-smoke"


def _open(conn, arch: str, suffix: str) -> str:
    return open_break(
        conn,
        merchant_id=f"M_{suffix}",
        side="AMOUNT_MISMATCH",
        amount_delta=Decimal("-10.00"),
        run_date=date(2026, 3, 10),
        seed=SEED,
        match_key=f"UTR-{suffix}",
        ground_truth_archetype=arch,
    )


def test_smoke_selects_one_per_named_archetype(tmp_path):
    conn = get_connection(str(tmp_path / "smoke.db"))
    for arch in SMOKE_ARCHETYPE_ORDER:
        _open(conn, arch, arch[:4])
    # filler
    for i in range(5):
        _open(conn, "REFUND_NETTED", f"R{i}")

    plan = select_open_breaks_smoke(conn, SEED)
    assert len(plan.break_ids) == len(SMOKE_ARCHETYPE_ORDER)
    meta = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT break_id, ground_truth_archetype FROM breaks WHERE seed=?", (SEED,)
        )
    }
    picked_arch = {meta[b] for b in plan.break_ids}
    for arch in SMOKE_ARCHETYPE_ORDER:
        assert arch in picked_arch
    conn.close()


def test_smoke_differs_from_arbitrary_limit_five(tmp_path):
    conn = get_connection(str(tmp_path / "diff.db"))
    for i in range(8):
        _open(conn, "REFUND_NETTED", f"R{i:02d}")
    _open(conn, "FEE_PLUS_GST", "FEE1")

    smoke = select_open_breaks_smoke(conn, SEED)
    strat = select_open_breaks_stratified(conn, SEED, limit=5)
    assert smoke.break_ids != strat.break_ids
    conn.close()


def test_budget_flags_oversized_run(tmp_path):
    conn = get_connection(str(tmp_path / "bud.db"))
    for i in range(100):
        _open(conn, "FEE_PLUS_GST", f"B{i:03d}")
    b = estimate_investigate_budget(conn, SEED, tokens_per_break=4000, tpd_limit=200_000)
    assert b.open_eligible == 100
    assert b.estimated_tokens_full == 400_000
    assert b.fits_full_run is False
    assert b.max_breaks_one_day == 50
    conn.close()


def test_fallback_fires_on_dead_primary_and_audits(tmp_path, monkeypatch):
    conn = get_connection(str(tmp_path / "fb.db"))
    bid = _open(conn, "FEE_PLUS_GST", "FB01")
    rec = {
        "break_id": bid,
        "seed": SEED,
        "merchant_id": "M_FB01",
        "side": "AMOUNT_MISMATCH",
        "amount_delta": "-10.00",
        "match_key": "UTR-FB01",
        "first_seen_run": "2026-03-10",
        "status": "OPEN",
    }
    calls = {"n": 0}

    def fake_chat(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("404 model __dead_primary_for_fallback_test__ not found")
        args = json.dumps(
            {
                "verdict": "NEEDS_HUMAN",
                "hypothesis": "fallback path",
                "evidence": [],
                "residual_unexplained": "10.00",
                "confidence": 0.5,
            }
        )
        tc = SimpleNamespace(
            id="tc1",
            function=SimpleNamespace(name="submit_verdict", arguments=args),
        )
        msg = SimpleNamespace(content="", tool_calls=[tc])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr("sbe.config.INVESTIGATOR_FALLBACK_API_KEY", "fake-key")
    monkeypatch.setattr("sbe.config.INVESTIGATOR_FALLBACK_PROVIDER", "google")
    monkeypatch.setattr("sbe.config.INVESTIGATOR_FALLBACK_MODEL", "gemini-test")

    with patch("sbe.engine.l3_investigator._provider_client") as pc:
        pc.return_value = (object(), "primary-dead")
        with patch(
            "sbe.engine.l3_investigator._chat_openai_compatible",
            side_effect=fake_chat,
        ):
            investigate(
                rec,
                conn=conn,
                primary_model_override="__dead_primary_for_fallback_test__",
            )

    prov = conn.execute(
        """
        SELECT new_value FROM audit_log
         WHERE break_id=? AND who='l3_investigator' AND what='provider'
        """,
        (bid,),
    ).fetchone()
    assert prov is not None
    payload = json.loads(prov[0])
    assert payload["fallback"] is True
    conn.close()
