import argparse
import json
from pathlib import Path
import secrets
import sys
import time

from .system import (Profile, analyze_configuration, decimal_rate,
                     encrypt_and_embed, extract_and_decrypt)


def display_summary(summary):
    """Keep exact internal fractions out of user-facing logs and JSON."""
    result = dict(summary)
    for name in ("chosen_rate", "suggested_rate"):
        result[name] = decimal_rate(summary[name], summary["pixels"])
    return result


def print_capacity(summary, stream):
    print(f"Image pixels: {summary['pixels']}", file=stream)
    print(f"Payload: {summary['message_bytes']} original bytes; "
          f"{summary['stored_bytes']} stored bytes"
          + (" (compressed)" if summary["compressed"] else " (uncompressed)"), file=stream)
    print(f"Net bpp: {summary['net_bpp']:.8f} original; "
          f"{summary['stored_net_bpp']:.8f} stored | "
          f"Gross bpp: {summary['gross_bpp']:.8f} (actual whole-byte frame)", file=stream)
    used = summary["capacity_used_percent"]
    percentage = f"{used:.2f}%" if used is not None else "n/a"
    print(f"Capacity used: {percentage} "
          f"({summary['stored_bytes']} / {summary['capacity_bytes']} stored bytes); "
          f"space left: {summary['remaining_bytes']} bytes; deficit: {summary['deficit_bytes']} bytes",
          file=stream)
    print(f"Suggested minimum gross rate: {summary['suggested_rate']} bpp (byte capacity only)", file=stream)
    print(f"Chosen gross rate: {summary['chosen_rate']} bpp", file=stream)
    print("Size-only fit within supported profile: "
          + ("yes" if summary["fits"] and summary["supported"] else "no"), file=stream)
    if not summary["supported"]:
        print("UNSUPPORTED: required rate exceeds the 0.20000000 bpp profile maximum.", file=stream)
    if not summary["fits"]:
        print("DOES NOT FIT: the stored message exceeds this frame's capacity.", file=stream)


FRAME_FIELDS = (
    ("Salt (bootstrap)", "salt_bytes"),
    ("Message header", "header_bytes"),
    ("Actual stored message", "stored_bytes"),
    ("Random padding / free space", "padding_bytes"),
    ("Authentication tag", "authentication_tag_bytes"),
    ("Public CRC checksum", "checksum_bytes"),
    ("Total allocated frame", "frame_bytes"),
)


def print_frame(chosen, suggested, stream):
    if suggested is None:
        print("Planned frame (bytes):", file=stream)
        for label, name in FRAME_FIELDS:
            if name != "checksum_bytes" or not chosen["keyed"]:
                print(f"  {label}: {chosen[name]}", file=stream)
    else:
        print("Frame comparison (bytes; difference = suggested - chosen):", file=stream)
        print(f"  {'Component':<30} {'Chosen':>12} {'Suggested':>12} {'Difference':>12}", file=stream)
        for label, name in FRAME_FIELDS:
            if name == "checksum_bytes" and chosen["keyed"]:
                continue
            print(f"  {label:<30} {chosen[name]:>12} {suggested[name]:>12} "
                  f"{suggested[name] - chosen[name]:>+12}", file=stream)
        print(f"Suggested actual frame bpp: {suggested['gross_bpp']:.8f}; "
              f"capacity used: {suggested['capacity_used_percent']:.2f}% "
              f"({suggested['stored_bytes']} / {suggested['capacity_bytes']} stored bytes); "
              f"space left: {suggested['remaining_bytes']} bytes", file=stream)
        print("Suggested profile: " + ("supported" if suggested["supported"] else "UNSUPPORTED (above maximum)"),
              file=stream)
    print(f"Payload body excluding salt: {chosen['body_bytes']} bytes"
          + (f" chosen; {suggested['body_bytes']} bytes suggested" if suggested is not None else ""), file=stream)
    print("Header = version (1) + compression flag (1) + original length (8) + stored length (8).", file=stream)
    if chosen["keyed"]:
        print("Layout: salt | encrypted(header + stored message + padding) | authentication tag.", file=stream)
        print("The 12-byte zero nonce is fixed by convention, not stored; context is authenticated, not embedded.", file=stream)
    else:
        print("Layout: salt | header + stored message + CRC + padding (public whitening; NOT encrypted).", file=stream)
        print("CRC is not authentication. No-key messages are publicly recoverable.", file=stream)
    if not chosen["fits"]:
        print("Chosen frame is infeasible: required components exceed its allocation; padding is shown as zero.", file=stream)


