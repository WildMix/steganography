"""Paired same-rate ablation using already-frozen, already-scored final models."""
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"


def main():
    manifest = json.loads((ART / "manifest.json").read_text())
    variants = ("baseline_0p05", "balanced_0p05")
    records = {}
    for name in ("adjacent_bin_chisquare", "rs_like_regularity", "residual_subspace_ensemble", "residual_extra_trees"):
        paths = [ART / "models" / v / f"{name}_test_predictions.npz" for v in variants]
        if not all(p.exists() for p in paths):
            raise SystemExit("Both frozen final comparisons must be complete first")
        data = [np.load(p) for p in paths]
        for field in ("cover_ids", "stego_ids"):
            np.testing.assert_array_equal(data[0][field], data[1][field])
        nc, ns = len(data[0]["cover"]), len(data[0]["stego"])
        labels = np.r_[np.zeros(nc, dtype=int), np.ones(ns, dtype=int)]
        scores = [np.r_[d["cover"], d["stego"]] for d in data]
        identifiers = np.r_[data[0]["cover_ids"], data[0]["stego_ids"]]
        groups = np.array([manifest["group_ids"][i] for i in identifiers])
        units = [np.flatnonzero(groups == group) for group in np.unique(groups)]
        rng = np.random.default_rng(6173)
        difference = []
        for _ in range(1000):
            draw = np.concatenate([units[i] for i in rng.integers(0, len(units), len(units))])
            if len(np.unique(labels[draw])) == 2:
                difference.append(roc_auc_score(labels[draw], scores[1][draw])
                                  - roc_auc_score(labels[draw], scores[0][draw]))
        a, b = (float(roc_auc_score(labels, s)) for s in scores)
        records[name] = {"baseline_auc": a, "balanced_auc": b, "balanced_minus_baseline_auc": b-a,
                         "paired_group_95_interval": np.quantile(difference, [.025, .975]).tolist(),
                         "both_point_scores_at_least_chance": a >= .5 and b >= .5,
                         "prediction_sha256": {str(p.relative_to(ART)): hashlib.sha256(p.read_bytes()).hexdigest()
                                                for p in paths}}
        for item in data:
            item.close()
    output = {"scope": "Same covers, gross payload, and changed-pixel locations; separately trained frozen detectors",
              "difference": "Balanced minus baseline AUC, with score orientations frozen on validation",
              "warning": "A lower signed AUC is not automatically better if the score becomes reliably reversed; "
                         "consult the separate either-orientation bounds. These intervals are per detector.",
              "detectors": records}
    (ART / "same_rate_ablation.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2), flush=True)


if __name__ == "__main__":
    main()
