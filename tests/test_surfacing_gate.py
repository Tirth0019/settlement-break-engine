"""Surfacing gate — fails on seed 1001 until L1 fix."""
from sbe.db.connection import get_connection
from sbe.engine.l1_surfacing_gate import check_l1_surfacing


def test_surfacing_gate_reports_fields(tmp_path):
    conn = get_connection(str(tmp_path / "empty.db"))
    r = check_l1_surfacing(conn, "nonexistent-seed-no-gt")
    assert "ok" in r
    assert r["injected_archetypes"] == 0
    assert r["ok"] is True  # vacuous pass when no injected archetypes
    conn.close()