class CommandProgress:
    """Time sequential stages and retain completed lines, including on a TTY.

    Percentages are stage markers, not time estimates. Total covers this CLI
    workflow, including file I/O and embed self-check, but not Python imports.
    """

    def __init__(self, stream=None, clock=None):
        self.stream = stream if stream is not None else sys.stderr
        self.clock = clock if clock is not None else time.perf_counter
        self.tty = self.stream.isatty()
        self.started = self.clock()
        self.active = None
        self.open_line = False
        self.timings = []
        self.selected_rate = None
        self.suggested_rate = None
        self.payload_summary = None
        self.total_seconds = None
        self.percent = 0
        self.line_width = 0

    def close(self):
        if self.open_line:
            print(file=self.stream, flush=True)
            self.open_line = False

    def _complete(self, now, status="done"):
        if self.active is None:
            return
        stage, started = self.active
        seconds = now - started
        self.timings.append({"stage": stage, "seconds": seconds, "status": status})
        line = f"[{status}: {seconds:.3f} s] {stage}"
        if self.open_line:
            self.stream.write("\r")
            line = line.ljust(self.line_width)
        print(line, file=self.stream, flush=True)
        self.open_line = False
        self.active = None

    def __call__(self, percent, stage, summary=None):
        self._complete(self.clock())
        if summary is not None:
            displayed = display_summary(summary)
            self.payload_summary = displayed
            self.selected_rate = displayed["chosen_rate"]
            self.suggested_rate = displayed["suggested_rate"]
            print_capacity(displayed, self.stream)
            print_frame(displayed, None, self.stream)
        self.percent = percent
        self.active = (stage, self.clock())
        self._bar(percent, stage)

    def _bar(self, percent, stage):
        filled = percent * 24 // 100
        line = f"[{'#' * filled}{'-' * (24 - filled)}] {percent:3d}%  {stage}"
        if self.tty:
            self.stream.write("\r" + line)
            self.stream.flush()
            self.open_line = True
            self.line_width = len(line)
        else:
            print(line, file=self.stream, flush=True)

    def finish(self, label, *, success=True):
        if self.total_seconds is not None:
            return
        now = self.clock()
        self._complete(now, "done" if success else "failed")
        self.total_seconds = now - self.started
        self._bar(100 if success else self.percent, label)
        self.close()
        print(f"Total elapsed time: {self.total_seconds:.3f} s "
              "(CLI workflow; excludes interpreter startup/imports)", file=self.stream, flush=True)


EmbedProgress = CommandProgress  # Backward-compatible callback import.


