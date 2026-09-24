"""Image embedding with keyed encrypted and no-key plaintext payload modes."""
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


def select_payload(message: bytes):
    """Select the shorter wire representation before image work begins."""
    compressor = zlib.compressobj(level=6, wbits=-15)
    compressed = compressor.compress(message) + compressor.flush()
    return (1, compressed) if len(compressed) < len(message) else (0, message)


def minimum_gross_rate(pixels: int, stored_bytes: int, keyed: bool) -> str:
    """Exact lowest profile rate satisfying the byte-level frame capacity."""
    lower = Fraction("0.0025")
    required = Fraction(8 * (stored_bytes + (66 if keyed else 54)), pixels)
    return "0.0025" if required <= lower else str(required)


def prepare_payload(message: bytes, total: int, pixels: int, keyed: bool, chosen_rate: str | None = None):
    """Return the shorter representation and pre-embedding capacity figures."""
    flag, data = select_payload(message)
    capacity = total - (66 if keyed else 54)
    summary = {"message_bytes": len(message), "stored_bytes": len(data),
               "capacity_bytes": capacity, "net_bpp": 8 * len(message) / pixels,
               "stored_net_bpp": 8 * len(data) / pixels,
               "gross_bpp": 8 * total / pixels,
               "capacity_used_percent": 100 * len(data) / capacity if capacity else None,
               "compressed": bool(flag),
               "suggested_rate": minimum_gross_rate(pixels, len(data), keyed),
               "chosen_rate": chosen_rate}
    return flag, data, summary


def embed_pixels(cover, message: bytes, key: bytes | None = None, profile=Profile(), *,
                 strategy="baseline", random_bytes=secrets.token_bytes, progress=None):
    validate_pixels(cover)
    if not isinstance(message, bytes) or len(message) > MAX_MESSAGE:
        raise ValueError("Message must be bytes and at most 16 MiB")
    if strategy not in ("baseline", "balanced"):
        raise ValueError("Unknown sender strategy")
    started = time.perf_counter()
    h, w = cover.shape
    if profile.rate == "auto":
        _, selected_data = select_payload(message)
        suggested = minimum_gross_rate(cover.size, len(selected_data), key is not None)
        if Fraction(suggested) > Fraction("0.2"):
            maximum_total = Profile("0.2").capacity(cover.size)
            maximum_bytes = maximum_total - (66 if key is not None else 54)
            if progress is not None:
                _, _, summary = prepare_payload(message, maximum_total, cover.size,
                                                key is not None, "auto (unavailable)")
                progress(20, "Payload exceeds supported rate", summary)
            raise coding.EmbeddingError(
                f"Payload requires {len(selected_data)} bytes; maximum at 0.2 bpp is "
                f"{maximum_bytes} bytes (minimum size-fitting rate: {suggested} bpp)")
        profile = Profile(suggested)
    total = profile.capacity(cover.size)
    q, length = total - 32, total - 48
    flag, data, summary = prepare_payload(message, total, cover.size, key is not None, profile.rate)
    if progress is not None:
        progress(20, "Payload capacity checked", summary)
    if len(data) > summary["capacity_bytes"]:
        raise coding.EmbeddingError(f"Payload requires {len(data)} bytes; capacity is {summary['capacity_bytes']}")
    ctx = context(w, h, total)
    root = root_key(key)
    head, base = split_positions(cover.size, derive(root, "split", ctx))
    if progress is not None:
        progress(25, "Computing adaptive costs", None)
    minus, plus = compute_costs(cover)
    if progress is not None:
        progress(45, "Adaptive costs ready", None)
    salt = random_bytes(32)
    if len(salt) != 32:
        raise ValueError("Randomness provider returned an invalid salt")
    keys = message_keys(root, ctx, salt)
    version = 1 if key is not None else 2
    frame = struct.pack(">BBQQ", version, flag, len(message), len(data)) + data
    if key is not None:
        frame += random_bytes(length - len(frame))
        aad = b"STEG-BP/1/aad\x00" + ctx + salt
        payload_bytes = ChaCha20Poly1305(keys["aead"]).encrypt(bytes(12), frame, aad)
    else:
        frame += (zlib.crc32(frame) & 0xFFFFFFFF).to_bytes(4, "big")
        frame += random_bytes(q - len(frame))
        # Public whitening makes the syndrome target less message-dependent;
        # anyone who knows the public layout can reverse it.
        payload_bytes = frame
    payload = bytes(a ^ b for a, b in zip(payload_bytes, Stream(keys["whiten"]).take(q), strict=True))
    body = body_positions(cover.size, derive(root, "split", ctx), keys["body-perm"])
    original = cover.ravel()
    output = original.copy()
    signs = Stream(keys["sign"])
    distortion = 0
    for positions, target, code_key, start_percent, end_percent, stage in (
        (head, bits(salt), derive(root, "head-code", ctx), 50, 60, "Embedding bootstrap"),
        (body, bits(payload), keys["body-code"], 60, 78, "Embedding payload body"),
    ):
        if progress is not None:
            progress(start_percent, stage, None)
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
        if progress is not None:
            progress(end_percent, stage + " complete", None)
    stego = output.reshape(cover.shape)
    balance_info = {}
    if strategy == "balanced":
        if progress is not None:
            progress(80, "Balancing modification signs", None)
        from .balance import balance_signs
        stego, balance_info = balance_signs(cover, stego)
        if not np.array_equal(stego & 1, output.reshape(cover.shape) & 1):
            raise RuntimeError("Balancing changed a payload parity")
    if progress is not None:
        progress(88, "Image embedding complete", None)
    changes = np.count_nonzero(stego != cover)
    return stego, {"rate": profile.rate, "strategy": strategy, "gross_bits": total * 8,
                   "stored_bytes": len(data), "message_bytes": len(message),
                   "changed_pixels": int(changes), "distortion": distortion,
                   "psnr": float(10 * np.log10(65025 * cover.size / changes)) if changes else float("inf"),
                   "seconds": time.perf_counter() - started, **balance_info}


