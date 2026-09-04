"""Calibration — 3-bin reliability curve + ECE (BUILD_PLAN Tier 2).

Honest thin-n reporting: bins with n<5 are flagged, never silently treated
as stable rates.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sbe.scoring.harness import (
    is_l3_scored_break,
    join_breaks_to_ground_truth,
    l3_investigated_break_ids,
    l3_verdict_map,
)


# FINAL_PLAN: 3 bins, not 10.
DEFAULT_EDGES = (0.0, 0.6, 0.85, 1.0001)
BIN_LABELS = ("low (<0.6)", "mid (0.6-0.85)", "high (>0.85)")


@dataclass
class CalibrationBin:
    label: str
    n: int
    predicted: float
    actual: float
    correct: int
    thin: bool  # n < 5


@dataclass
class CalibrationReport:
    n: int
    bins: list[CalibrationBin]
    ece: float


def reliability_curve(
    confidences: list,
    correct: list,
    n_bins: int = 3,
    *,
    edges: tuple[float, ...] | None = None,
) -> list[CalibrationBin]:
    """Return per-bin stats. Default is the FINAL_PLAN 3-bin scheme."""
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must be same length")
    if not confidences:
        return []

    if edges is None:
        if n_bins == 3:
            edges = DEFAULT_EDGES
        else:
            step = 1.0 / n_bins
            edges = tuple(i * step for i in range(n_bins)) + (1.0001,)

    bins: list[CalibrationBin] = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        idxs = [j for j, c in enumerate(confidences) if lo <= float(c) < hi]
        if n_bins == 3 and i < len(BIN_LABELS):
            label = BIN_LABELS[i]
        else:
            label = f"bin[{lo:.2f},{hi:.2f})"
        if not idxs:
            bins.append(
                CalibrationBin(
                    label=label, n=0, predicted=0.0, actual=0.0, correct=0, thin=True
                )
            )
            continue
        preds = [float(confidences[j]) for j in idxs]
        oks = [1 if correct[j] else 0 for j in idxs]
        n = len(idxs)
        predicted = sum(preds) / n
        actual = sum(oks) / n
        bins.append(
            CalibrationBin(
                label=label,
                n=n,
                predicted=predicted,
                actual=actual,
                correct=sum(oks),
                thin=n < 5,
            )
        )
    return bins


def expected_calibration_error(
    confidences: list,
    correct: list,
    n_bins: int = 3,
    *,
    edges: tuple[float, ...] | None = None,
) -> float:
    """ECE = Σ (n_b / N) |acc_b − conf_b|. Empty input → 0.0."""
    bins = reliability_curve(confidences, correct, n_bins=n_bins, edges=edges)
    n = len(confidences)
    if n == 0:
        return 0.0
    return sum((b.n / n) * abs(b.actual - b.predicted) for b in bins if b.n)


def calibrate_seed(conn: sqlite3.Connection, seed: str) -> CalibrationReport:
    """L3 confidence vs correctness on labeled hold-out / scored breaks."""
    l3_ids = l3_investigated_break_ids(conn, seed)
    l3_map = l3_verdict_map(conn, seed)
    rows = [
        r
        for r in join_breaks_to_ground_truth(conn, seed)
        if is_l3_scored_break(r, l3_ids) and r.get("correct_verdict")
    ]
    confidences: list[float] = []
    correct: list[bool] = []
    for r in rows:
        conf = r.get("confidence")
        if conf is None:
            continue
        l3v = l3_map.get(r["break_id"]) or r.get("verdict")
        confidences.append(float(conf))
        correct.append(l3v == r["correct_verdict"])

    bins = reliability_curve(confidences, correct, n_bins=3)
    ece = expected_calibration_error(confidences, correct, n_bins=3)
    return CalibrationReport(n=len(confidences), bins=bins, ece=ece)


def format_calibration_report(r: CalibrationReport) -> str:
    lines = [f"CONFIDENCE CALIBRATION (n={r.n})"]
    for b in r.bins:
        thin = "  [THIN n<5]" if b.thin else ""
        if b.n == 0:
            lines.append(f"  {b.label:18s}  n=0{thin}")
            continue
        lines.append(
            f"  {b.label:18s}  predicted {b.predicted:.2f}   "
            f"actual {b.correct}/{b.n}  ({b.actual:.2f}){thin}"
        )
    lines.append(f"  ECE = {r.ece:.3f}  ·  thin bins, interpret with n")
    return "\n".join(lines)