def main():
    parser = argparse.ArgumentParser(description="Grayscale PNG steganography with keyed encryption or public plaintext mode")
    sub = parser.add_subparsers(dest="action", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("output", type=Path)
    keygen.add_argument("--output-logs", type=Path, metavar="FILE",
                        help="save an optional JSON report to a new file; console logs remain human-readable")
    for action in ("analyze", "embed", "extract"):
        command = sub.add_parser(action)
        command.add_argument("image", type=Path)
        command.add_argument("--output-logs", type=Path, metavar="FILE",
                             help="save an optional JSON report to a new file; console logs remain human-readable")
        command.add_argument("--key", type=Path,
                             help="32-byte shared key; omit for publicly recoverable, unencrypted plaintext mode")
        if action != "analyze":
            command.add_argument("--output", type=Path, required=True)
        command.add_argument("--rate", default="0.05",
                             help="gross bpp; analyze/embed also accept auto for the minimum size-fitting rate")
        if action in ("analyze", "embed"):
            command.add_argument("--message", type=Path, required=True)
            command.add_argument("--strategy", choices=["baseline", "balanced"], default="baseline")
    args = parser.parse_args()
    if args.action == "extract" and args.rate == "auto":
        parser.error("Extraction requires the decimal rate reported by embedding; --rate auto is only for analyze/embed")
    if args.action != "analyze" and args.output.exists():
        parser.error("Output already exists; choose a new file")
    if args.output_logs is not None:
        if args.output_logs.exists():
            parser.error("Log output already exists; choose a new file")
        if args.action != "analyze" and args.output_logs.resolve() == args.output.resolve():
            parser.error("--output-logs must be different from the command output")
    progress = CommandProgress()
    log_output = None
    report = {"action": args.action}
    try:
        # Reserve the optional destination before expensive work. Exclusive
        # creation protects existing files even if a path changes after checks.
        if args.output_logs is not None:
            log_output = args.output_logs.open("x", encoding="utf-8")
        if args.action != "keygen":
            mode = "keyed (encrypted)" if args.key is not None else "plaintext (no key; publicly recoverable)"
            report["mode"] = mode
            print(f"Mode: {mode}", file=progress.stream)
            if args.action in ("analyze", "embed"):
                print(f"Strategy: {args.strategy}; rate selection: "
                      + ("automatic" if args.rate == "auto" else "explicit"), file=progress.stream)
        progress(0, {"analyze": "Read cover image, message and optional key",
                     "embed": "Read cover image, message and optional key",
                     "extract": "Read stego image and optional key",
                     "keygen": "Generate 32 cryptographically random shared-key bytes"}[args.action])
        if args.action == "keygen":
            result = secrets.token_bytes(32)
        else:
            key = args.key.read_bytes() if args.key is not None else None
            image = args.image.read_bytes()
            if args.action == "analyze":
                plan = analyze_configuration(image, args.message.read_bytes(), key, Profile(args.rate),
                                             strategy=args.strategy, progress=progress)
                chosen, suggested = display_summary(plan["chosen"]), display_summary(plan["suggested"])
                progress.close()
                print(f"Image: {plan['width']} x {plan['height']} = {chosen['pixels']} pixels; "
                      f"strategy: {args.strategy}", file=progress.stream)
                print_capacity(chosen, progress.stream)
                print_frame(chosen, suggested if args.rate != "auto" else None, progress.stream)
                print("Size-only analysis: no randomness, encryption, cost map, embedding or image output. "
                      "This does not test wet-pixel/coding feasibility or statistical detectability.", file=progress.stream)
                report.update({"width": plan["width"], "height": plan["height"],
                          "strategy": args.strategy,
                          "requested_rate": "auto" if args.rate == "auto" else chosen["chosen_rate"],
                          "rate": chosen["chosen_rate"], "suggested_rate": suggested["chosen_rate"],
                          "fits_by_size": chosen["fits"] and chosen["supported"],
                          "chosen": chosen, "suggested": suggested})
            elif args.action == "embed":
                # The API reaches 100% after verification; the CLI still has
                # output I/O to perform, so reserve its final completion marker.
                def embedding_progress(percent, stage, summary):
                    progress(min(percent, 98), stage, summary)
                result = encrypt_and_embed(image, args.message.read_bytes(), key, Profile(args.rate),
                                           strategy=args.strategy, progress=embedding_progress)
            else:
                result = extract_and_decrypt(image, key, Profile(args.rate), progress=progress)
        if args.action != "analyze":
            progress(99, "Write output file (exclusive creation; no overwriting)")
            with args.output.open("xb") as output:
                output.write(result)
            progress.close()
            print(f"Output saved: {args.output} ({len(result)} bytes)", file=progress.stream)
            report.update(output=str(args.output), bytes=len(result))
            if args.action == "embed":
                report.update(rate=progress.selected_rate, suggested_rate=progress.suggested_rate,
                              chosen=progress.payload_summary, strategy=args.strategy)
        report["status"] = "ok"
        progress.finish({"analyze": "Analysis complete; no image modified", "embed": "Embedding verified and saved",
                         "extract": "Extraction verified and saved", "keygen": "Shared key saved"}[args.action])
    except (ValueError, OSError, RuntimeError, OverflowError) as exc:
        report.update(status="error", error=str(exc))
        progress.finish("Command failed; see error below", success=False)
        parser.error(str(exc))
    finally:
        progress.close()
        if log_output is not None:
            report.update(seconds=progress.total_seconds, timings=progress.timings)
            try:
                with log_output:
                    json.dump(report, log_output, indent=2)
                    log_output.write("\n")
            except OSError as exc:
                parser.error(f"Could not write JSON log report: {exc}")
            print(f"JSON log report saved: {args.output_logs}", file=progress.stream, flush=True)


if __name__ == "__main__":
    main()
