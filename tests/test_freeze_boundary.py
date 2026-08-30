"""Commits after the behavioural freeze must not touch frozen agent paths.

The git tag ``agent-freeze`` currently points at Day-6 ``4c5a0ac``. The
L1/L3/L4 behaviour that is actually frozen shipped in ``d3594e2``. This
test diffs against that commit so we do not move the published tag.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Behavioural freeze (L1 three-way + L3/L4 as scored). See README freeze boundary.
FROZEN_BASE = "d3594e2"
FROZEN = (
    "sbe/engine/l3_investigator.py",
    "sbe/engine/l4_verifier.py",
    "sbe/engine/l1_deterministic.py",
)


def test_frozen_paths_unchanged_since_behavioural_freeze():
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", FROZEN_BASE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        return
    diff = subprocess.run(
        ["git", "diff", FROZEN_BASE, "--", *FROZEN],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert diff.stdout.strip() == "", (
        "Frozen paths changed after behavioural freeze "
        f"{FROZEN_BASE}:\n" + diff.stdout[:2000]
    )
