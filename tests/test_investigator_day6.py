"""Day 6 tools + investigator contract tests (no live LLM required)."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from sbe.engine.l3_investigator import (
    UNTRUSTED_BEGIN,
    UNTRUSTED_END,
    InvestigatorVerdict,
    build_user_prompt,
    investigate,
)
from sbe.engine.tools import decimal_calc
from sbe.engine.tools.find_split_candidates import find_split_candidates
from sbe.engine.tools.normalise_identifier import identifiers_compatible, normalise
from sbe.engine.tools.query_sources import SourceStore, query_bank, query_settlement
from sbe.engine.tools.reserve_schedule import reserve_schedule
from sbe.generator.archetypes.adversarial_narration import ADVERSARIAL_SNIPPET
from sbe.money import money


def test_find_split_candidates_exact_subset():
    hits = find_split_candidates(
        money("100.00"),
        [money("40.00"), money("60.00"), money("25.00")],
        max_n=3,
    )
    assert any(h["sum"] == "100.00" and set(h["indices"]) == {0, 1} for h in hits)


def test_find_split_candidates_respects_max_n():
    hits = find_split_candidates(
        money("100.00"),
        [money("25.00")] * 5,
        max_n=3,
    )
    assert hits == []  # need 4×25, capped out


def test_decimal_calc_ops_and_log():
    decimal_calc.clear_log()
    assert decimal_calc.add("10.005", "0.005") == money("10.02")
    assert decimal_calc.subtract("10.00", "3.33") == money("6.67")
    assert decimal_calc.residual(money("112.59"), ["112.59"]) == money("0.00")
    assert decimal_calc.calc("(100.00 - 2.00) * 0.18") == money("17.64")
    assert any(e["op"] == "residual" for e in decimal_calc.CALL_LOG)
    with pytest.raises(ValueError):
        decimal_calc.calc("__import__('os').system('x')")


def test_normalise_truncated_utr_compatible():
    full = "UTR9508836429833979"
    truncated = "NEFT UTR95088364"  # HDFC-style chop
    assert normalise(truncated).startswith("UTR")
    assert identifiers_compatible(truncated, full)


def test_reserve_schedule_reads_fee_yaml():
    rr = reserve_schedule("MERCH_0001")
    assert rr["hold_pct"] == 0.10
    assert rr["hold_days"] == 90


def test_query_sources_seed_1001():
    store = SourceStore.load("1001")
    if not store.settlement:
        pytest.skip("seed 1001 not generated")
    mid = store.settlement[0]["merchant_id"]
    settled = store.settlement[0]["settled_at"]
    rows = query_settlement(mid, (settled, settled), store)
    assert rows
    assert all(r["merchant_id"] == mid for r in rows)
    bank = query_bank(mid, (date(2026, 3, 1), date(2026, 3, 31)), store)
    assert isinstance(bank, list)


def test_match_verdict_rejects_nonzero_residual():
    with pytest.raises(ValidationError):
        InvestigatorVerdict(
            break_id="BRK-2026-0310-0001",
            verdict="MATCH",
            hypothesis="fees",
            evidence=[],
            residual_unexplained="0.03",
            confidence=0.9,
            tools_called=[],
        )


def test_prompt_quarantines_adversarial_narration():
    prompt = build_user_prompt(
        {
            "break_id": "BRK-TEST",
            "merchant_id": "MERCH_0001",
            "amount_delta": "-112.59",
            "narration": ADVERSARIAL_SNIPPET,
            "description": ADVERSARIAL_SNIPPET,
            "ground_truth_archetype": "ADVERSARIAL_NARRATION",  # must not appear trusted
        }
    )
    assert UNTRUSTED_BEGIN in prompt and UNTRUSTED_END in prompt
    assert ADVERSARIAL_SNIPPET in prompt
    # Ground truth must stay out of the trusted agent-visible payload
    assert "ADVERSARIAL_NARRATION" not in prompt
    assert "ground_truth_archetype" not in prompt


def _fake_chat_submit_match(messages, tools):
    """Deterministic fake model: one tool round then submit_verdict."""
    # Count prior assistant tool rounds
    n_assistant = sum(1 for m in messages if m.get("role") == "assistant")
    if n_assistant == 0:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                id="call_1",
                                function=SimpleNamespace(
                                    name="decimal_calc",
                                    arguments=json.dumps(
                                        {
                                            "op": "residual",
                                            "claimed_gap": "112.59",
                                            "explained_amounts": ["112.59"],
                                        }
                                    ),
                                ),
                            )
                        ],
                    )
                )
            ]
        )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call_2",
                            function=SimpleNamespace(
                                name="submit_verdict",
                                arguments=json.dumps(
                                    {
                                        "verdict": "MATCH",
                                        "hypothesis": "fee_gst explains gap",
                                        "evidence": [
                                            {
                                                "source": "decimal_calc",
                                                "ref": "residual",
                                                "value": "0.00",
                                            }
                                        ],
                                        "residual_unexplained": "0.00",
                                        "confidence": 0.85,
                                    }
                                ),
                            ),
                        )
                    ],
                )
            )
        ]
    )


def test_investigate_tool_loop_with_fake_chat():
    store = SourceStore(seed="test")
    verdict = investigate(
        {
            "break_id": "BRK-2026-0310-0099",
            "seed": "test",
            "merchant_id": "MERCH_0001",
            "amount_delta": "-112.59",
            "side": "AMOUNT_MISMATCH",
            "first_seen_run": "2026-03-10",
            "narration": ADVERSARIAL_SNIPPET,
        },
        store=store,
        chat_fn=_fake_chat_submit_match,
    )
    assert verdict.verdict == "MATCH"
    assert verdict.residual_unexplained == "0.00"
    assert "decimal_calc" in verdict.tools_called
