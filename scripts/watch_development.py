"""Finish detector fitting as already-running sample batches become complete."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
manifest = json.loads((ARTIFACTS / "manifest.json").read_text())
identifiers = manifest["parts"]["train"] + manifest["parts"]["validation"]
pending = ["0p05", "0p01"]
last = 0
while pending:
    for rate in pending.copy():
        done = sum((ARTIFACTS / "samples" / image / f"{rate}.json").exists() for image in identifiers)
        if done != len(identifiers):
            if time.monotonic() - last > 30:
                print(f"waiting for {rate}: {done}/{len(identifiers)}", flush=True)
                last = time.monotonic()
            continue
        for variant in [f"baseline_{rate}", f"balanced_{rate}"] + (["control"] if rate == "0p05" else []):
            report = ARTIFACTS / "models" / variant / "validation.json"
            if not report.exists():
                log = ARTIFACTS / f"fit_{variant}.log"
                with log.open("w", encoding="utf-8") as output:
                    subprocess.run([sys.executable, str(ROOT / "scripts" / "experiment.py"),
                                    "evaluate", "--variant", variant], cwd=ROOT,
                                   stdout=output, stderr=subprocess.STDOUT, check=True)
            data = json.loads(report.read_text())
            summary = {name: record["validation"] for name, record in data["detectors"].items()}
            print(json.dumps({"completed": variant, "validation": summary}), flush=True)
        pending.remove(rate)
    if pending:
        time.sleep(10)
print("All development feature-detector results are ready; final test remains untouched.", flush=True)
