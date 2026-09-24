# Measured steganography results

Public no-key mode is **not resistant to a format-aware attacker**: the public extractor recovered every tested stego message. Its image-only AUCs below do not override that result.

The frozen **balanced_0p05** candidate **met the provisional target against the evaluated detectors** on the final holdout. Largest classical upper bound: 0.5204; neural upper bound: 0.5041. Held-out positive-control sensitivity gate: passed.

This report is generated from saved experiment artifacts. A pass is evidence only against the evaluated detector, its fitted model, this image source, and the tested payload profile. It is not a proof of statistical indistinguishability.

## Acceptance rule

The agreed provisional target is ROC-AUC at most 0.55. The conservative operational rule requires a paired source-group bootstrap 95% interval contained in [0.45, 0.55], accounting for either score direction. Neural results are reported separately. Intervals are per detector, not familywise; training-procedure uncertainty is not included.

An interval entirely above 0.5 still demonstrates a detectable signal, even if it passes the provisional 0.55 bound. This rule is not a test that proves exact equality of cover and stego distributions, and it does not certify repeated-image or aggregate-channel security.

## Source and split

The source contains 10,000 native 512-by-512 grayscale photographic rasters. No resizing or pixel conversion is used. Cover and stego PNGs use an identical serializer. Exact duplicates and approximate difference-hash neighbors are grouped before splitting.

Partitions: train=1200, validation=400, test=1000, reserve=7400. Source groups: 9703.

Camera/session labels are unavailable; the split does not establish unseen-camera generalization. The manifest and source archive checksum are retained in `artifacts/manifest.json` and `data/dataset.json`.

## Selection

Frozen candidate: **balanced_0p05**.

The full decision record, including validation evidence and the scope of selection, is in `artifacts/selection.json`.

At the largest predeclared rate, 0.05 gross bpp, both sender strategies passed the classical validation gate. Balancing was chosen because its worst validation upper confidence bound was lower: 0.5273, versus 0.5433 for the baseline. This choice was frozen before final-test detector scores were computed. Lower-rate experiments are supplementary capacity comparisons, not evidence used to choose a different encoder after looking at the final test.

## Development measurements

Validation is used for encoder comparison, score orientation, decision thresholds, and neural checkpoint selection. It is not the independent final confirmation.

| Variant | Detector | AUC | Group-bootstrap 95% interval | Either-direction upper bound | Equal-prior error | Target |
|---|---|---:|---|---:|---:|---|
| balanced_0p01 | adjacent_bin_chisquare | 0.5025 | [0.5007, 0.5056] | 0.5056 | 0.4942 | pass |
| balanced_0p01 | rs_like_regularity | 0.5025 | [0.4998, 0.5063] | 0.5063 | 0.4952 | pass |
| balanced_0p01 | residual_subspace_ensemble | 0.5054 | [0.4997, 0.5120] | 0.5120 | 0.4906 | pass |
| balanced_0p01 | residual_extra_trees | 0.5072 | [0.4942, 0.5194] | 0.5194 | 0.4795 | pass |
| balanced_0p05 | adjacent_bin_chisquare | 0.5042 | [0.5018, 0.5078] | 0.5078 | 0.4910 | pass |
| balanced_0p05 | rs_like_regularity | 0.5037 | [0.5000, 0.5085] | 0.5085 | 0.4941 | pass |
| balanced_0p05 | residual_subspace_ensemble | 0.5150 | [0.5105, 0.5213] | 0.5213 | 0.4843 | pass |
| balanced_0p05 | residual_extra_trees | 0.5101 | [0.4929, 0.5273] | 0.5273 | 0.4695 | pass |
| baseline_0p01 | adjacent_bin_chisquare | 0.5026 | [0.5008, 0.5057] | 0.5057 | 0.4942 | pass |
| baseline_0p01 | rs_like_regularity | 0.5025 | [0.5000, 0.5064] | 0.5064 | 0.4952 | pass |
| baseline_0p01 | residual_subspace_ensemble | 0.5052 | [0.5008, 0.5118] | 0.5118 | 0.4878 | pass |
| baseline_0p01 | residual_extra_trees | 0.5011 | [0.4887, 0.5129] | 0.5129 | 0.4827 | pass |
| baseline_0p05 | adjacent_bin_chisquare | 0.5044 | [0.5020, 0.5079] | 0.5079 | 0.4922 | pass |
| baseline_0p05 | rs_like_regularity | 0.5043 | [0.5011, 0.5095] | 0.5095 | 0.4929 | pass |
| baseline_0p05 | residual_subspace_ensemble | 0.5257 | [0.5196, 0.5346] | 0.5346 | 0.4729 | pass |
| baseline_0p05 | residual_extra_trees | 0.5270 | [0.5111, 0.5433] | 0.5433 | 0.4700 | pass |
| control | adjacent_bin_chisquare | 0.7184 | [0.7039, 0.7358] | 0.7358 | 0.3275 | control |
| control | rs_like_regularity | 0.8160 | [0.7962, 0.8361] | 0.8361 | 0.2450 | control |
| control | residual_subspace_ensemble | 0.9919 | [0.9880, 0.9950] | 0.9950 | 0.0475 | control |
| control | residual_extra_trees | 0.9987 | [0.9976, 0.9995] | 0.9995 | 0.0163 | control |

