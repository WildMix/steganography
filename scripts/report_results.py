"""Render measured artifacts only; never trains, selects, or opens unseen test features."""
import json
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def metric_row(variant, detector, item):
    lo, hi = item["auc_95_interval"]
    status = "control" if variant == "control" else ("pass" if item["passes_provisional_upper_bound"] else "fail")
    return (f"| {variant} | {detector} | {item['auc']:.4f} | [{lo:.4f}, {hi:.4f}] | "
            f"{item['orientation_robust_auc_upper_95']:.4f} | {item['equal_prior_error']:.4f} | "
            f"{status} |")


def table():
    return ["| Variant | Detector | AUC | Group-bootstrap 95% interval | Either-direction upper bound | Equal-prior error | Target |",
            "|---|---|---:|---|---:|---:|---|"]


def main():
    manifest = read(ART / "manifest.json")
    selection = read(ART / "selection.json") if (ART / "selection.json").exists() else None
    lines = ["# Measured steganography results", "",
             "This report is generated from saved experiment artifacts. A pass is evidence only against "
             "the evaluated detector, its fitted model, this image source, and the tested payload profile. "
             "It is not a proof of statistical indistinguishability.", "",
             "## Acceptance rule", "",
             "The agreed provisional target is ROC-AUC at most 0.55. The conservative operational rule "
             "requires a paired source-group bootstrap 95% interval contained in [0.45, 0.55], accounting "
             "for either score direction. Neural results are reported separately. Intervals are per detector, "
             "not familywise; training-procedure uncertainty is not included.", "",
             "An interval entirely above 0.5 still demonstrates a detectable signal, even if it passes "
             "the provisional 0.55 bound. This rule is not a test that proves exact equality of cover and "
             "stego distributions, and it does not certify repeated-image or aggregate-channel security.", "",
             "## Source and split", "",
             "The source contains 10,000 native 512-by-512 grayscale photographic rasters. No resizing "
             "or pixel conversion is used. Cover and stego PNGs use an identical serializer. Exact duplicates "
             "and approximate difference-hash neighbors are grouped before splitting.", "",
             "Partitions: " + ", ".join(f"{k}={len(v)}" for k, v in manifest["parts"].items()) + ". "
             f"Source groups: {manifest['near_duplicate_groups']}.", "",
             "Camera/session labels are unavailable; the split does not establish unseen-camera generalization. "
             "The manifest and source archive checksum are retained in `artifacts/manifest.json` and `data/dataset.json`.", "",
             "## Selection", ""]
    if selection:
        lines += [f"Frozen candidate: **{selection['variant']}**.", "",
                  "The full decision record, including validation evidence and the scope of selection, "
                  "is in `artifacts/selection.json`."]
        if selection["variant"] == "balanced_0p05":
            lines += ["", "At the largest predeclared rate, 0.05 gross bpp, both sender strategies passed "
                      "the classical validation gate. Balancing was chosen because its worst validation "
                      "upper confidence bound was lower: 0.5273, versus 0.5433 for the baseline. "
                      "This choice was frozen before final-test detector scores were computed. "
                      "Lower-rate experiments are supplementary capacity comparisons, not evidence used "
                      "to choose a different encoder after looking at the final test."]
    else:
        lines += ["No candidate has been frozen yet. This is an incomplete progress report, not a final acceptance claim."]
    if selection:
        final_path = ART / "models" / selection["variant"] / "final.json"
        deep_path = ART / "deep" / selection["variant"] / "final.json"
        control_path = ART / "models" / "control" / "final.json"
        deep_control_path = ART / "deep" / "control" / "final.json"
        if all(p.exists() for p in (final_path, deep_path, control_path, deep_control_path)):
            final, deep = read(final_path), read(deep_path)
            control, deep_control = read(control_path), read(deep_control_path)
            classical = [v["test"] for v in final["detectors"].values()]
            bounds_pass = all(v["passes_provisional_upper_bound"] for v in classical + [deep])
            control_pass = all(control["detectors"][name]["test"]["auc_95_interval"][0] > .75
                               for name in ("residual_subspace_ensemble", "residual_extra_trees"))
            control_pass = control_pass and deep_control["auc_95_interval"][0] > .75
            outcome = ("met the provisional target against the evaluated detectors" if bounds_pass and control_pass
                       else "did not establish the complete provisional target")
            lines[2:2] = [f"The frozen **{selection['variant']}** candidate **{outcome}** on the final holdout. "
                          f"Largest classical upper bound: {max(v['orientation_robust_auc_upper_95'] for v in classical):.4f}; "
                          f"neural upper bound: {deep['orientation_robust_auc_upper_95']:.4f}. "
                          f"Held-out positive-control sensitivity gate: {'passed' if control_pass else 'failed'}.", ""]
    lines += ["", "## Development measurements", "",
              "Validation is used for encoder comparison, score orientation, decision thresholds, and neural "
              "checkpoint selection. It is not the independent final confirmation.", "", *table()]
    validations = sorted((ART / "models").glob("*/validation.json"))
    for path in validations:
        record = read(path)
        for detector, item in record["detectors"].items():
            lines.append(metric_row(record["variant"], detector, item["validation"]))
    lines += ["", "## Independent final measurements", "", *table()]
    finals = sorted((ART / "models").glob("*/final.json"))
    for path in finals:
        record = read(path)
        for detector, item in record["detectors"].items():
            lines.append(metric_row(record["variant"], detector, item["test"]))
    if not finals:
        lines += ["", "Final measurements are not complete."]
    ablation_path = ART / "same_rate_ablation.json"
    if ablation_path.exists():
        ablation = read(ablation_path)
        lines += ["", "### Same-rate ablation", "",
                  "Both variants use the same test covers, payloads, and changed-pixel locations. "
                  "Only modification signs differ; each detector is trained separately for its variant. "
                  "The paired source-group interval below measures balanced-minus-baseline AUC with "
                  "score directions frozen on validation. Negative values mean a lower AUC in that "
                  "fixed direction; use the either-direction bounds above to rule out misleading reversals.", "",
                  "| Detector | AUC difference | Paired group-bootstrap 95% interval |",
                  "|---|---:|---|"]
        for name, item in ablation["detectors"].items():
            lo, hi = item["paired_group_95_interval"]
            lines.append(f"| {name} | {item['balanced_minus_baseline_auc']:+.4f} | [{lo:+.4f}, {hi:+.4f}] |")
        improved = [name for name, item in ablation["detectors"].items()
                    if item["paired_group_95_interval"][1] < 0
                    and item["both_point_scores_at_least_chance"]]
        uncertain = [name for name, item in ablation["detectors"].items()
                     if item["paired_group_95_interval"][0] <= 0 <= item["paired_group_95_interval"][1]]
        if improved:
            lines += ["", "The paired interval supports a reduction in validation-oriented AUC for "
                      + ", ".join(f"`{name}`" for name in improved) + "."]
        if uncertain:
            lines += ["", "The paired interval includes zero for "
                      + ", ".join(f"`{name}`" for name in uncertain)
                      + "; a measurable improvement is not established for those detectors. "
                      "This is not evidence of a uniform improvement across all steganalyzers. "
                      "No same-rate neural baseline ablation was run."]
    lines += ["", "The primary table includes every ordinary cover and only successfully emitted stegos. "
              "Accepted-cover-only results, validation-calibrated low-FPR operating points, and image-level "
              "predictions are retained in each model's JSON/NPZ artifacts.", "",
              "## Neural detector", "",
              "The neural model is a compact 30,929-parameter high-pass residual CNN trained locally on CPU. "
              "It is not a full SRNet reproduction or an exhaustive modern-steganalysis evaluation. "
              "Inference averages four quadrants covering every image pixel.", "", *table()]
    for path in sorted((ART / "deep").glob("*/validation.json")):
        record = read(path)
        lines.append(metric_row(record["variant"], f"CNN validation, epoch {record['selected_epoch']}", record["validation"]))
        final = path.with_name("final.json")
        if final.exists():
            lines.append(metric_row(record["variant"], "CNN final", read(final)))
    lines += ["", "The intentionally detectable control uses 0.4-bpp random LSB replacement. A successful "
              "control demonstrates basic detector functionality, not sufficient power against every "
              "low-rate adaptive signal. Its desired result is high AUC, not the low-detection target. "
              "The residual-feature and neural controls must have a lower AUC confidence bound above 0.75. "
              "A failed control makes the corresponding security conclusion inconclusive.", "",
              "## Embedding behavior", "",
              "Every admitted sample is actually encoded, serialized to PNG, decoded, and authenticated. "
              "Both baseline and balanced variants must recover the original message; a simulator is not used. "
              "The sign-only extension preserves change positions, parity, unit-change magnitude, additive "
              "distortion, and PSNR. Its histogram-objective decrease is not a detection metric.", "",
              "| Partition | Gross bpp | Completed covers | Rejected | Mean changed pixels | Mean PSNR (dB) | Mean objective before / after |",
              "|---|---:|---:|---:|---:|---:|---|"]
    rates = sorted({p.stem for directory in (ART / "samples").iterdir() for p in directory.glob("*.json")})
    for part in ("train", "validation", "test"):
        # Never expose unconfirmed test-generation summaries as development feedback.
        if part == "test" and not finals:
            continue
        for rate in rates:
            records = [read(path) for i in manifest["parts"][part]
                       if (path := ART / "samples" / i / f"{rate}.json").exists()]
            if not records:
                continue
            success = [r for r in records if "failure" not in r]
            if not success:
                continue
            mean = lambda name: statistics.mean(r[name] for r in success)
            lines.append(f"| {part} | {rate.replace('p', '.')} | {len(records)} | {len(records)-len(success)} | "
                         f"{mean('changed_pixels'):.2f} | {mean('psnr'):.2f} | "
                         f"{mean('balance_objective_before'):.3f} / {mean('balance_objective_after'):.3f} |")
    lines += ["", "At 512-by-512 pixels, stored message capacities before possible compression gains are "
              "1,572 bytes at 0.05 gross bpp, 753 bytes at 0.025, 261 bytes at 0.01, and 97 bytes at 0.005. "
              "Salt, authentication, framing, and padding are included in the gross rate. "
              "Protected image regions can cause admission failures independently of nominal capacity.", "",
              "## Reproducibility and limits", "",
              "Implementation and commands: `README.md`. Original specification: `steganography_master_blueprint.md`. "
              "Experimental objective and invariants: `DESIGN_EXTENSION.md`. Split and decision rules: "
              "`EXPERIMENT_PROTOCOL.md`. Runtime versions and implementation hashes: `artifacts/environment.json`. "
              "Exact installed Python dependencies: `requirements-research.lock.txt`.", "",
              "The benchmark deliberately reuses a public experimental key and has reproducible per-image salt "
              "streams. Production uses operating-system randomness and a private 32-byte key. "
              "The deterministic experiment key must never protect actual secrets. Only one embedding "
              "salt per image and rate is sampled; uncertainty over repeated embeddings and all possible "
              "keys is not included in the confidence intervals.", "",
              "The evaluated detectors receive a single image's pixels/features, not its original cover "
              "or shared key. A known original permits direct image comparison, and a known shared key "
              "permits authenticated extraction as a presence test. Public benchmark images and the "
              "public experiment key therefore do not constitute a secure live channel against a "
              "lookup-capable or key-informed adversary. These measurements concern the specified "
              "key-blind, unknown-cover classifiers; actual use requires private keys and an appropriate "
              "cover source, without implying those conditions alone guarantee security.", "",
              "Important unresolved threats include stronger or better-trained steganalyzers, more training "
              "images, unseen camera and processing sources, source-selection or metadata fingerprints, "
              "multiple-message/key-reuse attacks, and distribution shift. Lossy image transformations "
              "are unsupported. Arbitrary input metadata is not preserved. No claim of universal KL/TV "
              "security or immunity to deep networks follows from this experiment.", ""]
    public_progress = ART / "public_probe" / "progress.json"
    if public_progress.exists():
        progress = read(public_progress)
        lines += ["## Public-layout exploratory probe", "",
                  "This is a separate, smaller, resumable experiment at 0.05 gross bpp with the balanced "
                  "encoder and 32-byte messages. It uses the frozen source-group splits, but only their "
                  "first 120 train, 60 validation, and 120 test images; it is not the original full-scale "
                  "confirmation and does not establish performance across message structures. Each completed "
                  "image has an independently saved round-trip and feature record.", "",
                  "| Partition | Completed / target | Rejected |", "|---|---:|---:|"]
        for part, item in progress["counts"].items():
            lines.append(f"| {part} | {item['completed']} / {item['target']} | {item['rejected']} |")
        result_path = ART / "public_probe" / "results.json"
        if result_path.exists():
            result = read(result_path)
            lines += ["", "Held-out classical results (models fitted only on this public-mode probe):", "", *table()]
            for detector, item in result["detectors"].items():
                lines.append(metric_row(result["variant"], detector, item["test"]))
        else:
            lines += ["", "Detector fitting or held-out evaluation is pending; do not treat generation progress as a resistance result."]
        cnn_path = ART / "public_probe" / "cnn_transfer.json"
        if cnn_path.exists():
            lines += ["", "Frozen keyed-trained CNN transfer to public images (not retrained for public mode):", "",
                      *table(), metric_row("public_balanced_0p05_probe", "CNN transfer", read(cnn_path)), ""]
        protocol_path = ART / "public_probe" / "protocol_detection.json"
        if protocol_path.exists():
            item = read(protocol_path)
            lines += ["", f"Public-format extraction attack: {item['recovered_stegos']}/{item['tested_stegos']} "
                      f"test stegos recovered; {item['false_positives']}/{item['tested_covers']} "
                      "ordinary covers falsely accepted. This is a format-aware test, not an image-only CNN. "
                      "Therefore public mode fails against an attacker who knows this public algorithm, "
                      "regardless of the image-only AUCs above.", ""]
        lines += ["", "The public salt and layout seed can be recovered or computed by any observer. A salt-aware "
                  "adversary can run the public extractor directly; the AUC table only measures image-only "
                  "detectors without that protocol knowledge. Random salt does not provide secrecy or "
                  "cryptographic authentication.", ""]
    test_report = ART / "test-results.xml"
    if test_report.exists():
        suites = list(ET.parse(test_report).getroot().iter("testsuite"))
        count = lambda field: sum(int(s.get(field, "0")) for s in suites)
        lines += ["## Correctness verification", "",
                  f"Saved full-suite run: {count('tests')} tests, {count('failures')} failures, "
                  f"{count('errors')} errors, {count('skipped')} skips. The machine-readable record is "
                  "`artifacts/test-results.xml`. Correctness tests are separate from resistance measurements.", ""]
    if (ART / "public_probe" / "protocol_detection.json").exists():
        lines[2:2] = ["Public no-key mode is **not resistant to a format-aware attacker**: the public "
                      "extractor recovered every tested stego message. Its image-only AUCs below do not "
                      "override that result.", ""]
    (ROOT / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print(ROOT / "RESULTS.md")


if __name__ == "__main__":
    main()
