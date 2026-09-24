"""Reproducible, resumable data generation and independently held-out steganalysis."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import time

# Avoid nested BLAS/OpenMP parallelism in image workers.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import joblib
import numpy as np
from PIL import Image
from threadpoolctl import threadpool_limits

from stegolab.balance import balance_signs
from stegolab.costs import compute_costs
from stegolab.evaluation import fit_detectors, metrics, predict
from stegolab.features import extract_features
from stegolab.primitives import Stream
from stegolab.system import Profile, decode_png, embed_pixels, encode_png, extract_pixels

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
DATA = ROOT / "data"
BENCH_KEY = hashlib.sha256(b"PUBLIC BENCHMARK KEY - NEVER USE FOR PRIVATE MESSAGES").digest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def save_array(path, value):
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("wb") as stream:
        np.save(stream, value)
    temporary.replace(path)


def prepare(enrich=False):
    output = ARTIFACTS / "manifest.json"
    previous_manifest = json.loads(output.read_text()) if output.exists() else None
    if previous_manifest is not None and not enrich:
        raise SystemExit("A frozen manifest already exists; refusing to change its splits")
    files = sorted((DATA / "bossbase").glob("*.pgm"), key=lambda p: int(p.stem))
    if len(files) != 10000:
        raise ValueError("Expected the complete 10,000-image BOSSbase source")
    parent = list(range(len(files)))
    hashes, buckets, digests = [], {}, {}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)
    for i, file in enumerate(files):
        with Image.open(file) as image:
            if image.mode != "L" or image.size != (512, 512):
                raise ValueError(f"Unexpected source image: {file}")
            small = np.array(image.resize((9, 8), Image.Resampling.BILINEAR))
            signature = int.from_bytes(np.packbits(small[:, 1:] > small[:, :-1]).tobytes(), "big")
            digest = hashlib.sha256(image.tobytes()).hexdigest()
        if digest in digests:
            join(i, digests[digest])
        digests[digest] = i
        # Five disjoint bands: <=4 bit differences must leave one band equal.
        candidates = set()
        for band in range(5):
            token = (band, (signature >> (13 * band)) & 8191)
            candidates.update(buckets.get(token, []))
        for previous in candidates:
            if (signature ^ hashes[previous]).bit_count() <= 4:
                join(i, previous)
        for band in range(5):
            token = (band, (signature >> (13 * band)) & 8191)
            buckets.setdefault(token, []).append(i)
        hashes.append(signature)
        if (i + 1) % 2000 == 0:
            print(f"grouped {i+1}/10000 source images", flush=True)
    groups = {}
    for i, file in enumerate(files):
        groups.setdefault(find(i), []).append(file.stem)
    ordered = sorted(groups.values(), key=lambda g: hashlib.sha256(("split-93191:" + g[0]).encode()).digest())
    parts = {"train": [], "validation": [], "test": [], "reserve": []}
    targets = {"train": 1200, "validation": 400, "test": 1000}
    for group in ordered:
        part = next((p for p in targets if len(parts[p]) < targets[p]), "reserve")
        parts[part].extend(group)
    record = {"seed": 93191, "parts": parts, "near_duplicate_groups": len(groups),
              "group_ids": {file.stem: str(find(i)) for i, file in enumerate(files)},
              "grouping": "Exact pixel hashes and 64-bit dHash connected components within Hamming distance 4",
              "known_limit": "Camera/session labels are unavailable; grouping cannot prove scene independence",
              "target": {"auc_upper_95": .55, "deep_results_separate": True},
              "candidate_rates": ["0.05", "0.025", "0.01", "0.005"],
              "candidate_strategies": ["baseline", "balanced"],
              "source": json.loads((DATA / "dataset.json").read_text())}
    if enrich:
        write_json(ARTIFACTS / "source_group_ids.json", record["group_ids"])
        if previous_manifest is None or previous_manifest["parts"] != record["parts"]:
            raise ValueError("Group enrichment must preserve every frozen split exactly")
        previous_manifest["group_ids"] = record["group_ids"]
        record = previous_manifest
    write_json(output, record)
    print({p: len(ids) for p, ids in parts.items()}, flush=True)


def features_with_container(image, encoded=None):
    encoded = encode_png(image) if encoded is None else encoded
    return np.r_[extract_features(image), len(encoded) / image.size].astype(np.float32)


def image_job(identifier, rate):
    folder = ARTIFACTS / "samples" / identifier
    folder.mkdir(parents=True, exist_ok=True)
    rate_tag = rate.replace(".", "p")
    complete = folder / f"{rate_tag}.json"
    if complete.exists():
        return json.loads(complete.read_text())
    started = time.perf_counter()
    with Image.open(DATA / "bossbase" / f"{identifier}.pgm") as source:
        cover = np.array(source)
    if not (folder / "cover_features.npy").exists():
        save_array(folder / "cover.npy", cover)
        save_array(folder / "cover_features.npy", features_with_container(cover))
        rng = np.random.default_rng(int(identifier) + 721)
        control = cover.copy()
        selected = rng.random(cover.shape) < .4
        control[selected] = ((cover[selected] & 254)
                             | rng.integers(0, 2, np.count_nonzero(selected), dtype=np.uint8))
        save_array(folder / "control.npy", control)
        save_array(folder / "control_features.npy", features_with_container(control))
    # Reproducible experiment randomness, separated from the production OS CSPRNG.
    stream = Stream(hashlib.sha256(f"experiment-salt:{identifier}:{rate}".encode()).digest())
    message = hashlib.sha256(f"payload:{identifier}".encode()).digest()
    try:
        stego, information = embed_pixels(cover, message, BENCH_KEY, Profile(rate),
                                          random_bytes=stream.take)
    except ValueError as exc:
        record = {"image": identifier, "rate": rate, "failure": str(exc)}
        write_json(complete, record)
        return record
    encoded = encode_png(stego)
    assert np.array_equal(decode_png(encoded), stego)
    resolved = Profile(information["rate"])
    assert extract_pixels(decode_png(encoded), BENCH_KEY, resolved) == message
    save_array(folder / f"baseline_{rate_tag}.npy", stego)
    save_array(folder / f"baseline_{rate_tag}_features.npy", features_with_container(stego, encoded))
    balanced, balance_info = balance_signs(cover, stego)
    encoded_balanced = encode_png(balanced)
    assert np.array_equal(decode_png(encoded_balanced), balanced)
    assert extract_pixels(decode_png(encoded_balanced), BENCH_KEY, resolved) == message
    save_array(folder / f"balanced_{rate_tag}.npy", balanced)
    save_array(folder / f"balanced_{rate_tag}_features.npy", features_with_container(balanced, encoded_balanced))
    record = {"image": identifier, **information, **balance_info,
              "verified_round_trips": 2, "job_seconds": time.perf_counter() - started}
    write_json(complete, record)
    return record


def generate(args):
    manifest = json.loads((ARTIFACTS / "manifest.json").read_text())
    parts = ["train", "validation"] if args.part == "development" else [args.part]
    identifiers = sum((manifest["parts"][part] for part in parts), [])
    if args.limit:
        identifiers = identifiers[:args.limit]
    started, failures = time.monotonic(), 0
    pending = identifiers
    completed_before = 0
    if args.rate == "auto":
        pending = [identifier for identifier in identifiers
                   if not (ARTIFACTS / "samples" / identifier / "auto.json").exists()]
        completed_before = len(identifiers) - len(pending)
        pending_ids = set(pending)
        failures = sum("failure" in json.loads((ARTIFACTS / "samples" / identifier / "auto.json").read_text())
                       for identifier in identifiers if identifier not in pending_ids)
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(image_job, identifier, args.rate): identifier for identifier in pending}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            failures += int("failure" in result)
            if i % 20 == 0 or i == len(futures):
                if args.rate == "auto":
                    status_path = ARTIFACTS / "auto_rate_progress.json"
                    status = json.loads(status_path.read_text()) if status_path.exists() else {"parts": {}}
                    status["parts"][args.part] = {"completed": completed_before + i,
                                                  "target": len(identifiers), "failures": failures}
                    write_json(status_path, status)
                if args.rate == "auto" and (i % 100 == 0 or i == len(futures)):
                    from report_results import main as report_results
                    report_results()
                print(f"rate={args.rate} {args.part} {completed_before+i}/{len(identifiers)} failures={failures} "
                      f"elapsed={time.monotonic()-started:.1f}s", flush=True)
    if args.rate == "auto" and not pending:
        status_path = ARTIFACTS / "auto_rate_progress.json"
        status = json.loads(status_path.read_text()) if status_path.exists() else {"parts": {}}
        status["parts"][args.part] = {"completed": len(identifiers), "target": len(identifiers),
                                      "failures": failures}
        write_json(status_path, status)
        from report_results import main as report_results
        report_results()


def load_part(manifest, part, variant):
    cover, stego, ids, accepted, failures = [], [], [], [], []
    for identifier in manifest["parts"][part]:
        folder = ARTIFACTS / "samples" / identifier
        candidate = folder / f"{variant}_features.npy"
        if not (folder / "cover_features.npy").exists():
            raise ValueError(f"Image {identifier} has not been generated")
        cover.append(np.load(folder / "cover_features.npy"))
        ids.append(identifier)
        if candidate.exists():
            stego.append(np.load(candidate))
            accepted.append(identifier)
        else:
            rate_tag = variant.rsplit("_", 1)[-1]
            record_path = folder / f"{rate_tag}.json"
            record = json.loads(record_path.read_text()) if record_path.exists() else {}
            if "failure" not in record:
                raise ValueError(f"Missing generated candidate {identifier}/{variant}")
            failures.append(identifier)
    if len(cover) < 40:
        raise ValueError(f"Only {len(cover)} usable {part} pairs for {variant}")
    return np.array(cover), np.array(stego), ids, accepted, failures


def evaluate(args):
    manifest = json.loads((ARTIFACTS / "manifest.json").read_text())
    folder = ARTIFACTS / "models" / args.variant
    folder.mkdir(parents=True, exist_ok=True)
    train_c, train_s, train_ids, train_accepted, train_rejected = load_part(manifest, "train", args.variant)
    val_c, val_s, val_ids, val_accepted, val_rejected = load_part(manifest, "validation", args.variant)
    def groups(cover_ids, stego_ids):
        return ([manifest["group_ids"][i] for i in cover_ids],
                [manifest["group_ids"][i] for i in stego_ids])
    with threadpool_limits(limits=2):
        if args.final:
            if not (folder / "models.joblib").exists():
                raise ValueError("Freeze validation-trained models before final evaluation")
            models = joblib.load(folder / "models.joblib")
        else:
            models = fit_detectors(train_c, train_s, val_c, val_s,
                                   groups=groups(val_ids, val_accepted))
            joblib.dump(models, folder / "models.joblib")
        record = {"variant": args.variant, "train_covers": len(train_ids), "train_stegos": len(train_accepted),
                  "train_rejections": train_rejected, "validation_rejections": val_rejected,
                  "validation_covers": len(val_ids), "validation_stegos": len(val_accepted),
                  "features": train_c.shape[1],
                  "detectors": {name: {k: v for k, v in model.items() if k != "model"}
                                for name, model in models.items()}}
        if not args.final:
            for name, model in models.items():
                c, s = predict(model, val_c, val_s)
                np.savez(folder / f"{name}_validation_predictions.npz", cover=c, stego=s,
                         cover_ids=np.array(val_ids), stego_ids=np.array(val_accepted))
        if args.final:
            test_c, test_s, ids, accepted, rejected = load_part(manifest, "test", args.variant)
            record["test_rejections"] = rejected
            for name, model in models.items():
                c, s = predict(model, test_c, test_s)
                record["detectors"][name]["test"] = metrics(c, s, model["threshold"], model["low_fpr_threshold"],
                                                           groups=groups(ids, accepted))
                selected = np.array([i for i, identifier in enumerate(ids) if identifier in set(accepted)])
                record["detectors"][name]["test_conditional_on_acceptance"] = metrics(
                    c[selected], s, model["threshold"], model["low_fpr_threshold"],
                    groups=groups(accepted, accepted))
                np.savez(folder / f"{name}_test_predictions.npz", cover=c, stego=s,
                         cover_ids=np.array(ids), stego_ids=np.array(accepted))
        output = folder / ("final.json" if args.final else "validation.json")
        write_json(output, record)
        print(json.dumps(record, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--enrich-groups", action="store_true")
    gen = sub.add_parser("generate")
    gen.add_argument("--part", choices=["development", "train", "validation", "test", "reserve"], default="development")
    gen.add_argument("--rate", default="0.05")
    gen.add_argument("--workers", type=int, default=6)
    gen.add_argument("--limit", type=int)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--variant", required=True)
    ev.add_argument("--final", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.enrich_groups)
    elif args.command == "generate":
        generate(args)
    else:
        evaluate(args)


if __name__ == "__main__":
    main()
