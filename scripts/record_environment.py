"""Record the local runtime and implementation fingerprints for reproducibility."""
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import torch

root = Path(__file__).resolve().parents[1]
paths = [*root.glob("src/stegolab/**/*.py"), *root.glob("src/stegolab/**/*.cpp"),
         *root.glob("scripts/*.py"), *root.glob("tests/*.py"), root / "pyproject.toml",
         root / "EXPERIMENT_PROTOCOL.md", root / "steganography_master_blueprint.md"]
record = {
    "python": sys.version,
    "platform": platform.platform(),
    "processor": platform.processor(),
    "logical_cpus": os.cpu_count(),
    "cuda_available": torch.cuda.is_available(),
    "packages": {name: version(name) for name in
                 ("numpy", "scipy", "scikit-learn", "Pillow", "cryptography", "torch", "pytest")},
    "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
    "sha256": {str(path.relative_to(root)).replace("\\", "/"):
               hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)},
}
folder = root / "artifacts"
folder.mkdir(exist_ok=True)
(folder / "environment.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
frozen = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
lines = [line for line in frozen.splitlines() if line and not line.startswith(("-e", "#"))]
(root / "requirements-research.lock.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in record.items() if k != "sha256"}, indent=2))
