"""Sequential, checkpointed CLI timing and separate API stage profiling.

Uses real BOSSbase rasters, fresh production salt/padding, and the unmodified
embedding implementation. Never overwrites statistical experiment artifacts.
"""
import argparse
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
from unittest.mock import patch

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
from PIL import Image

from stegolab import balance, coding, primitives, system

ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = {
    "hello_5": b"HELLO",
    "binary_32": hashlib.sha256(b"auto-rate timing 32-byte payload").digest(),
    "binary_1024": hashlib.shake_256(b"auto-rate timing 1024-byte payload").digest(1024),
}
KEY = hashlib.sha256(b"PUBLIC BENCHMARK KEY - never use for private messages").digest()


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(records):
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["kind"], record["strategy"], record["payload"])].append(record)
    groups = []
    for (kind, strategy, payload), rows in sorted(grouped.items()):
        pairs = defaultdict(dict)
        for row in rows:
            pairs[(row["cover"], row["repeat"])][row["rate_option"]] = row
        paired = [pair for pair in pairs.values()
                  if set(pair) == {"0.05", "auto"}
                  and all(row["ok"] for row in pair.values())]
        result = {"kind": kind, "strategy": strategy, "payload": payload,
                  "complete_pairs": len(paired),
                  "failures": sum(not row["ok"] for row in rows), "rates": {}}
        for rate in ("0.05", "auto"):
            selected = [pair[rate] for pair in paired]
            if not selected:
                continue
            times = [row["wall_seconds"] for row in selected]
            entry = {"median_seconds": statistics.median(times),
                     "min_seconds": min(times), "max_seconds": max(times),
                     "median_changed_pixels": statistics.median(row["changed_pixels"] for row in selected),
                     "budgets_bytes": sorted({row["budget_bytes"] for row in selected}),
                     "selected_rates": sorted({row["selected_rate"] for row in selected})}
            if kind == "profile":
                entry["mean_stages_seconds"] = {
                    stage: statistics.mean(row["stages"].get(stage, 0) for row in selected)
                    for stage in sorted(set().union(*(row["stages"] for row in selected)))}
                entry["mean_seconds"] = statistics.mean(times)
                entry["median_cpu_seconds"] = statistics.median(row["cpu_seconds"] for row in selected)
            result["rates"][rate] = entry
        if paired:
            savings = [100 * (pair["0.05"]["wall_seconds"] - pair["auto"]["wall_seconds"])
                       / pair["0.05"]["wall_seconds"] for pair in paired]
            result.update(median_paired_saving_percent=statistics.median(savings),
                          paired_saving_range_percent=[min(savings), max(savings)],
                          auto_faster_pairs=sum(value > 0 for value in savings))
        groups.append(result)
    return {"records": len(records), "failures": sum(not row["ok"] for row in records),
            "groups": groups}


def run_cli(output, cover, payload, rate, token, repeat):
    target = output / "stegos" / f"{token}.png"
    log_report = output / "logs" / f"{token}.json"
    command = [sys.executable, "-m", "stegolab.cli", "embed", str(output / "inputs" / f"{cover}.png"),
               "--message", str(output / "inputs" / f"{payload}.bin"),
               "--key", str(output / "inputs" / "benchmark.key"), "--output", str(target),
               "--rate", rate, "--strategy", "balanced", "--output-logs", str(log_report)]
    started = time.perf_counter()
    child = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=600)
    elapsed = time.perf_counter() - started
    (output / "logs" / f"{token}.txt").write_text(child.stdout + child.stderr, encoding="utf-8")
    record = {"kind": "cli", "cover": cover, "payload": payload, "repeat": repeat,
              "rate_option": rate, "strategy": "balanced", "wall_seconds": elapsed,
              "ok": child.returncode == 0, "returncode": child.returncode}
    if child.returncode:
        record["error"] = child.stderr[-2000:]
        return record
    result = json.loads(log_report.read_text(encoding="utf-8"))
    # This inspection occurs AFTER the subprocess timing. The CLI has already
    # decoded and authenticated its own output before writing it to disk.
    original = system.decode_png((output / "inputs" / f"{cover}.png").read_bytes())
    stego_bytes = target.read_bytes()
    decoded = system.decode_png(stego_bytes)
    record.update(selected_rate=result["rate"],
                  budget_bytes=system.Profile(result["rate"]).capacity(original.size),
                  changed_pixels=int(np.count_nonzero(original != decoded)),
                  output_sha256=hashlib.sha256(stego_bytes).hexdigest(),
                  output_bytes=len(stego_bytes))
    return record


