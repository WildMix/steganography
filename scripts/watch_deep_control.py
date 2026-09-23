"""Start the CPU neural positive control once its fixed development set is ready."""
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
art = root / "artifacts"
manifest = json.loads((art / "manifest.json").read_text())
identifiers = manifest["parts"]["train"] + manifest["parts"]["validation"]
while True:
    complete = sum((art / "samples" / i / "control.npy").exists() for i in identifiers)
    print(f"neural-control development images ready: {complete}/{len(identifiers)}", flush=True)
    if complete == len(identifiers):
        break
    time.sleep(30)
print("Starting nine-epoch residual-CNN positive control; final test is not accessed.", flush=True)
subprocess.run([sys.executable, str(root / "scripts" / "train_deep.py"),
                "--variant", "control", "--epochs", "9", "--threads", "4", "--validate-every", "3"],
               cwd=root, check=True)