def extract_pixels(stego, key: bytes | None = None, profile=Profile()) -> bytes:
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
        payload_bytes = bytes(a ^ b for a, b in zip(payload, Stream(keys["whiten"]).take(q), strict=True))
        if key is not None:
            aad = b"STEG-BP/1/aad\x00" + ctx + salt
            frame = ChaCha20Poly1305(keys["aead"]).decrypt(bytes(12), payload_bytes, aad)
        else:
            frame = payload_bytes
        version, flag, original_length, stored_length = struct.unpack(">BBQQ", frame[:18])
        expected_version = 1 if key is not None else 2
        frame_length = length if key is not None else q
        data_capacity = frame_length - 18 - (0 if key is not None else 4)
        if (len(frame) != frame_length or version != expected_version or flag not in (0, 1)
                or original_length > MAX_MESSAGE or stored_length > data_capacity):
            raise ValueError("Invalid frame")
        data = frame[18:18 + stored_length]
        if key is None:
            checksum_end = 18 + stored_length
            expected_crc = int.from_bytes(frame[checksum_end:checksum_end + 4], "big")
            if expected_crc != (zlib.crc32(frame[:checksum_end]) & 0xFFFFFFFF):
                raise ValueError("Invalid plaintext checksum")
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
        message = "No valid authenticated payload" if key is not None else "No valid plaintext payload"
        raise ExtractionError(message) from None


def encrypt_and_embed(cover_png: bytes, message: bytes, key: bytes | None = None, profile=Profile(), *,
                      strategy="baseline", progress=None) -> bytes:
    if progress is not None:
        progress(5, "Decoding cover PNG", None)
    cover = decode_png(cover_png)
    stego, information = embed_pixels(cover, message, key, profile, strategy=strategy, progress=progress)
    if progress is not None:
        progress(90, "Serializing stego PNG", None)
    result = encode_png(stego)
    if progress is not None:
        progress(95, "Verifying serialized image and extraction", None)
    decoded = decode_png(result)
    if not np.array_equal(decoded, stego) or extract_pixels(decoded, key, Profile(information["rate"])) != message:
        raise RuntimeError("Post-serialization self-check failed")
    if progress is not None:
        progress(100, "Embedding verified", None)
    return result


def extract_and_decrypt(stego_png: bytes, key: bytes | None = None, profile=Profile()) -> bytes:
    try:
        return extract_pixels(decode_png(stego_png), key, profile)
    except (ValueError, OSError):
        message = "No valid authenticated payload" if key is not None else "No valid plaintext payload"
        raise ExtractionError(message) from None
