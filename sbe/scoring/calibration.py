"""Calibration — reliability curve + ECE (BUILD_PLAN Tier 2 item 1, KEEP THIS,
do not cut: ~30 lines against data you already have in the breaks table)."""
import numpy as np


def reliability_curve(confidences: list, correct: list, n_bins: int = 10):
    raise NotImplementedError


def expected_calibration_error(confidences: list, correct: list, n_bins: int = 10) -> float:
    raise NotImplementedError
