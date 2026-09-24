"""Wire-compatible primitive inputs and byte ordering for STEG-BP/1."""
from functools import lru_cache
import hashlib
import hmac
import struct

import numpy as np


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
            for _ in range((count - available + 31) // 32):
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


def bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8), bitorder="big")


def octets(values: np.ndarray) -> bytes:
    if len(values) % 8:
        raise ValueError("Bit count must be divisible by eight")
    return np.packbits(values, bitorder="big").tobytes()
