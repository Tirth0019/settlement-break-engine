"""
Generator self-assertion pass (BUILD_PLAN Phase 1 GATE 1).

Run this before any agent ever sees a seed. It must be green on all three
dev seeds before Phase 2 starts. This is the generator's own roll-forward:
every archetype's self_check already passed at construction (base.py), so
this pass focuses on CROSS-archetype and cross-source consistency.
"""
from __future__ import annotations

from collections import Counter

from sbe.generator.archetypes._helpers import (
    flatten_result_rows,
    settlement_row_integrity,
)
from sbe.money import ZERO, money


def validate_seed(archetype_results: list, *, print_distribution: bool = True) -> dict:
    """
    Raises AssertionError with a specific, actionable message on first failure.

    Checks:
      1. Every result.self_check == 0.00
      2. Every settlement row's net_amount equals recomputed components
      3. Cross-source: for non-leakage MATCH rows, bank_net - ledger_net equals
         ground_truth.amount_delta (the declared break gap)
    """
    labels = Counter()

    for r in archetype_results:
        arch = r.ground_truth.get("archetype", "UNKNOWN")
        labels[arch] += 1
        assert r.self_check == ZERO, (
            f"{arch}: self_check={r.self_check}, expected {ZERO}"
        )

        flat = flatten_result_rows(r)
        for row in flat["settlement_report"]:
            residual = settlement_row_integrity(row)
            assert residual == ZERO, (
                f"{arch}: settlement {row.get('settlement_id')} net integrity "
                f"residual={residual} (stated net vs components)"
            )

        # Cross-source declared-gap check on primary-day rows (open state)
        from sbe.generator.archetypes._helpers import amount_delta

        primary_bank = r.rows.get("bank_statement") or []
        primary_ledger = r.rows.get("merchant_ledger") or []
        implied = amount_delta(primary_bank, primary_ledger)
        declared = money(r.ground_truth.get("amount_delta", "0"))
        # TRUE_LEAKAGE / date-shift archetypes may declare a naive gap while
        # also shipping the resolving bank row in the same payload — for those,
        # skip strict primary equality and rely on self_check + settlement integrity.
        skip_primary = arch in {
            "STATE_HOLIDAY_SHIFT",
            "BANK_CUTOFF_ROLLOVER",
            "T2_PERIOD_BOUNDARY",
        }
        if not skip_primary:
            assert implied == declared, (
                f"{arch}: cross-source amount_delta mismatch: "
                f"implied={implied}, declared={declared}"
            )

    distribution = dict(sorted(labels.items()))
    if print_distribution:
        total = sum(labels.values())
        print(f"validate_seed: {total} results")
        for k, v in distribution.items():
            pct = 100.0 * v / total if total else 0
            print(f"  {k:28s} {v:5d}  ({pct:5.1f}%)")

    return {"ok": True, "label_counts": distribution, "n": sum(labels.values())}
