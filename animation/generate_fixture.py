"""Rebuild the public HELLO teaching fixture with the actual encoder.

Run from the repository root: .venv/Scripts/python animation/generate_fixture.py
The counting key and randomness are PUBLIC teaching values, never real secrets.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from stegolab import coding
from stegolab.costs import compute_costs
from stegolab.primitives import (Stream, bits, body_positions, columns, context,
                                derive, octets, root_key, split_positions)
from stegolab.system import (Profile, decode_png, embed_pixels, encode_png,
                            extract_pixels, message_keys, select_payload)


def main():
    out = ROOT / "animation" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    # A mathematical landscape, not a photograph or a security benchmark.
    rng = np.random.default_rng(331)
    yy, xx = np.mgrid[:512, :512]
    noise = gaussian_filter(rng.normal(0, 1, (512, 512)), 0.6)
    cover = 198 - yy * 0.10 + 1.2 * noise
    for layer in range(6):
        ridge = (160 + layer * 51 + 28 * np.sin(xx / (81 - layer * 7) + layer)
                 + 17 * np.cos(xx / 37 + layer * 2))
        texture = (3 + layer * 1.9) * noise + 4 * np.sin(xx * .15 + yy * .24)
        cover = np.where(yy > ridge, 152 - layer * 19 + texture, cover)
    cover = np.clip(np.rint(cover), 5, 250).astype(np.uint8)
    key, salt, padding = bytes(range(32)), bytes(range(32, 64)), bytes(range(64, 74))
    message = b"HELLO"
    calls = iter((salt, padding))

    def demo_random(count):
        result = next(calls)
        assert len(result) == count
        return result

    def progress(percent, stage, _):
        print(f"{percent}% {stage}", flush=True)

    stego, info = embed_pixels(cover, message, key, Profile("auto"), strategy="balanced",
                              random_bytes=demo_random, progress=progress)
    encoded = encode_png(stego)
    decoded = decode_png(encoded)
    assert np.array_equal(decoded, stego)
    assert extract_pixels(decoded, key, Profile(info["rate"])) == message
    assert select_payload(message) == (0, message)
    total = Profile(info["rate"]).capacity(cover.size)
    assert total == 81
    ctx, root = context(512, 512, total), root_key(key)
    keys = message_keys(root, ctx, salt)
    frame = struct.pack(">BBQQ", 1, 0, 5, 5) + message + padding
    encrypted = ChaCha20Poly1305(keys["aead"]).encrypt(
        bytes(12), frame, b"STEG-BP/1/aad\x00" + ctx + salt)
    mask = Stream(keys["whiten"]).take(len(encrypted))
    body_bytes = bytes(a ^ b for a, b in zip(encrypted, mask, strict=True))
    split_key = derive(root, "split", ctx)
    head, base = split_positions(cover.size, split_key)
    body = body_positions(cover.size, split_key, keys["body-perm"])
    for positions, target, code_key in (
        (head, salt, derive(root, "head-code", ctx)),
        (body, body_bytes, keys["body-code"]),
    ):
        matrix = columns(len(positions), len(target) * 8, 10, code_key)
        assert octets(coding.extract(stego.ravel()[positions] & 1, len(target) * 8, matrix)) == target
    delta = stego.astype(int) - cover.astype(int)
    assert np.max(np.abs(delta)) == 1
    assert not np.any(delta[:16]) and not np.any(delta[-16:])
    assert not np.any(delta[:, :16]) and not np.any(delta[:, -16:])
    minus, plus = compute_costs(cover)
    costs = np.minimum(minus, plus).reshape(512, 512)
    wet = costs == coding.WET
    assert not np.any(delta[wet])
    log_cost = np.log1p(costs.astype(float))
    low, high = np.percentile(log_cost[~wet], [3, 97])
    normalized = np.clip((log_cost - low) / (high - low), 0, 1)
    rgb = (np.array([100, 223, 182])[None, None, :] * (1 - normalized[..., None])
           + np.array([232, 158, 105])[None, None, :] * normalized[..., None])
    rgb[wet] = [38, 44, 54]
    Image.fromarray(rgb.astype(np.uint8)).save(out / "costs.png")
    (out / "cover.png").write_bytes(encode_png(cover))
    (out / "stego.png").write_bytes(encoded)
    changed = np.flatnonzero(delta.ravel())
    is_head = np.zeros(cover.size, dtype=bool)
    is_head[head] = True
    records = [[int(i % 512), int(i // 512), int(cover.ravel()[i]),
                int(stego.ravel()[i]), bool(is_head[i])] for i in changed]
    sampled = [int((row * 16 + 8) * 512 + col * 16 + 8)
               for row in range(32) for col in range(32)]
    fixture = {
        "description": "Deterministic, public teaching example; synthetic landscape; not a security benchmark.",
        "message": "HELLO", "key": key.hex(), "salt": salt.hex(), "padding": padding.hex(),
        "frame": frame.hex(), "encrypted": encrypted.hex(), "whitening": mask.hex(),
        "body": body_bytes.hex(), "context": ctx.hex(), "info": info,
        "headCount": len(head), "bodyCount": len(body), "changes": records,
        "headChanges": int(is_head[changed].sum()), "wetCount": int(wet.sum()),
        "poolSample": is_head[sampled].astype(int).tolist(),
        "coverSha256": hashlib.sha256(encode_png(cover)).hexdigest(),
        "stegoSha256": hashlib.sha256(encoded).hexdigest(),
        "verified": {"pngPixels": True, "saltSyndrome": True, "bodySyndrome": True,
                     "recoveredHex": message.hex(), "unitChanges": True, "protectedPixels": True},
    }
    (out.parent / "fixture.js").write_text(
        "// Generated by generate_fixture.py; contains only PUBLIC teaching values.\n"
        + "window.STEGO_FIXTURE = " + json.dumps(fixture, indent=2) + ";\n", encoding="utf-8")
    print(json.dumps({"changed_pixels": len(changed), "recovered": "HELLO", **info}, indent=2))


if __name__ == "__main__":
    main()
