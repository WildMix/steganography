"""Resumable, disjoint-split public-layout probe at the existing 0.05-bpp profile."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
from PIL import Image
from threadpoolctl import threadpool_limits

from experiment import ARTIFACTS, DATA, features_with_container, save_array, write_json
from stegolab.evaluation import fit_detectors, metrics, predict
from stegolab.primitives import Stream
from stegolab.system import Profile, decode_png, embed_pixels, encode_png, extract_pixels

ROOT = Path(__file__).resolve().parents[1]
OUT = ARTIFACTS / "public_probe"
RATE = "0.05"
COUNTS = {"train": 120, "validation": 60, "test": 120}


def job(identifier):
    folder = OUT / "samples" / identifier
    complete = folder / "result.json"
    if complete.exists():
        return json.loads(complete.read_text(encoding="utf-8"))
    folder.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with Image.open(DATA / "bossbase" / f"{identifier}.pgm") as source:
        cover = np.array(source)
    message = hashlib.sha256(f"payload:{identifier}".encode()).digest()
    # Reproducible only for research; production draws salt from the OS CSPRNG.
    stream = Stream(hashlib.sha256(f"public-probe-salt:{identifier}:{RATE}".encode()).digest())
    try:
        stego, info = embed_pixels(cover, message, None, Profile(RATE),
                                   strategy="balanced", random_bytes=stream.take)
        encoded = encode_png(stego)
        assert np.array_equal(decode_png(encoded), stego)
        assert extract_pixels(decode_png(encoded), None, Profile(RATE)) == message
        features = features_with_container(stego, encoded)
        save_array(folder / "features.npy", features)
        result = {"image": identifier, "round_trip": True, **info,
                  "job_seconds": time.perf_counter() - started}
    except ValueError as exc:
        result = {"image": identifier, "failure": str(exc)}
    write_json(complete, result)
    return result


def ids_by_part(manifest):
    return {part: manifest["parts"][part][:count] for part, count in COUNTS.items()}


def progress(manifest):
    counts = {}
    for part, ids in ids_by_part(manifest).items():
        records = [OUT / "samples" / identifier / "result.json" for identifier in ids]
        done = [json.loads(p.read_text(encoding="utf-8")) for p in records if p.exists()]
        counts[part] = {"completed": len(done), "target": len(ids),
                        "rejected": sum("failure" in item for item in done)}
    write_json(OUT / "progress.json", {"rate": RATE, "strategy": "balanced",
                                       "payload": "32 deterministic SHA-256 bytes per image",
                                       "counts": counts})
    # Refresh the human-readable report after each durable batch.
    from report_results import main as report_results
    report_results()


def generate(manifest, workers):
    ids = [identifier for group in ids_by_part(manifest).values() for identifier in group]
    progress(manifest)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(job, identifier): identifier for identifier in ids
                   if not (OUT / "samples" / identifier / "result.json").exists()}
        for number, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if number % 10 == 0 or number == len(futures):
                progress(manifest)
                print(f"public probe {number}/{len(futures)} new jobs; latest={result['image']}", flush=True)


def load(manifest, part):
    cover, stego, kept, rejected = [], [], [], []
    for identifier in ids_by_part(manifest)[part]:
        folder = OUT / "samples" / identifier
        record_path = folder / "result.json"
        if not record_path.exists():
            raise ValueError(f"Missing public probe sample {part}/{identifier}")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if "failure" in record:
            rejected.append(identifier)
            continue
        cover.append(np.load(ARTIFACTS / "samples" / identifier / "cover_features.npy"))
        stego.append(np.load(folder / "features.npy"))
        kept.append(identifier)
    return np.array(cover), np.array(stego), kept, rejected


def evaluate(manifest):
    train_c, train_s, train_ids, train_rejected = load(manifest, "train")
    val_c, val_s, val_ids, val_rejected = load(manifest, "validation")
    test_c, test_s, test_ids, test_rejected = load(manifest, "test")
    if min(len(train_ids), len(val_ids), len(test_ids)) < 40:
        raise ValueError("Insufficient admitted pairs")
    group_ids = manifest["group_ids"]
    groups = lambda ids: [group_ids[i] for i in ids]
    result = {"variant": "public_balanced_0p05_probe", "rate": RATE,
              "sample_counts": {"train": len(train_ids), "validation": len(val_ids), "test": len(test_ids)},
              "rejections": {"train": train_rejected, "validation": val_rejected, "test": test_rejected},
              "detectors": {}}
    with threadpool_limits(limits=2):
        models = fit_detectors(train_c, train_s, val_c, val_s,
                               groups=(groups(val_ids), groups(val_ids)))
        joblib.dump(models, OUT / "models.joblib")
        for name, model in models.items():
            cover_scores, stego_scores = predict(model, test_c, test_s)
            item = metrics(cover_scores, stego_scores, model["threshold"],
                           model["low_fpr_threshold"], groups=(groups(test_ids), groups(test_ids)))
            result["detectors"][name] = {"validation": model["validation"], "test": item}
            np.savez(OUT / f"{name}_test_predictions.npz", cover=cover_scores, stego=stego_scores,
                     ids=np.array(test_ids))
            write_json(OUT / "results.json", result)
            progress(manifest)
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "evaluate", "all"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    manifest = json.loads((ARTIFACTS / "manifest.json").read_text(encoding="utf-8"))
    if args.command in ("generate", "all"):
        generate(manifest, args.workers)
    if args.command in ("evaluate", "all"):
        evaluate(manifest)


if __name__ == "__main__":
    main()
