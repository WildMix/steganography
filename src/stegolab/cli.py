import argparse
from fractions import Fraction
import json
from pathlib import Path
import secrets
import sys

from .system import Profile, encrypt_and_embed, extract_and_decrypt


class EmbedProgress:
    """Stage-based progress; percentages mark completed stages, not elapsed time."""

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stderr
        self.tty = self.stream.isatty()
        self.open_line = False
        self.selected_rate = None
        self.suggested_rate = None

    def close(self):
        if self.open_line:
            print(file=self.stream, flush=True)
            self.open_line = False

    def __call__(self, percent, stage, summary):
        if summary is not None:
            self.close()
            self.selected_rate = summary["chosen_rate"]
            self.suggested_rate = summary["suggested_rate"]
            print(f"Payload: {summary['message_bytes']} original bytes; "
                  f"{summary['stored_bytes']} stored bytes"
                  + (" (compressed)" if summary["compressed"] else ""), file=self.stream)
            print(f"Net bpp: {summary['net_bpp']:.6f} original; "
                  f"{summary['stored_net_bpp']:.6f} stored | "
                  f"Gross bpp: {summary['gross_bpp']:.6f}", file=self.stream)
            used = summary["capacity_used_percent"]
            percentage = f"{used:.2f}%" if used is not None else "n/a"
            print(f"Capacity used: {percentage} "
                  f"({summary['stored_bytes']} / {summary['capacity_bytes']} stored bytes)",
                  file=self.stream)
            suggested = summary["suggested_rate"]
            print(f"Suggested minimum gross rate: {suggested} bpp "
                  f"(~{float(Fraction(suggested)):.8f}; byte capacity only)", file=self.stream)
            print(f"Chosen gross rate: {summary['chosen_rate']} bpp", file=self.stream, flush=True)
        filled = percent * 24 // 100
        line = f"[{'#' * filled}{'-' * (24 - filled)}] {percent:3d}%  {stage}"
        if self.tty:
            self.stream.write("\r" + line.ljust(72))
            self.stream.flush()
            self.open_line = True
            if percent == 100:
                self.close()
        else:
            print(line, file=self.stream, flush=True)


def main():
    parser = argparse.ArgumentParser(description="Grayscale PNG steganography with keyed encryption or public plaintext mode")
    sub = parser.add_subparsers(dest="action", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("output", type=Path)
    for action in ("embed", "extract"):
        command = sub.add_parser(action)
        command.add_argument("image", type=Path)
        command.add_argument("--key", type=Path,
                             help="32-byte shared key; omit for publicly recoverable, unencrypted plaintext mode")
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--rate", default="0.05",
                             help="gross bpp; use auto when embedding for the minimum size-fitting rate")
        if action == "embed":
            command.add_argument("--message", type=Path, required=True)
            command.add_argument("--strategy", choices=["baseline", "balanced"], default="baseline")
    args = parser.parse_args()
    if args.action == "extract" and args.rate == "auto":
        parser.error("Extraction requires the exact rate reported by embedding; --rate auto is embed-only")
    # Exclusive creation prevents overwriting user inputs, covers, messages, or keys.
    if args.output.exists():
        parser.error("Output already exists; choose a new file")
    progress = EmbedProgress() if args.action == "embed" else None
    try:
        if args.action == "keygen":
            result = secrets.token_bytes(32)
        else:
            key = args.key.read_bytes() if args.key is not None else None
            if args.action == "embed":
                progress(0, "Reading input files", None)
                result = encrypt_and_embed(args.image.read_bytes(), args.message.read_bytes(), key,
                                           Profile(args.rate), strategy=args.strategy, progress=progress)
            else:
                result = extract_and_decrypt(args.image.read_bytes(), key, Profile(args.rate))
        with args.output.open("xb") as output:
            output.write(result)
    except (ValueError, OSError) as exc:
        if progress is not None:
            progress.close()
        parser.error(str(exc))
    finally:
        if progress is not None:
            progress.close()
    report = {"output": str(args.output), "bytes": len(result)}
    if args.action == "embed":
        report["rate"] = progress.selected_rate
        report["suggested_rate"] = progress.suggested_rate
    if args.action != "keygen" and args.key is None:
        report["mode"] = "plaintext (no key; publicly recoverable)"
    print(json.dumps(report))


if __name__ == "__main__":
    main()
