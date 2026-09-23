"""Authenticated image embedding. Cost strategy is sender-only; rate is shared."""
from dataclasses import dataclass
from fractions import Fraction
from io import BytesIO
import secrets
import struct
import time
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
import numpy as np
from PIL import Image

from . import coding
from .costs import compute_costs
from .primitives import Stream, bits, body_positions, columns, context, derive, mac, octets, root_key, split_positions

MAX_MESSAGE = 16 * 1024 * 1024


class ExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class Profile:
    rate: str = "0.05"

    def capacity(self, n: int) -> int:
        rate = Fraction(self.rate)
        if not Fraction("0.0025") <= rate <= Fraction("0.2"):
            raise ValueError("Experimental gross rate must be between 0.0025 and 0.2 bpp")
        total = n * rate.numerator // (8 * rate.denominator)
        if total < 66:
            raise ValueError("Image and rate leave no room for the authenticated frame")
        return total


def validate_pixels(image):
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 2:
        raise ValueError("Require an unconverted 8-bit grayscale image")
    h, w = image.shape
    if not (256 <= h <= 8192 and 256 <= w <= 8192 and 262144 <= image.size <= 16777216):
        raise ValueError("Image dimensions are outside the blueprint profile")


def decode_png(data: bytes) -> np.ndarray:
    if not isinstance(data, bytes) or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Input must be PNG bytes")
    with Image.open(BytesIO(data)) as image:
        w, h = image.size
        if image.mode != "L" or getattr(image, "n_frames", 1) != 1:
            raise ValueError("Only single-frame grayscale PNG is supported")
        if not (256 <= h <= 8192 and 256 <= w <= 8192 and 262144 <= w * h <= 16777216):
            raise ValueError("PNG dimensions exceed limits")
        image.load()
        result = np.array(image, dtype=np.uint8)
    validate_pixels(result)
    return result


def encode_png(image: np.ndarray) -> bytes:
    validate_pixels(image)
    output = BytesIO()
    Image.fromarray(image).save(output, format="PNG", compress_level=6, optimize=False)
    return output.getvalue()


def message_keys(root, ctx, salt):
    msg = mac(salt, root)
    return {label: derive(msg, label, ctx)
            for label in ("aead", "whiten", "body-perm", "body-code", "sign")}


def embed_pixels(cover, message: bytes, key: bytes, profile=Profile(), *,
                 strategy="baseline", random_bytes=secrets.token_bytes):
    validate_pixels(cover)
    if not isinstance(message, bytes) or len(message) > MAX_MESSAGE:
        raise ValueError("Message must be bytes and at most 16 MiB")
    if strategy not in ("baseline", "balanced"):
        raise ValueError("Unknown sender strategy")
    started = time.perf_counter()
    h, w = cover.shape
    total = profile.capacity(cover.size)
    q, length = total - 32, total - 48
    ctx = context(w, h, total)
    root = root_key(key)
    head, base = split_positions(cover.size, derive(root, "split", ctx))
    minus, plus = compute_costs(cover)
    compressor = zlib.compressobj(level=6, wbits=-15)
    compressed = compressor.compress(message) + compressor.flush()
    flag, data = (1, compressed) if len(compressed) < len(message) else (0, message)
    if len(data) > length - 18:
        raise coding.EmbeddingError(f"Payload requires {len(data)} bytes; capacity is {length - 18}")
    salt = random_bytes(32)
    if len(salt) != 32:
        raise ValueError("Randomness provider returned an invalid salt")
    keys = message_keys(root, ctx, salt)
    frame = (struct.pack(">BBQQ", 1, flag, len(message), len(data)) + data
             + random_bytes(length - 18 - len(data)))
    aad = b"STEG-BP/1/aad\x00" + ctx + salt
    encrypted = ChaCha20Poly1305(keys["aead"]).encrypt(bytes(12), frame, aad)
    payload = bytes(a ^ b for a, b in zip(encrypted, Stream(keys["whiten"]).take(q), strict=True))
    body = body_positions(cover.size, derive(root, "split", ctx), keys["body-perm"])
    original = cover.ravel()
    output = original.copy()
    signs = Stream(keys["sign"])
    distortion = 0
    for positions, target, code_key in (
        (head, bits(salt), derive(root, "head-code", ctx)),
        (body, bits(payload), keys["body-code"]),
    ):
        x = original[positions] & 1
        costs = np.minimum(minus[positions], plus[positions])
        if np.count_nonzero(costs != coding.WET) < len(target):
            raise coding.EmbeddingError("Insufficient dry pixels")
        matrix = columns(len(x), len(target), 10, code_key)
        y, stage_cost = coding.embed(x, costs, target, matrix)
        changed = positions[x != y]
        direction = np.where(minus[changed] < plus[changed], -1, 1).astype(np.int16)
        ties = minus[changed] == plus[changed]
        random_signs = np.frombuffer(signs.take(int(np.count_nonzero(ties))), dtype=np.uint8)
        direction[ties] = (random_signs.astype(np.int16) & 1) * 2 - 1
        output[changed] = (original[changed].astype(np.int16) + direction).astype(np.uint8)
        if not np.array_equal(coding.extract(output[positions] & 1, len(target), matrix), target):
            raise RuntimeError("Internal syndrome verification failed")
        distortion += stage_cost
    stego = output.reshape(cover.shape)
    balance_info = {}
    if strategy == "balanced":
        from .balance import balance_signs
        stego, balance_info = balance_signs(cover, stego)
        if not np.array_equal(stego & 1, output.reshape(cover.shape) & 1):
            raise RuntimeError("Balancing changed a payload parity")
    changes = np.count_nonzero(stego != cover)
    return stego, {"rate": profile.rate, "strategy": strategy, "gross_bits": total * 8,
                   "stored_bytes": len(data), "message_bytes": len(message),
                   "changed_pixels": int(changes), "distortion": distortion,
                   "psnr": float(10 * np.log10(65025 * cover.size / changes)) if changes else float("inf"),
                   "seconds": time.perf_counter() - started, **balance_info}


