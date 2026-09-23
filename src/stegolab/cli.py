import argparse
import json
from pathlib import Path
import secrets

from .system import Profile, encrypt_and_embed, extract_and_decrypt


def main():
    parser = argparse.ArgumentParser(description="Authenticated, experimental grayscale PNG steganography")
    sub = parser.add_subparsers(dest="action", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("output", type=Path)
    for action in ("embed", "extract"):
        command = sub.add_parser(action)
        command.add_argument("image", type=Path)
        command.add_argument("--key", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--rate", default="0.05")
        if action == "embed":
            command.add_argument("--message", type=Path, required=True)
            command.add_argument("--strategy", choices=["baseline", "balanced"], default="baseline")
    args = parser.parse_args()
    # Exclusive creation prevents overwriting user inputs, covers, messages, or keys.
    if args.output.exists():
        parser.error("Output already exists; choose a new file")
    try:
        if args.action == "keygen":
            result = secrets.token_bytes(32)
        else:
            key = args.key.read_bytes()
            if args.action == "embed":
                result = encrypt_and_embed(args.image.read_bytes(), args.message.read_bytes(), key,
                                           Profile(args.rate), strategy=args.strategy)
            else:
                result = extract_and_decrypt(args.image.read_bytes(), key, Profile(args.rate))
        with args.output.open("xb") as output:
            output.write(result)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(args.output), "bytes": len(result)}))


if __name__ == "__main__":
    main()
