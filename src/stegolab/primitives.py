"""Wire-compatible primitive inputs and byte ordering for STEG-BP/1."""
from functools import lru_cache
import ctypes
import hashlib
import hmac
import os
import struct

import numpy as np


@lru_cache(maxsize=1)
def _native_backend():
    """Optional batch implementation; old native engines keep working."""
    if os.name != "nt":
        return None
    from .coding import library
    try:
        lib = library()
    except (OSError, RuntimeError):
        return None
    if not hasattr(lib, "wire_backend_version") or lib.wire_backend_version() != 1:
        return None
    u8 = np.ctypeslib.ndpointer(dtype=np.uint8, ndim=1, flags="C_CONTIGUOUS")
    u16 = np.ctypeslib.ndpointer(dtype=np.uint16, ndim=1, flags="C_CONTIGUOUS")
    i64 = np.ctypeslib.ndpointer(dtype=np.int64, ndim=1, flags="C_CONTIGUOUS")
    lib.wire_stream.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, u8]
    lib.wire_stream.restype = ctypes.c_int
    lib.wire_permute.argtypes = [i64, ctypes.c_uint64, ctypes.c_char_p, ctypes.c_uint64]
    lib.wire_permute.restype = ctypes.c_int
    lib.wire_columns.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32,
                                ctypes.c_char_p, ctypes.c_uint64, u16]
    lib.wire_columns.restype = ctypes.c_int
    # Additive export: an already installed version-1 DLL remains usable.
    if hasattr(lib, "wire_extract"):
        lib.wire_extract.argtypes = [u8, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32,
                                     ctypes.c_char_p, ctypes.c_uint64, u8]
        lib.wire_extract.restype = ctypes.c_int
    return lib


def _accelerator():
    # Diagnostic/reference switch, not a wire-format or cryptography setting.
    return None if os.environ.get("STEGOLAB_NATIVE_PRIMITIVES") == "0" else _native_backend()


def _check_native(status):
    if status:
        raise RuntimeError(f"Native wire primitive failed: {status}")


def mac(key: bytes, data: bytes) -> bytes:
    return hmac.digest(key, data, "sha256")


def context(width: int, height: int, size: int) -> bytes:
    return b"STEG-BP/1" + struct.pack(">IIQB", width, height, size, 10)


def root_key(key: bytes | None) -> bytes:
    if key is None:
        # Deliberately public: supports interoperable, unencrypted no-key mode.
        key = hashlib.sha256(b"STEG-BP/1/public-plaintext-layout").digest()
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("Shared key must contain exactly 32 random bytes")
    return mac(hashlib.sha256(b"STEG-BP/1/root").digest(), key)


def derive(prk: bytes, label: str, ctx: bytes) -> bytes:
    return mac(prk, label.encode("ascii") + b"\x00" + ctx + b"\x01")


class Stream:
    def __init__(self, key: bytes):
        self.key = key
        self.counter = 0
        self.buffer = bytearray()
        self.position = 0

    def take(self, count: int) -> bytes:
        if count < 0:
            raise ValueError("Negative stream length")
        available = len(self.buffer) - self.position
        if available < count:
            self.buffer = self.buffer[self.position:]
            self.position = 0
            blocks = (count - available + 31) // 32
            accelerator = _accelerator()
            if accelerator is not None and self.counter + blocks <= 1 << 64:
                output = np.empty(blocks * 32, dtype=np.uint8)
                _check_native(accelerator.wire_stream(bytes(self.key), len(self.key),
                                                     self.counter, blocks, output))
                self.buffer.extend(output.tobytes())
                self.counter += blocks
                blocks = 0
            for _ in range(blocks):
                if self.counter >= 1 << 64:
                    raise OverflowError("Stream exhausted")
                self.buffer.extend(mac(self.key, b"STEG-BP/1/stream\x00"
                                       + self.counter.to_bytes(8, "big")))
                self.counter += 1
        result = bytes(self.buffer[self.position:self.position + count])
        self.position += count
        return result