def extract_pixels(stego, key: bytes, profile=Profile()) -> bytes:
    try:
        validate_pixels(stego)
        h, w = stego.shape
        total = profile.capacity(stego.size)
        q, length = total - 32, total - 48
        ctx, root = context(w, h, total), root_key(key)
        head, base = split_positions(stego.size, derive(root, "split", ctx))
        flat = stego.ravel()
        head_matrix = columns(len(head), 256, 10, derive(root, "head-code", ctx))
        salt = octets(coding.extract(flat[head] & 1, 256, head_matrix))
        keys = message_keys(root, ctx, salt)
        body = body_positions(stego.size, derive(root, "split", ctx), keys["body-perm"])
        matrix = columns(len(body), 8 * q, 10, keys["body-code"])
        payload = octets(coding.extract(flat[body] & 1, 8 * q, matrix))
        encrypted = bytes(a ^ b for a, b in zip(payload, Stream(keys["whiten"]).take(q), strict=True))
        aad = b"STEG-BP/1/aad\x00" + ctx + salt
        frame = ChaCha20Poly1305(keys["aead"]).decrypt(bytes(12), encrypted, aad)
        version, flag, original_length, stored_length = struct.unpack(">BBQQ", frame[:18])
        if (len(frame) != length or version != 1 or flag not in (0, 1)
                or original_length > MAX_MESSAGE or stored_length > length - 18):
            raise ValueError("Invalid frame")
        data = frame[18:18 + stored_length]
        if flag == 0:
            if len(data) != original_length:
                raise ValueError("Invalid raw length")
            return data
        inflater = zlib.decompressobj(wbits=-15)
        message = inflater.decompress(data, original_length + 1)
        if (len(message) != original_length or not inflater.eof or inflater.unused_data
                or inflater.unconsumed_tail):
            raise ValueError("Invalid compressed frame")
        return message
    except (ValueError, InvalidTag, zlib.error, struct.error, OverflowError):
        raise ExtractionError("No valid authenticated payload") from None


def encrypt_and_embed(cover_png: bytes, message: bytes, key: bytes, profile=Profile(), *, strategy="baseline") -> bytes:
    cover = decode_png(cover_png)
    stego, _ = embed_pixels(cover, message, key, profile, strategy=strategy)
    result = encode_png(stego)
    decoded = decode_png(result)
    if not np.array_equal(decoded, stego) or extract_pixels(decoded, key, profile) != message:
        raise RuntimeError("Post-serialization self-check failed")
    return result


def extract_and_decrypt(stego_png: bytes, key: bytes, profile=Profile()) -> bytes:
    try:
        return extract_pixels(decode_png(stego_png), key, profile)
    except (ValueError, OSError):
        raise ExtractionError("No valid authenticated payload") from None