def run_profile(cover_png, payload, rate, strategy, cover, repeat):
    for function in (primitives.split_positions, primitives.body_positions, primitives.columns):
        function.cache_clear()
    spans = defaultdict(float)
    depth = 0
    information = {}
    selected = {}

    def progress(percent, stage, summary):
        if summary:
            selected.update(summary)

    def timed(function, name):
        def wrapped(*args, **kwargs):
            nonlocal depth
            if depth:
                return function(*args, **kwargs)
            label = name(args) if callable(name) else name
            started = time.perf_counter()
            depth += 1
            try:
                return function(*args, **kwargs)
            finally:
                depth -= 1
                spans[label] += time.perf_counter() - started
        return wrapped

    embed = system.embed_pixels

    def capture(*args, **kwargs):
        result, info = embed(*args, **kwargs)
        information.update(info)
        return result, info

    hooks = [(system, "decode_png", "png_decode"), (system, "encode_png", "png_encode"),
             (system, "compute_costs", "cost_map"),
             (system, "split_positions", "bootstrap_shuffle"),
             (system, "body_positions", "body_shuffle"),
             (system, "columns", "parity_matrices"),
             (coding, "embed", lambda args: "bootstrap_stc" if len(args[2]) == 256 else "body_stc"),
             (coding, "extract", "syndrome_checks"),
             (balance, "balance_signs", "sign_balancing"),
             (system, "extract_pixels", "roundtrip_extract_cached")]
    with ExitStack() as stack:
        for module, attribute, name in hooks:
            stack.enter_context(patch.object(module, attribute, timed(getattr(module, attribute), name)))
        stack.enter_context(patch.object(system, "embed_pixels", capture))
        started_cpu = time.process_time()
        started = time.perf_counter()
        try:
            encoded = system.encrypt_and_embed(cover_png, PAYLOADS[payload], KEY,
                                              system.Profile(rate), strategy=strategy, progress=progress)
            ok, error = True, None
        except (ValueError, RuntimeError) as exc:
            ok, error = False, str(exc)
        elapsed = time.perf_counter() - started
        cpu = time.process_time() - started_cpu
    spans["other"] = elapsed - sum(spans.values())
    record = {"kind": "profile", "cover": cover, "payload": payload, "repeat": repeat,
              "rate_option": rate, "strategy": strategy, "wall_seconds": elapsed,
              "cpu_seconds": cpu, "stages": dict(spans), "ok": ok}
    if not ok:
        record["error"] = error
        return record
    record.update(selected_rate=information["rate"], budget_bytes=information["gross_bits"] // 8,
                  changed_pixels=information["changed_pixels"],
                  output_sha256=hashlib.sha256(encoded).hexdigest(), output_bytes=len(encoded),
                  stored_bytes=information["stored_bytes"], compressed=selected["compressed"])
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--covers", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--profile-repeats", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if min(args.covers, args.repeats, args.profile_repeats) < 1:
        parser.error("Cover and repeat counts must be positive")
    output = args.output or ROOT / "artifacts" / "runtime_auto" / datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest = json.loads((ROOT / "artifacts" / "manifest.json").read_text())
    covers = manifest["parts"]["train"][:args.covers]
    config = {"covers": covers, "repeats": args.repeats, "profile_repeats": args.profile_repeats,
              "payloads": {name: {"bytes": len(value), "stored_bytes": len(system.select_payload(value)[1]),
                                  "sha256": hashlib.sha256(value).hexdigest()}
                           for name, value in PAYLOADS.items()}}
    if output.exists() and not args.resume:
        parser.error("Output directory exists; use --resume or choose another directory")
    for folder in (output, output / "inputs", output / "logs", output / "stegos"):
        folder.mkdir(parents=True, exist_ok=True)
    if args.resume:
        saved = json.loads((output / "metadata.json").read_text())
        if saved["config"] != config:
            parser.error("Resume settings differ from the original run")
    else:
        for name, value in PAYLOADS.items():
            (output / "inputs" / f"{name}.bin").write_bytes(value)
        (output / "inputs" / "benchmark.key").write_bytes(KEY)
        inputs = []
        for cover in covers:
            path = ROOT / "data" / "bossbase" / f"{cover}.pgm"
            with Image.open(path) as image:
                raster = np.array(image)
            encoded = system.encode_png(raster)
            (output / "inputs" / f"{cover}.png").write_bytes(encoded)
            inputs.append({"id": cover, "width": raster.shape[1], "height": raster.shape[0],
                           "pixel_sha256": hashlib.sha256(raster.tobytes()).hexdigest(),
                           "png_sha256": hashlib.sha256(encoded).hexdigest()})
        sources = [ROOT / "src" / "stegolab" / name for name in
                   ("system.py", "primitives.py", "costs.py", "coding.py", "balance.py", "cli.py")]
        sources += [ROOT / "src" / "stegolab" / "native" / "stc.dll", Path(__file__).resolve()]
        write_json(output / "metadata.json", {
            "started_utc": datetime.now(timezone.utc).isoformat(), "config": config, "inputs": inputs,
            "python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
            "logical_cpus": os.cpu_count(), "thread_limits": {k: os.environ[k] for k in
                      ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
            "packages": {p: importlib.metadata.version(p) for p in ("numpy", "scipy", "pillow", "cryptography")},
            "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in sources},
            "method": "Sequential, alternating paired rate order. Fresh process per CLI run; OS/file caches warm. "
                      "Separate API profiles clear layout/code caches before each call, retain intra-call "
                      "self-verification caches, and exclude imports and filesystem I/O. Fresh OS salt/padding. "
                      "Inputs are the first train manifest covers, with no timing-based selection."})
    records_path = output / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()] if records_path.exists() else []
    completed = {(r["kind"], r["strategy"], r["payload"], r["cover"], r["repeat"], r["rate_option"])
                 for r in records}
    print(f"Output: {output}", flush=True)
    # Unreported warm-ups prime filesystem, imports and the native library.
    for rate in ("0.05", "auto"):
        token = f"warmup_{time.time_ns()}_{rate}"
        result = run_cli(output, covers[0], "hello_5", rate, token, -1)
        if not result["ok"]:
            raise RuntimeError(result["error"])
    coding.library()
    tasks = [("cli", "balanced", payload, cover, repeat)
             for payload in PAYLOADS for cover in covers for repeat in range(args.repeats)]
    tasks += [("profile", strategy, "hello_5", cover, repeat)
              for strategy in ("baseline", "balanced") for cover in covers
              for repeat in range(args.profile_repeats)]
    random.Random(20260926).shuffle(tasks)
    for pair_number, (kind, strategy, payload, cover, repeat) in enumerate(tasks):
        for rate in (("0.05", "auto") if pair_number % 2 == 0 else ("auto", "0.05")):
            identity = (kind, strategy, payload, cover, repeat, rate)
            if identity in completed:
                continue
            token = "_".join(map(str, identity))
            if kind == "cli":
                # A unique suffix permits resuming after a child finished but before the record was saved.
                record = run_cli(output, cover, payload, rate, token + f"_{time.time_ns()}", repeat)
            else:
                record = run_profile((output / "inputs" / f"{cover}.png").read_bytes(),
                                     payload, rate, strategy, cover, repeat)
            records.append(record)
            with records_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            write_json(output / "summary.json", summarize(records))
            print(f"{len(records)}/{2 * len(tasks)} {kind} {strategy} {payload} cover={cover} "
                  f"rate={rate}: {record['wall_seconds']:.3f}s ok={record['ok']}", flush=True)
    print(json.dumps(summarize(records), indent=2), flush=True)


if __name__ == "__main__":
    main()
