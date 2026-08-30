"""Hold-out seed sizing (docs/FINAL_PLAN.md §1.1) — generator config, not agent behaviour."""
from pathlib import Path

from sbe.generator.archetypes.registry import HOLDOUT_ARCHETYPE_WEIGHTS
from sbe.generator.seed import generate_seed


def test_target_breaks_maps_to_record_count(tmp_path, monkeypatch):
    import sbe.generator.seed as seed_mod

    monkeypatch.setattr(seed_mod, "SEEDS_ROOT", Path(tmp_path))
    out = generate_seed("8888", days=10, holdout=True, target_breaks=60)
    import json

    meta = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert meta["holdout"] is True
    assert meta["record_count_target"] == 86
    assert meta["records_generated"] == 86
    labels = meta["label_counts"]
    for arch in ("FEE_PLUS_GST", "TDS_194O", "CHARGEBACK_PLUS_FEE", "TRUE_LEAKAGE"):
        assert labels.get(arch, 0) >= 1, f"{arch} missing from hold-out injection"


def test_holdout_weights_sum_positive():
    total = sum(w for _, _, w in HOLDOUT_ARCHETYPE_WEIGHTS)
    assert total > 0.99
    names = {n for n, _, _ in HOLDOUT_ARCHETYPE_WEIGHTS}
    assert {"FEE_PLUS_GST", "TDS_194O", "CHARGEBACK_PLUS_FEE", "TRUE_LEAKAGE"} <= names