## Independent final measurements

| Variant | Detector | AUC | Group-bootstrap 95% interval | Either-direction upper bound | Equal-prior error | Target |
|---|---|---:|---|---:|---:|---|
| balanced_0p05 | adjacent_bin_chisquare | 0.5022 | [0.5013, 0.5038] | 0.5038 | 0.4996 | pass |
| balanced_0p05 | rs_like_regularity | 0.5008 | [0.4998, 0.5023] | 0.5023 | 0.4996 | pass |
| balanced_0p05 | residual_subspace_ensemble | 0.5130 | [0.5103, 0.5163] | 0.5163 | 0.4932 | pass |
| balanced_0p05 | residual_extra_trees | 0.5091 | [0.4985, 0.5204] | 0.5204 | 0.5005 | pass |
| baseline_0p05 | adjacent_bin_chisquare | 0.5023 | [0.5013, 0.5039] | 0.5039 | 0.4981 | pass |
| baseline_0p05 | rs_like_regularity | 0.5012 | [0.5003, 0.5028] | 0.5028 | 0.4996 | pass |
| baseline_0p05 | residual_subspace_ensemble | 0.5218 | [0.5182, 0.5262] | 0.5262 | 0.4851 | pass |
| baseline_0p05 | residual_extra_trees | 0.5112 | [0.5011, 0.5225] | 0.5225 | 0.4933 | pass |
| control | adjacent_bin_chisquare | 0.7037 | [0.6948, 0.7134] | 0.7134 | 0.3545 | control |
| control | rs_like_regularity | 0.8154 | [0.8040, 0.8296] | 0.8296 | 0.2665 | control |
| control | residual_subspace_ensemble | 0.9892 | [0.9862, 0.9919] | 0.9919 | 0.0610 | control |
| control | residual_extra_trees | 0.9981 | [0.9971, 0.9989] | 0.9989 | 0.0230 | control |

### Same-rate ablation

Both variants use the same test covers, payloads, and changed-pixel locations. Only modification signs differ; each detector is trained separately for its variant. The paired source-group interval below measures balanced-minus-baseline AUC with score directions frozen on validation. Negative values mean a lower AUC in that fixed direction; use the either-direction bounds above to rule out misleading reversals.

| Detector | AUC difference | Paired group-bootstrap 95% interval |
|---|---:|---|
| adjacent_bin_chisquare | -0.0001 | [-0.0002, +0.0001] |
| rs_like_regularity | -0.0004 | [-0.0006, -0.0004] |
| residual_subspace_ensemble | -0.0088 | [-0.0125, -0.0055] |
| residual_extra_trees | -0.0021 | [-0.0174, +0.0117] |

The paired interval supports a reduction in validation-oriented AUC for `rs_like_regularity`, `residual_subspace_ensemble`.

The paired interval includes zero for `adjacent_bin_chisquare`, `residual_extra_trees`; a measurable improvement is not established for those detectors. This is not evidence of a uniform improvement across all steganalyzers. No same-rate neural baseline ablation was run.

The primary table includes every ordinary cover and only successfully emitted stegos. Accepted-cover-only results, validation-calibrated low-FPR operating points, and image-level predictions are retained in each model's JSON/NPZ artifacts.

## Neural detector

The neural model is a compact 30,929-parameter high-pass residual CNN trained locally on CPU. It is not a full SRNet reproduction or an exhaustive modern-steganalysis evaluation. Inference averages four quadrants covering every image pixel.

| Variant | Detector | AUC | Group-bootstrap 95% interval | Either-direction upper bound | Equal-prior error | Target |
|---|---|---:|---|---:|---:|---|
| balanced_0p05 | CNN validation, epoch 15 | 0.5053 | [0.5022, 0.5101] | 0.5101 | 0.4903 | pass |
| balanced_0p05 | CNN final | 0.5023 | [0.5012, 0.5041] | 0.5041 | 0.4999 | pass |
| control | CNN validation, epoch 9 | 0.9965 | [0.9942, 0.9982] | 0.9982 | 0.0300 | control |
| control | CNN final | 0.9964 | [0.9949, 0.9976] | 0.9976 | 0.0365 | control |

The intentionally detectable control uses 0.4-bpp random LSB replacement. A successful control demonstrates basic detector functionality, not sufficient power against every low-rate adaptive signal. Its desired result is high AUC, not the low-detection target. The residual-feature and neural controls must have a lower AUC confidence bound above 0.75. A failed control makes the corresponding security conclusion inconclusive.

## Embedding behavior

Every admitted sample is actually encoded, serialized to PNG, decoded, and authenticated. Both baseline and balanced variants must recover the original message; a simulator is not used. The sign-only extension preserves change positions, parity, unit-change magnitude, additive distortion, and PSNR. Its histogram-objective decrease is not a detection metric.