def permute(values: np.ndarray, key: bytes) -> np.ndarray:
    result = np.array(values, dtype=np.int64, copy=True)
    accelerator = _accelerator()
    if accelerator is not None and result.ndim == 1:
        _check_native(accelerator.wire_permute(result, len(result), bytes(key), len(key)))
        return result
    stream = Stream(key)
    # Fetch the ordinary draws in one batch without changing stream order.
    block = stream.take(max(0, len(result) - 1) * 8)
    cursor = 0
    for i in range(len(result) - 1, 0, -1):
        bound = i + 1
        threshold = (1 << 64) - ((1 << 64) % bound)
        while True:
            if cursor < len(block):
                value = struct.unpack_from(">Q", block, cursor)[0]
                cursor += 8
            else:
                value = int.from_bytes(stream.take(8), "big")
            if value < threshold:
                break
        j = value % bound
        result[i], result[j] = result[j], result[i]
    return result


@lru_cache(maxsize=8)
def split_positions(n: int, key: bytes) -> tuple[np.ndarray, np.ndarray]:
    order = permute(np.arange(n), key)
    order.flags.writeable = False
    return order[:n // 8], order[n // 8:]


@lru_cache(maxsize=8)
def body_positions(n: int, split_key: bytes, body_key: bytes) -> np.ndarray:
    result = permute(split_positions(n, split_key)[1], body_key)
    result.flags.writeable = False
    return result


@lru_cache(maxsize=8)
def columns(n: int, m: int, height: int, key: bytes) -> np.ndarray:
    if not 1 <= m <= n or not 1 <= height <= 15:
        raise ValueError("Invalid matrix dimensions")
    result = np.empty(n, dtype=np.uint16)
    accelerator = _accelerator()
    if accelerator is not None:
        _check_native(accelerator.wire_columns(n, m, height, bytes(key), len(key), result))
        result.flags.writeable = False
        return result
    bitmask = (1 << height) - 1
    forced = 1 | (1 << (height - 1))
    for row in range(m):
        prefix = b"STEG-BP/1/column\x00" + row.to_bytes(4, "big")
        active = (1 << min(height, m - row)) - 1
        for col in range(row * n // m, (row + 1) * n // m):
            digest = mac(key, prefix + col.to_bytes(8, "big"))
            result[col] = ((int.from_bytes(digest[:2], "big") & bitmask) | forced) & active
    result.flags.writeable = False
    return result


def extract_syndrome(parity: np.ndarray, m: int, height: int, key: bytes, *,
                     reuse_columns: bool = False) -> np.ndarray:
    """Recover the same syndrome without hashing zero-parity columns.

    Embedding's self-check opts into its already populated matrix cache. The
    fallback also supports older DLLs, non-Windows hosts and diagnostic flags.
    Native failures propagate; they never silently switch implementations.
    """
    from . import coding
    parity = np.asarray(parity)
    if (parity.ndim != 1 or not 1 <= m <= len(parity) or not 1 <= height <= 15
            or np.any((parity != 0) & (parity != 1))):
        raise ValueError("Invalid extraction dimensions or parity bits")
    parity = np.ascontiguousarray(parity, dtype=np.uint8)
    accelerator = _accelerator()
    if (not reuse_columns and os.environ.get("STEGOLAB_NATIVE_EXTRACT") != "0"
            and accelerator is not None and hasattr(accelerator, "wire_extract")):
        result = np.empty(m, dtype=np.uint8)
        _check_native(accelerator.wire_extract(parity, len(parity), m, height,
                                              bytes(key), len(key), result))
        return result
    return coding.extract(parity, m, columns(len(parity), m, height, key), height)


def bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8), bitorder="big")


def octets(values: np.ndarray) -> bytes:
    if len(values) % 8:
        raise ValueError("Bit count must be divisible by eight")
    return np.packbits(values, bitorder="big").tobytes()
