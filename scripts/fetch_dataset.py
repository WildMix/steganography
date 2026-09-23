"""Download the public BOSSbase archive, then safely extract its original PGM images."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import zipfile

URL = "https://dde.binghamton.edu/download/ImageDB/BOSSbase_1.01.zip"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data"))
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    archive = args.root / "BOSSbase_1.01.zip"
    partial = archive.with_suffix(".zip.partial")
    if not archive.exists():
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(URL, headers={"Range": f"bytes={offset}-"})
        with urllib.request.urlopen(request, timeout=120) as response:
            append = offset > 0 and response.status == 206
            if not append:
                offset = 0
            total = int(response.headers.get("Content-Length", 0)) + offset
            last = time.monotonic()
            with partial.open("ab" if append else "wb") as output:
                while block := response.read(4 * 1024 * 1024):
                    output.write(block)
                    offset += len(block)
                    if time.monotonic() - last > 10:
                        print(f"download {offset / 1e6:.1f}/{total / 1e6:.1f} MB", flush=True)
                        last = time.monotonic()
        partial.replace(archive)
    destination = args.root / "bossbase"
    destination.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if member.is_dir() or not member.filename.lower().endswith(".pgm"):
                continue
            target = destination / Path(member.filename).name
            if not target.stem.isdigit() or member.file_size > 2 * 1024 * 1024:
                raise ValueError(f"Unexpected dataset entry: {member.filename}")
            if not target.exists():
                target.write_bytes(source.read(member))
            count += 1
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    metadata = {"url": URL, "archive_sha256": digest, "images": count,
                "processing": "Original PGM sample values; no resizing or filtering"}
    (args.root / "dataset.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata), flush=True)


if __name__ == "__main__":
    main()

