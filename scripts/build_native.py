"""Build the local coding engine with GCC; never downloads or executes build hooks."""
from pathlib import Path
import os
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
folder = root / "src" / "stegolab" / "native"
compiler = shutil.which("g++")
if not compiler:
    raise SystemExit("A C++ compiler is required: install GCC and put g++ on PATH.")
output = folder / ("stc.dll" if os.name == "nt" else "stc.so")
flags = ["-O3", "-std=c++17", "-shared", "-DNDEBUG"]
flags += ["-static", "-static-libgcc", "-static-libstdc++"] if os.name == "nt" else ["-fPIC"]
command = [compiler, *flags, str(folder / "stc.cpp"), "-o", str(output)]
subprocess.run(command, check=True)
print(output)
