"""Paired fresh-process extraction benchmark with resumable per-run checkpoints.

The reference must be a preserved pre-change import root containing stegolab/,
including its native DLL. Inputs are copied, never modified. All keys/messages
created here are PUBLIC research fixtures, not production secrets.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def source_hashes(root):
    return {name: sha((root / "stegolab" / name).read_bytes()) for name in
            ("cli.py", "system.py", "primitives.py", "coding.py", "native/stc.dll")}


def summarize(records):
    grouped = {}
    for record in records:
        grouped.setdefault(record["group"], []).append(record)
    rows = []
    for group, entries in sorted(grouped.items()):
        row = {"group": group, "pairs": len(entries)}
        for metric in ("wall_seconds", "workflow_seconds", "syndrome_seconds"):
            savings = [100 * (1 - entry["after"][metric] / entry["before"][metric]) for entry in entries]
            row[metric] = {
                "median_before": statistics.median(entry["before"][metric] for entry in entries),
                "median_after": statistics.median(entry["after"][metric] for entry in entries),
                "median_paired_saving_percent": statistics.median(savings),
                "paired_saving_range_percent": [min(savings), max(savings)],
                "faster_pairs": sum(value > 0 for value in savings),
            }
        rows.append(row)
    return {"completed_pairs": len(records), "all_recovered_exactly": all(r["verified"] for r in records),
            "groups": rows}


def prepare_inputs(output, fixtures, large_cover):
    # Resume preparation after each fixture, too; no expensive embedding is lost.
    sys.path.insert(0, str(ROOT / "src"))
    from stegolab import primitives, system
    inputs, manifest = output / "inputs", output / "cases.json"
    cases = json.loads(manifest.read_text()) if manifest.exists() else []
    done = {case["id"] for case in cases}
    key = (fixtures / "inputs" / "public_benchmark.key").read_bytes()

    def record(name, group, png, message, rate, keyed):
        image = system.decode_png(png)
        paths = {"image": inputs / f"{name}.png", "message": inputs / f"{name}.bin"}
        paths["image"].write_bytes(png)
        paths["message"].write_bytes(message)
        if keyed:
            paths["key"] = inputs / f"{name}.key"
            paths["key"].write_bytes(key)
        case = {"id": name, "group": group, "rate": str(rate), "width": image.shape[1],
                "height": image.shape[0], "pixels": int(image.size), "message_bytes": len(message),
                "odd_pixels": int((image & 1).sum()),
                "files": {label: str(path) for label, path in paths.items()},
                "sha256": {label: sha(path.read_bytes()) for label, path in paths.items()}}
        cases.append(case)
        save(manifest, cases)
        print(f"Prepared {name}", flush=True)

    for cover, payload in [(c, "hello") for c in ("1883", "4000", "8872")] + [
            ("1883", "binary1024"), ("1883", "compressed")]:
        for rate in (("auto", "0.05") if payload == "hello" else ("auto",)):
            name = f"small_{cover}_{payload}_{rate}"
            if name in done:
                continue
            prefix = f"identity_{cover}_{payload}_{rate}_balanced_after"
            report = json.loads((fixtures / "jobs" / f"{prefix}.result.json").read_text())
            png = (fixtures / "stegos" / f"{prefix}.png").read_bytes()
            assert sha(png) == report["png_sha256"]
            record(name, f"small/keyed/{payload}/{rate}", png,
                   (fixtures / "inputs" / f"{payload}.bin").read_bytes(), report["info"]["rate"], True)

    for size, source, keyed, rate in [
            ("large", large_cover, True, "auto"), ("large", large_cover, True, "0.05"),
            ("large", large_cover, False, "auto"),
            ("small", fixtures / "inputs" / "1883.png", False, "auto")]:
        name = f"{size}_{'keyed' if keyed else 'public'}_{rate}"
        if name in done:
            continue
        cover = system.decode_png(source.read_bytes())
        # Determinism is ONLY for these published timing fixtures.
        stego, info = system.embed_pixels(cover, b"HELLO", key if keyed else None,
                                         system.Profile(rate), strategy="balanced",
                                         random_bytes=random.Random(4517).randbytes)
        record(name, f"{size}/{'keyed' if keyed else 'public'}/hello/{rate}",
               system.encode_png(stego), b"HELLO", info["rate"], keyed)
        for function in (primitives.columns, primitives.split_positions, primitives.body_positions):
            function.cache_clear()
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fixtures", type=Path,
                        default=ROOT / "artifacts/runtime_exact/20260926/comparison")
    parser.add_argument("--large-cover", type=Path, default=ROOT / "atene_gray.png")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    output = args.output.resolve()
    if output.exists() and not args.resume:
        parser.error("Output exists; use a new directory or --resume")
    for directory in (output, output / "inputs", output / "runs"):
        directory.mkdir(parents=True, exist_ok=True)
    implementations = {"before": args.reference.resolve(), "after": ROOT / "src"}
    metadata = {"implementations": {label: str(root) for label, root in implementations.items()},
                "sha256": {label: source_hashes(root) for label, root in implementations.items()},
                "script_sha256": sha(Path(__file__).read_bytes()), "repeats": args.repeats,
                "fixtures": str(args.fixtures.resolve()), "large_cover": str(args.large_cover.resolve()),
                "large_cover_sha256": sha(args.large_cover.read_bytes()),
                "python": sys.version, "platform": platform.platform(),
                "processor": platform.processor(),
                "method": "Fresh CLI processes; paired alternating order; warm filesystem; no outlier removal. "
                          "Wall timer includes interpreter/imports/I/O/logs/process exit. Workflow/stage "
                          "timers come from normal CLI JSON logs. Every recovered message checked exactly."}
    metadata_path = output / "metadata.json"
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text())
        assert all(previous[field] == value for field, value in metadata.items()), "Inputs/source changed; use a new output directory"
    else:
        save(metadata_path, {**metadata, "utc": datetime.now(timezone.utc).isoformat()})
    os.environ["STEGOLAB_NATIVE_PRIMITIVES"] = "1"
    os.environ["STEGOLAB_NATIVE_EXTRACT"] = "1"
    cases = prepare_inputs(output, args.fixtures.resolve(), args.large_cover.resolve())
    for case in cases:
        assert all(sha(Path(path).read_bytes()) == case["sha256"][label]
                   for label, path in case["files"].items())
    # An isolated probe proves the reference uses the old DLL and after has the new export.
    environments = {}
    for label, root in implementations.items():
        env = dict(os.environ, PYTHONPATH=str(root), OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        environments[label] = env
        code = ("from stegolab import primitives as p; b=p._native_backend(); "
                "assert b is not None; print(int(hasattr(b,'wire_extract')))")
        probe = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        assert probe.stdout.strip() == ("1" if label == "after" else "0"), "Unexpected native backend"

    def run(case, label, prefix):
        directory = output / "runs" / f"{prefix}_{case['id']}_{label}"
        directory.mkdir(exist_ok=True)
        result_path = directory / "result.json"
        recovered = directory / "recovered.bin"
        expected = Path(case["files"]["message"]).read_bytes()
        if result_path.exists():
            saved = json.loads(result_path.read_text())
            assert Path(saved["recovered"]).read_bytes() == expected
            return saved
        # An interrupted run may have left exclusive CLI destinations; preserve them.
        attempt = 0
        while recovered.exists() or (directory / f"log-{attempt}.json").exists():
            attempt += 1
            recovered = directory / f"recovered-{attempt}.bin"
        log_path = directory / f"log-{attempt}.json"
        command = [sys.executable, "-m", "stegolab.cli", "extract", case["files"]["image"],
                   "--rate", case["rate"], "--output", str(recovered), "--output-logs", str(log_path)]
        if "key" in case["files"]:
            command += ["--key", case["files"]["key"]]
        started = time.perf_counter()
        process = subprocess.run(command, env=environments[label], capture_output=True, text=True)
        elapsed = time.perf_counter() - started
        (directory / f"console-{attempt}.txt").write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            raise RuntimeError(f"Extraction failed; see {directory}")
        assert recovered.read_bytes() == expected
        log = json.loads(log_path.read_text())
        assert log["status"] == "ok"
        syndrome_stages = [stage for stage in log["timings"] if
                           "32-byte salt" in stage["stage"] or
                           "Rebuild body parity matrix" in stage["stage"] or
                           "Recover body syndrome" in stage["stage"]]
        assert len(syndrome_stages) == 2
        result = {"wall_seconds": elapsed, "workflow_seconds": log["seconds"],
                  "syndrome_seconds": sum(stage["seconds"] for stage in syndrome_stages),
                  "recovered": str(recovered), "recovered_sha256": sha(expected),
                  "log": str(log_path), "verified": True}
        save(result_path, result)
        return result

    for label in implementations:
        run(cases[0], label, "warmup")  # Not included in the statistics.
    records_path = output / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()] if records_path.exists() else []
    done = {record["id"] for record in records}
    for repeat in range(args.repeats):
        for index, case in enumerate(cases):
            identity = f"{repeat}_{case['id']}"
            if identity in done:
                continue
            order = ("before", "after") if (repeat + index) % 2 == 0 else ("after", "before")
            result = {label: run(case, label, str(repeat)) for label in order}
            record = {"id": identity, "group": case["group"], "order": order,
                      "verified": True, **result}
            records.append(record)
            with records_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            save(output / "summary.json", summarize(records))
            print(f"{len(records)}/{len(cases) * args.repeats}: {identity}: "
                  f"{result['before']['wall_seconds']:.3f} -> {result['after']['wall_seconds']:.3f} s", flush=True)
    save(output / "summary.json", summarize(records))


if __name__ == "__main__":
    main()
