"""Regression tests for the measurement, not evidence of photographic security."""
import json
from pathlib import Path

import numpy as np
import pytest

from stegolab.evaluation import (AdjacentBinStatistic, RegularityStatistic, auc_interval,
                                 dataset, metrics, SubspaceEnsemble)


def test_paired_identical_scores_are_chance():
    scores = np.linspace(-1, 1, 60)
    result = metrics(scores, scores.copy(), 0, .98)
    assert result["auc"] == pytest.approx(.5)
    assert result["auc_95_interval"] == pytest.approx([.5, .5])
    assert result["passes_provisional_upper_bound"]


def test_reversed_detection_is_not_security():
    result = metrics(np.ones(60), np.zeros(60), .5, .99)
    assert result["auc"] == 0
    assert result["orientation_robust_auc"] == 1
    assert result["orientation_robust_auc_upper_95"] == 1
    assert not result["passes_provisional_upper_bound"]


def test_rejections_and_shared_source_groups():
    c = np.linspace(0, 1, 60)
    s = c[5:] + .05
    groups = np.arange(60) // 2
    result = metrics(c, s, .5, .99, groups=(groups, groups[5:]))
    assert result["cover_images"] == 60
    assert result["stego_images"] == 55
    assert 0 <= result["auc_95_interval"][0] <= result["auc_95_interval"][1] <= 1
    assert auc_interval(c, s, groups=(groups, groups[5:]), repetitions=100) == auc_interval(
        c, s, groups=(groups, groups[5:]), repetitions=100)
    x, y = dataset(c[:, None], s[:, None])
    assert x.shape == (115, 1)
    assert y.sum() == 55


def test_discriminant_detector_learns_separable_positive_control():
    rng = np.random.default_rng(631)
    c = rng.normal(size=(100, 20))
    s = rng.normal(size=(90, 20)) + 3
    x, y = dataset(c, s)
    model = SubspaceEnsemble(learners=8, dimension=12).fit(x, y)
    assert np.max(model.decision_function(rng.normal(size=(30, 20)))) < np.min(
        model.decision_function(rng.normal(size=(30, 20)) + 3))


def test_standalone_statistic_feature_offsets():
    x = np.zeros((2, 8177), dtype=np.float32)
    x[0, -403:-147:2] = 1 / 128
    x[1, -403:-147] = 1 / 256
    np.testing.assert_allclose(AdjacentBinStatistic().decision_function(x), [-1, 0])
    x[0, -19:-1:3] = 1
    x[1, -18:-1:3] = 1
    np.testing.assert_allclose(RegularityStatistic().decision_function(x), [-1, 1])


def test_frozen_manifest_has_no_group_leakage():
    path = Path(__file__).resolve().parents[1] / "artifacts" / "manifest.json"
    if not path.exists():
        pytest.skip("Public research data has not been prepared")
    manifest = json.loads(path.read_text())
    ids, groups = set(), set()
    for part in manifest["parts"].values():
        part_groups = {manifest["group_ids"][i] for i in part}
        assert not ids.intersection(part)
        assert not groups.intersection(part_groups)
        ids.update(part)
        groups.update(part_groups)
    assert len(ids) == 10000
