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
from .primitives import (Stream, bits, body_positions, columns, context, derive,
                         extract_syndrome, mac, octets, root_key, split_positions)

MAX_MESSAGE = 16 * 1024 * 1024


class ExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class Profile:
    rate: str = "0.05"

    def capacity(self, n: int) -> int:
        try:
            rate = Fraction(self.rate)
        except (ValueError, ZeroDivisionError):
            raise ValueError("Rate must be a finite decimal bpp value") from None
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


def decimal_rate(rate: str, pixels: int | None = None) -> str:
    """Copyable decimal, rounded upward without changing the byte budget.

    Fractions remain internal for wire compatibility. Eight decimal places are
    enough for automatic rates in this image profile; unusual explicit rates
    may need more digits to stay on the same side of a byte boundary.
    """
    exact = Fraction(rate)
    places = 8
    while True:
        scale = 10 ** places
        value = (exact.numerator * scale + exact.denominator - 1) // exact.denominator
        rounded = Fraction(value, scale)
        if pixels is None or int(pixels * rounded // 8) == int(pixels * exact // 8):
            return f"{value // scale}.{value % scale:0{places}d}"
        places += 1


def _payload_summary(message, flag, data, total, pixels, keyed, chosen_rate):
    capacity = total - (66 if keyed else 54)
    summary = {"message_bytes": len(message), "stored_bytes": len(data),
               "pixels": pixels, "keyed": keyed,
               "capacity_bytes": capacity, "net_bpp": 8 * len(message) / pixels,
               "stored_net_bpp": 8 * len(data) / pixels,
               "gross_bpp": 8 * total / pixels,
               "capacity_used_percent": 100 * len(data) / capacity if capacity else None,
               "compressed": bool(flag),
               "suggested_rate": minimum_gross_rate(pixels, len(data), keyed),
               "chosen_rate": chosen_rate}
    summary.update({"frame_bytes": total, "body_bytes": total - 32,
                    "salt_bytes": 32, "header_bytes": 18,
                    "padding_bytes": max(0, capacity - len(data)),
                    "authentication_tag_bytes": 16 if keyed else 0,
                    "checksum_bytes": 0 if keyed else 4,
                    "remaining_bytes": max(0, capacity - len(data)),
                    "deficit_bytes": max(0, len(data) - capacity),
                    "fits": len(data) <= capacity})
    return summary


def prepare_payload(message: bytes, total: int, pixels: int, keyed: bool, chosen_rate: str | None = None):
    """Return the shorter representation and pre-embedding capacity figures."""
    flag, data = select_payload(message)
    summary = _payload_summary(message, flag, data, total, pixels, keyed, chosen_rate)
    return flag, data, summary


def plan_payload(message: bytes, pixels: int, keyed: bool, profile=Profile()):
    """Shared size-only preflight; no randomness, cryptography or pixel costs."""
    if not isinstance(message, bytes) or len(message) > MAX_MESSAGE:
        raise ValueError("Message must be bytes and at most 16 MiB")
    flag, data = select_payload(message)
    suggested = minimum_gross_rate(pixels, len(data), keyed)
    chosen = suggested if profile.rate == "auto" else profile.rate
    if profile.rate != "auto":
        profile.capacity(pixels)  # Validate explicit rates, including bounds.
    summaries = []
    for rate in (chosen, suggested):
        total = int(pixels * Fraction(rate) // 8)
        summary = _payload_summary(message, flag, data, total, pixels, keyed, rate)
        summary["supported"] = Fraction("0.0025") <= Fraction(rate) <= Fraction("0.2")
        summaries.append(summary)
    return flag, data, {"requested_rate": profile.rate, "chosen": summaries[0],
                        "suggested": summaries[1]}


def analyze_configuration(cover_png: bytes, message: bytes, key: bytes | None = None,
                          profile=Profile(), *, strategy="baseline", progress=None):
    """Inspect inputs and predict framing without running the embedding engine."""
    _progress(progress, 10, "Decode and validate the grayscale cover PNG")
    cover = decode_png(cover_png)
    if key is not None and (not isinstance(key, bytes) or len(key) != 32):
        raise ValueError("Shared key must contain exactly 32 random bytes")
    if strategy not in ("baseline", "balanced"):
        raise ValueError("Unknown sender strategy")
    _progress(progress, 35, "Try raw DEFLATE compression and calculate frame budgets")
    _, _, plan = plan_payload(message, cover.size, key is not None, profile)
    plan.update({"width": cover.shape[1], "height": cover.shape[0], "strategy": strategy})
    _progress(progress, 90, "Compare chosen and suggested frames (size-only; no embedding)")
    return plan


def _progress(callback, percent, stage, summary=None):
    if callback is not None:
        callback(percent, stage, summary)


def embed_pixels(cover, message: bytes, key: bytes | None = None, profile=Profile(), *,
                 strategy="baseline", random_bytes=secrets.token_bytes, progress=None):
    validate_pixels(cover)
    if strategy not in ("baseline", "balanced"):
        raise ValueError("Unknown sender strategy")
    started = time.perf_counter()
    h, w = cover.shape
    _progress(progress, 10, "Try raw DEFLATE compression and calculate frame budget")
    flag, data, plan = plan_payload(message, cover.size, key is not None, profile)
    summary = plan["chosen"]
    _progress(progress, 20, "Check stored message against frame capacity", summary)
    if not summary["supported"]:
        maximum_bytes = Profile("0.2").capacity(cover.size) - (66 if key is not None else 54)
        raise coding.EmbeddingError(
            f"Payload requires {len(data)} bytes; maximum at 0.2 bpp is "
            f"{maximum_bytes} bytes (minimum size-fitting rate: "
            f"{decimal_rate(summary['suggested_rate'], cover.size)} bpp)")
    profile = Profile(summary["chosen_rate"])
    total = summary["frame_bytes"]
    q, length = total - 32, total - 48
    if len(data) > summary["capacity_bytes"]:
        raise coding.EmbeddingError(f"Payload requires {len(data)} bytes; capacity is {summary['capacity_bytes']}")
    _progress(progress, 22, "Derive root/bootstrap keys and shuffle bootstrap/body pools")
    ctx = context(w, h, total)
    root = root_key(key)
    head, base = split_positions(cover.size, derive(root, "split", ctx))
    _progress(progress, 25, "Computing adaptive costs from wavelet residuals; protect wet pixels")
    minus, plus = compute_costs(cover)
    _progress(progress, 40, "Generate 32-byte random salt and derive purpose-specific body keys")
    salt = random_bytes(32)
    if len(salt) != 32:
        raise ValueError("Randomness provider returned an invalid salt")
    keys = message_keys(root, ctx, salt)
    _progress(progress, 42, "Pack 18-byte header, stored message and random padding")
    version = 1 if key is not None else 2
    frame = struct.pack(">BBQQ", version, flag, len(message), len(data)) + data
    if key is not None:
        frame += random_bytes(length - len(frame))
        aad = b"STEG-BP/1/aad\x00" + ctx + salt
        _progress(progress, 44, "ChaCha20-Poly1305 encryption + 16-byte tag; salt-derived key, zero nonce, context AAD")
        payload_bytes = ChaCha20Poly1305(keys["aead"]).encrypt(bytes(12), frame, aad)
    else:
        frame += (zlib.crc32(frame) & 0xFFFFFFFF).to_bytes(4, "big")
        frame += random_bytes(q - len(frame))
        # Public whitening makes the syndrome target less message-dependent;
        # anyone who knows the public layout can reverse it.
        payload_bytes = frame
    _progress(progress, 46, "XOR body with derived pseudorandom whitening stream")
    payload = bytes(a ^ b for a, b in zip(payload_bytes, Stream(keys["whiten"]).take(q), strict=True))
    _progress(progress, 48, "Shuffle body positions using the salt-derived permutation key")
    body = body_positions(cover.size, derive(root, "split", ctx), keys["body-perm"])
    original = cover.ravel()
    output = original.copy()
    signs = Stream(keys["sign"])
    distortion = 0
    for positions, target, code_key, start_percent, stage in (
        (head, bits(salt), derive(root, "head-code", ctx), 50, "bootstrap salt"),
        (body, bits(payload), keys["body-code"], 65, "payload body"),
    ):
        _progress(progress, start_percent,
                  f"{stage} pixel parities, dry-pixel check and parity matrix")
        x = original[positions] & 1
        costs = np.minimum(minus[positions], plus[positions])
        if np.count_nonzero(costs != coding.WET) < len(target):
            raise coding.EmbeddingError("Insufficient dry pixels")
        matrix = columns(len(x), len(target), 10, code_key)
        _progress(progress, start_percent + 5,
                  f"Embedding {stage} with minimum-cost syndrome-trellis coding")
        y, stage_cost = coding.embed(x, costs, target, matrix)
        _progress(progress, start_percent + 10,
                  f"Apply +/-1 {stage} changes and verify parity equations")
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
        _progress(progress, 80, "Balance modification signs while preserving every payload parity")
        from .balance import balance_signs
        stego, balance_info = balance_signs(cover, stego)
        if not np.array_equal(stego & 1, output.reshape(cover.shape) & 1):
            raise RuntimeError("Balancing changed a payload parity")
    _progress(progress, 88, "Count changed pixels and calculate distortion/PSNR statistics")
    changes = np.count_nonzero(stego != cover)
    return stego, {"rate": profile.rate, "strategy": strategy, "gross_bits": total * 8,
                   "stored_bytes": len(data), "message_bytes": len(message),
                   "changed_pixels": int(changes), "distortion": distortion,
                   "psnr": float(10 * np.log10(65025 * cover.size / changes)) if changes else float("inf"),
                   "seconds": time.perf_counter() - started, **balance_info}


def extract_pixels(stego, key: bytes | None = None, profile=Profile(), *, progress=None,
                   _reuse_embedding_matrices=False) -> bytes:
    try:
        _progress(progress, 10, "Validate image/profile and rebuild context and root key")
        validate_pixels(stego)
        h, w = stego.shape
        total = profile.capacity(stego.size)
        q, length = total - 32, total - 48
        ctx, root = context(w, h, total), root_key(key)
        _progress(progress, 18, f"Reconstruct bootstrap positions; rate "
                  f"{decimal_rate(profile.rate, stego.size)} bpp, {total}-byte frame")
        head, base = split_positions(stego.size, derive(root, "split", ctx))
        flat = stego.ravel()
        _progress(progress, 28, "Recover bootstrap syndrome and the 32-byte salt")
        salt = octets(extract_syndrome(flat[head] & 1, 256, 10, derive(root, "head-code", ctx),
                                      reuse_columns=_reuse_embedding_matrices))
        _progress(progress, 38, "Derive body keys from recovered salt and reconstruct body positions")
        keys = message_keys(root, ctx, salt)
        body = body_positions(stego.size, derive(root, "split", ctx), keys["body-perm"])
        _progress(progress, 50, "Recover body syndrome bits from image parities")
        payload = octets(extract_syndrome(flat[body] & 1, 8 * q, 10, keys["body-code"],
                                         reuse_columns=_reuse_embedding_matrices))
        _progress(progress, 65, "Pack bits into bytes and reverse XOR whitening")
        payload_bytes = bytes(a ^ b for a, b in zip(payload, Stream(keys["whiten"]).take(q), strict=True))
        if key is not None:
            _progress(progress, 73, "Verify authentication tag and decrypt with derived key, zero nonce and context AAD")
            aad = b"STEG-BP/1/aad\x00" + ctx + salt
            frame = ChaCha20Poly1305(keys["aead"]).decrypt(bytes(12), payload_bytes, aad)
        else:
            frame = payload_bytes
        _progress(progress, 82, "Validate header/lengths, check public CRC if applicable and discard padding")
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
            _progress(progress, 90, "Verify original length and recover unchanged message bytes")
            if len(data) != original_length:
                raise ValueError("Invalid raw length")
            return data
        _progress(progress, 90, "Bounded raw DEFLATE decompression and original-length verification")
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
    _progress(progress, 5, "Decode and validate the grayscale cover PNG")
    cover = decode_png(cover_png)
    stego, information = embed_pixels(cover, message, key, profile, strategy=strategy, progress=progress)
    _progress(progress, 90, "Serialize modified pixels as lossless PNG")
    result = encode_png(stego)
    _progress(progress, 95, "Decode saved PNG, check pixels and run full extraction self-check")
    decoded = decode_png(result)
    if not np.array_equal(decoded, stego) or extract_pixels(
            decoded, key, Profile(information["rate"]), _reuse_embedding_matrices=True) != message:
        raise RuntimeError("Post-serialization self-check failed")
    _progress(progress, 100, "Embedding verified")
    return result


def extract_and_decrypt(stego_png: bytes, key: bytes | None = None, profile=Profile(), *, progress=None) -> bytes:
    try:
        _progress(progress, 5, "Decode and validate the received grayscale PNG")
        return extract_pixels(decode_png(stego_png), key, profile, progress=progress)
    except (ValueError, OSError):
        message = "No valid authenticated payload" if key is not None else "No valid plaintext payload"
        raise ExtractionError(message) from None
