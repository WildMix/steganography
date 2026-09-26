"""Compare a preserved original package with the current implementation.

Checks exact ciphertext/PNG equality with controlled research randomness, then
times unmodified CLI subprocesses with production randomness in paired order.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = {"hello": b"HELLO", "binary1024": hashlib.shake_256(b"exact timing payload").digest(1024),
            "compressed": b"repeatable compressed message\n" * 1000}


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def worker(job_path):
    job = json.loads(job_path.read_text())
    sys.path.insert(0, job["implementation"])
    from stegolab import primitives, system
    import numpy as np
    expected_root = Path(job["implementation"]).resolve()
    assert Path(system.__file__).resolve().is_relative_to(expected_root)
    cover = system.decode_png(Path(job["cover_png"]).read_bytes())
    message = Path(job["message"]).read_bytes()
    key = Path(job["key"]).read_bytes()
    wire = {}
    original_aead = system.ChaCha20Poly1305

    class TracedAEAD:
        def __init__(self, key):
            self.inner = original_aead(key)
            wire["derived_key_sha256"] = sha(key)

        def encrypt(self, nonce, plaintext, aad):
            encrypted = self.inner.encrypt(nonce, plaintext, aad)
            wire.update(nonce=nonce.hex(), plaintext=plaintext.hex(), aad=aad.hex(), ciphertext=encrypted.hex())
            return encrypted

        def decrypt(self, nonce, ciphertext, aad):
            return self.inner.decrypt(nonce, ciphertext, aad)

    system.ChaCha20Poly1305 = TracedAEAD
    started = time.perf_counter()
    stego, info = system.embed_pixels(cover, message, key, system.Profile(job["rate"]),
                                    strategy=job["strategy"], random_bytes=random.Random(job["seed"]).randbytes)
    encoded = system.encode_png(stego)
    decoded = system.decode_png(encoded)
    assert np.array_equal(decoded, stego)
    assert system.extract_pixels(decoded, key, system.Profile(info["rate"])) == message
    elapsed = time.perf_counter() - started
    Path(job["png_output"]).write_bytes(encoded)
    result = {"png_sha256": sha(encoded), "pixels_sha256": sha(stego.tobytes()),
              "wire": wire, "info": {k: v for k, v in info.items() if k != "seconds"},
              "api_seconds": elapsed,
              "native_primitives": getattr(primitives, "_native_backend", lambda: None)() is not None,
              "module": system.__file__}
    save(Path(job["report"]), result)


def summary(records):
    grouped = {}
    identical = [r for r in records if r["kind"] == "identity"]
    for row in records:
        if row["kind"] != "cli":
            continue
        grouped.setdefault((row["payload"], row["rate"]), []).append(row)
    timings = []
    for (payload, rate), rows in sorted(grouped.items()):
        savings = [100 * (r["before_seconds"] - r["after_seconds"]) / r["before_seconds"] for r in rows]
        timings.append({"payload": payload, "rate": rate, "pairs": len(rows),
                        "median_before_seconds": statistics.median(r["before_seconds"] for r in rows),
                        "median_after_seconds": statistics.median(r["after_seconds"] for r in rows),
                        "median_paired_saving_percent": statistics.median(savings),
                        "paired_saving_range_percent": [min(savings), max(savings)],
                        "faster_pairs": sum(value > 0 for value in savings)})
    return {"identity_cases": len(identical), "all_identical": all(r["identical"] for r in identical),
            "cli_pairs": sum(len(rows) for rows in grouped.values()), "timings": timings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
        return
    if not args.reference or not args.output:
        parser.error("--reference and --output are required")
    reference, output = args.reference.resolve(), args.output.resolve()
    if output.exists() and not args.resume:
        parser.error("Output already exists; select another directory or use --resume")
    for directory in (output, output / "inputs", output / "jobs", output / "logs", output / "stegos"):
        directory.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    covers = json.loads((ROOT / "artifacts" / "manifest.json").read_text())["parts"]["train"][:3]
    implementations = {"before": reference, "after": ROOT / "src"}
    key_path = output / "inputs" / "public_benchmark.key"
    if not args.resume:
        key_path.write_bytes(hashlib.sha256(b"Public exact optimization benchmark key").digest())
        for cover in covers:
            with Image.open(ROOT / "data" / "bossbase" / f"{cover}.pgm") as image:
                image.save(output / "inputs" / f"{cover}.png", compress_level=6)
        for name, data in PAYLOADS.items():
            (output / "inputs" / f"{name}.bin").write_bytes(data)
        save(output / "metadata.json", {
            "date_utc": datetime.now(timezone.utc).isoformat(), "covers": covers,
            "reference": str(reference), "python": sys.version,
            "implementation_sha256": {label: {name: sha((path / "stegolab" / name).read_bytes())
                for name in ("system.py", "primitives.py", "native/stc.dll")}
                for label, path in implementations.items()},
            "method": "Identical image/message/key/salt/padding for equality checks; fresh process per backend. "
                      "CLI uses fresh production randomness and includes startup, I/O and self-verification. "
                      "Pairs run sequentially in alternating order; BLAS/OMP threads=1; no outlier removal."})
    else:
        assert json.loads((output / "metadata.json").read_text())["reference"] == str(reference)
    records_path = output / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()] if records_path.exists() else []
    completed = {r["id"] for r in records}

    def checkpoint(record):
        records.append(record)
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        save(output / "summary.json", summary(records))
        print(f"{len(records)}/72 {record['id']}: OK", flush=True)

    def environment(backend):
        env = dict(os.environ, PYTHONPATH=str(implementations[backend]), STEGOLAB_NATIVE_PRIMITIVES="1")
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            env[name] = "1"
        return env

    for cover in covers:
        for payload in PAYLOADS:
            for rate in ("0.05", "auto"):
                for strategy in ("baseline", "balanced"):
                    identity = f"identity_{cover}_{payload}_{rate}_{strategy}"
                    if identity in completed:
                        continue
                    results = {}
                    pngs = {}
                    for backend, implementation in implementations.items():
                        token = f"{identity}_{backend}"
                        pngs[backend] = output / "stegos" / f"{token}.png"
                        job_path = output / "jobs" / f"{token}.json"
                        report = output / "jobs" / f"{token}.result.json"
                        save(job_path, {"implementation": str(implementation),
                            "cover_png": str(output / "inputs" / f"{cover}.png"),
                            "message": str(output / "inputs" / f"{payload}.bin"), "key": str(key_path),
                            "rate": rate, "strategy": strategy, "seed": int(sha(identity.encode())[:16], 16),
                            "png_output": str(pngs[backend]), "report": str(report)})
                        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", str(job_path)],
                                       cwd=ROOT, env=environment(backend), check=True, timeout=600)
                        results[backend] = json.loads(report.read_text())
                    assert not results["before"]["native_primitives"] and results["after"]["native_primitives"]
                    assert pngs["before"].read_bytes() == pngs["after"].read_bytes(), identity
                    for field in ("wire", "pixels_sha256", "info"):
                        assert results["before"][field] == results["after"][field], (identity, field)
                    checkpoint({"id": identity, "kind": "identity", "identical": True,
                                "png_sha256": results["after"]["png_sha256"]})
    cases = [(cover, payload, rate, repeat) for cover in covers for payload in ("hello", "binary1024")
             for rate in ("0.05", "auto") for repeat in range(3)]
    random.Random(5026).shuffle(cases)
    # Equality runs above have already warmed imports/filesystem caches for both packages.
    for index, (cover, payload, rate, repeat) in enumerate(cases):
        identity = f"cli_{cover}_{payload}_{rate}_{repeat}"
        if identity in completed:
            continue
        times = {}
        for backend in (("before", "after") if index % 2 == 0 else ("after", "before")):
            token = f"{identity}_{backend}_{time.time_ns()}"
            command = [sys.executable, "-m", "stegolab.cli", "embed", str(output / "inputs" / f"{cover}.png"),
                       "--message", str(output / "inputs" / f"{payload}.bin"), "--key", str(key_path),
                       "--output", str(output / "stegos" / f"{token}.png"), "--rate", rate,
                       "--strategy", "balanced"]
            env = environment(backend)
            started = time.perf_counter()
            child = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
            times[backend] = time.perf_counter() - started
            (output / "logs" / f"{token}.txt").write_text(child.stdout + child.stderr, encoding="utf-8")
            if child.returncode:
                raise RuntimeError(child.stderr)
        checkpoint({"id": identity, "kind": "cli", "cover": cover, "payload": payload, "rate": rate,
                    "repeat": repeat, "before_seconds": times["before"], "after_seconds": times["after"]})
    print(json.dumps(summary(records), indent=2), flush=True)


if __name__ == "__main__":
    main()
