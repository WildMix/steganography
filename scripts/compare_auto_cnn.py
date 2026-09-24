"""Paired held-out CNN comparison of keyed balanced auto and 0.05-bpp embedding."""
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"


def main():
    manifest = json.loads((ART / "manifest.json").read_text(encoding="utf-8"))
    paths = {"fixed": ART / "deep" / "balanced_0p05" / "test_predictions.npz",
             "auto": ART / "deep" / "balanced_auto" / "test_predictions.npz"}
    if not all(path.exists() for path in paths.values()):
        raise SystemExit("Both frozen CNN final prediction sets must exist first")
    scores = {}
    for variant, path in paths.items():
        with np.load(path) as data:
            scores[variant] = {
                "cover": dict(zip(data["cover_ids"].tolist(), data["cover"].tolist(), strict=True)),
                "stego": dict(zip(data["stego_ids"].tolist(), data["stego"].tolist(), strict=True))}
    common = [identifier for identifier in manifest["parts"]["test"]
              if all(identifier in scores[variant]["stego"] for variant in scores)]
    if len(common) < 40:
        raise ValueError(f"Only {len(common)} common accepted image pairs")
    labels = np.r_[np.zeros(len(common), dtype=int), np.ones(len(common), dtype=int)]
    joined = {variant: np.array([scores[variant]["cover"][i] for i in common]
                                + [scores[variant]["stego"][i] for i in common])
              for variant in scores}
    groups = np.array([manifest["group_ids"][i] for i in common * 2])
    units = [np.flatnonzero(groups == group) for group in np.unique(groups)]
    rng = np.random.default_rng(5824)
    signed_differences, robust_differences = [], []
    for _ in range(1000):
        draw = np.concatenate([units[i] for i in rng.integers(0, len(units), len(units))])
        if len(np.unique(labels[draw])) != 2:
            continue
        fixed = roc_auc_score(labels[draw], joined["fixed"][draw])
        auto = roc_auc_score(labels[draw], joined["auto"][draw])
        signed_differences.append(auto - fixed)
        robust_differences.append(max(auto, 1-auto) - max(fixed, 1-fixed))
    fixed_auc = float(roc_auc_score(labels, joined["fixed"]))
    auto_auc = float(roc_auc_score(labels, joined["auto"]))
    changes = {}
    for variant, tag in (("fixed", "0p05"), ("auto", "auto")):
        records = [json.loads((ART / "samples" / i / f"{tag}.json").read_text(encoding="utf-8"))
                   for i in common]
        changes[variant] = {"mean_changed_pixels": float(np.mean([r["changed_pixels"] for r in records])),
                            "mean_psnr_db": float(np.mean([r["psnr"] for r in records]))}
    result = {"scope": "Common accepted held-out covers and messages; independently validation-trained CNNs",
              "common_pairs": len(common), "fixed_auc": fixed_auc, "auto_auc": auto_auc,
              "auto_minus_fixed_auc": auto_auc - fixed_auc,
              "paired_group_95_interval": np.quantile(signed_differences, [.025, .975]).tolist(),
              "fixed_orientation_robust_auc": max(fixed_auc, 1-fixed_auc),
              "auto_orientation_robust_auc": max(auto_auc, 1-auto_auc),
              "paired_robust_95_interval": np.quantile(robust_differences, [.025, .975]).tolist(),
              "embedding": changes,
              "prediction_sha256": {variant: hashlib.sha256(path.read_bytes()).hexdigest()
                                    for variant, path in paths.items()}}
    from experiment import write_json
    write_json(ART / "auto_rate_cnn_comparison.json", result)
    from report_results import main as report_results
    report_results()
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