| Partition | Gross bpp | Completed covers | Rejected | Mean changed pixels | Mean PSNR (dB) | Mean objective before / after |
|---|---:|---:|---:|---:|---:|---|
| train | 0.01 | 1200 | 0 | 387.49 | 76.46 | 20.530 / 7.168 |
| train | 0.05 | 1200 | 6 | 2346.19 | 68.64 | 178.934 / 18.303 |
| validation | 0.01 | 400 | 2 | 390.46 | 76.44 | 20.008 / 7.361 |
| validation | 0.05 | 400 | 3 | 2356.81 | 68.62 | 204.809 / 20.596 |
| test | 0.05 | 1000 | 2 | 2343.10 | 68.64 | 178.104 / 19.237 |

At 512-by-512 pixels, stored message capacities before possible compression gains are 1,572 bytes at 0.05 gross bpp, 753 bytes at 0.025, 261 bytes at 0.01, and 97 bytes at 0.005. Salt, authentication, framing, and padding are included in the gross rate. Protected image regions can cause admission failures independently of nominal capacity.

## Reproducibility and limits

Implementation and commands: `README.md`. Original specification: `steganography_master_blueprint.md`. Experimental objective and invariants: `DESIGN_EXTENSION.md`. Split and decision rules: `EXPERIMENT_PROTOCOL.md`. Runtime versions and implementation hashes: `artifacts/environment.json`. Exact installed Python dependencies: `requirements-research.lock.txt`.

The benchmark deliberately reuses a public experimental key and has reproducible per-image salt streams. Production uses operating-system randomness and a private 32-byte key. The deterministic experiment key must never protect actual secrets. Only one embedding salt per image and rate is sampled; uncertainty over repeated embeddings and all possible keys is not included in the confidence intervals.

The evaluated detectors receive a single image's pixels/features, not its original cover or shared key. A known original permits direct image comparison, and a known shared key permits authenticated extraction as a presence test. Public benchmark images and the public experiment key therefore do not constitute a secure live channel against a lookup-capable or key-informed adversary. These measurements concern the specified key-blind, unknown-cover classifiers; actual use requires private keys and an appropriate cover source, without implying those conditions alone guarantee security.

Important unresolved threats include stronger or better-trained steganalyzers, more training images, unseen camera and processing sources, source-selection or metadata fingerprints, multiple-message/key-reuse attacks, and distribution shift. Lossy image transformations are unsupported. Arbitrary input metadata is not preserved. No claim of universal KL/TV security or immunity to deep networks follows from this experiment.

## Public-layout exploratory probe

This is a separate, smaller, resumable experiment at 0.05 gross bpp with the balanced encoder and 32-byte messages. It uses the frozen source-group splits, but only their first 120 train, 60 validation, and 120 test images; it is not the original full-scale confirmation and does not establish performance across message structures. Each completed image has an independently saved round-trip and feature record.

| Partition | Completed / target | Rejected |
|---|---:|---:|
| train | 120 / 120 | 1 |
| validation | 60 / 60 | 0 |
| test | 120 / 120 | 0 |

Held-out classical results (models fitted only on this public-mode probe):

| Variant | Detector | AUC | Group-bootstrap 95% interval | Either-direction upper bound | Equal-prior error | Target |
|---|---|---:|---|---:|---:|---|
| public_balanced_0p05_probe | adjacent_bin_chisquare | 0.5031 | [0.5011, 0.5075] | 0.5075 | 0.5000 | pass |
| public_balanced_0p05_probe | rs_like_regularity | 0.4999 | [0.4970, 0.5023] | 0.5030 | 0.5042 | pass |
| public_balanced_0p05_probe | residual_subspace_ensemble | 0.5144 | [0.5031, 0.5290] | 0.5290 | 0.4958 | pass |
| public_balanced_0p05_probe | residual_extra_trees | 0.5139 | [0.4893, 0.5407] | 0.5407 | 0.4792 | pass |

Frozen keyed-trained CNN transfer to public images (not retrained for public mode):

| Variant | Detector | AUC | Group-bootstrap 95% interval | Either-direction upper bound | Equal-prior error | Target |
|---|---|---:|---|---:|---:|---|
| public_balanced_0p05_probe | CNN transfer | 0.5035 | [0.5024, 0.5083] | 0.5083 | 0.5000 | pass |


Public-format extraction attack: 120/120 test stegos recovered; 0/40 ordinary covers falsely accepted. This is a format-aware test, not an image-only CNN. Therefore public mode fails against an attacker who knows this public algorithm, regardless of the image-only AUCs above.


The public salt and layout seed can be recovered or computed by any observer. A salt-aware adversary can run the public extractor directly; the AUC table only measures image-only detectors without that protocol knowledge. Random salt does not provide secrecy or cryptographic authentication.

## Correctness verification

Saved full-suite run: 19 tests, 0 failures, 0 errors, 0 skips. The machine-readable record is `artifacts/test-results.xml`. Correctness tests are separate from resistance measurements.
