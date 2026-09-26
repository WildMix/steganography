"""Cross-check accelerated wire bytes against independent stdlib calculations."""
import hashlib
import hmac
import random

import numpy as np
import pytest

from stegolab import primitives as p
from stegolab.system import Profile, embed_pixels, encode_png, extract_pixels


@pytest.fixture(autouse=True)
def native_backend(monkeypatch):
    if p._native_backend() is None:
        pytest.skip("Optional Windows primitive acceleration is unavailable")
    monkeypatch.setenv("STEGOLAB_NATIVE_PRIMITIVES", "1")
    clear_layouts()
    yield
    clear_layouts()


def clear_layouts():
    for function in (p.columns, p.split_positions, p.body_positions):
        function.cache_clear()


def reference_stream(key, first, blocks):
    return b"".join(hmac.digest(key, b"STEG-BP/1/stream\x00" + i.to_bytes(8, "big"), "sha256")
                    for i in range(first, first + blocks))


@pytest.mark.parametrize("key", [b"", b"x", bytes(range(32)), bytes(range(64)), bytes(range(100))])
def test_native_stream_fragmentation_and_counters(key):
    stream = p.Stream(key)
    stream.counter = (1 << 32) + 9
    lengths = [0, 1, 31, 33, 2048, 7]
    result = b"".join(stream.take(length) for length in lengths)
    expected = reference_stream(key, (1 << 32) + 9, (len(result) + 31) // 32)
    assert result == expected[:len(result)]
    stream = p.Stream(key)
    stream.counter = (1 << 64) - 1
    assert stream.take(32) == reference_stream(key, (1 << 64) - 1, 1)
    with pytest.raises(OverflowError):
        stream.take(1)
    with pytest.raises(ValueError):
        stream.take(-1)


@pytest.mark.parametrize("n", [0, 1, 2, 17, 257, 10000])
def test_native_shuffle_matches_reference(n):
    key = hashlib.sha256(str(n).encode()).digest()
    original = np.arange(n, dtype=np.int64) * 3 - 900
    expected = original.tolist()
    stream = reference_stream(key, 0, (max(0, n - 1) * 8 + 31) // 32 + 32)
    cursor = 0
    for i in range(n - 1, 0, -1):
        while True:
            value = int.from_bytes(stream[cursor:cursor + 8], "big")
            cursor += 8
            if value < (1 << 64) - (1 << 64) % (i + 1):
                break
        j = value % (i + 1)
        expected[i], expected[j] = expected[j], expected[i]
    np.testing.assert_array_equal(p.permute(original, key), expected)
    np.testing.assert_array_equal(original, np.arange(n) * 3 - 900)


@pytest.mark.parametrize("n,m,height", [(1, 1, 1), (33, 1, 10), (17, 17, 15),
                                        (100, 7, 2), (1000, 392, 10), (4096, 3, 15)])
def test_native_matrix_matches_reference(n, m, height):
    key = bytes(range(32))
    expected = np.empty(n, dtype=np.uint16)
    for row in range(m):
        for col in range(row * n // m, (row + 1) * n // m):
            data = b"STEG-BP/1/column\x00" + row.to_bytes(4, "big") + col.to_bytes(8, "big")
            digest = hmac.digest(key, data, "sha256")
            mask = (int.from_bytes(digest[:2], "big") & ((1 << height) - 1)) | 1 | (1 << (height - 1))
            expected[col] = mask & ((1 << min(height, m - row)) - 1)
    actual = p.columns(n, m, height, key)
    np.testing.assert_array_equal(actual, expected)
    assert not actual.flags.writeable


@pytest.mark.parametrize("message,rate,strategy,key", [
    (b"HELLO", "auto", "balanced", bytes(range(32))),
    (bytes(range(256)), "0.05", "baseline", bytes(range(32))),
    (b"compressible" * 1000, "auto", "balanced", bytes(range(32))),
    (b"", "auto", "baseline", bytes(range(32))),
    (b"public compatibility", "0.05", "balanced", None),
])
def test_identical_png_and_cross_backend_extraction(monkeypatch, message, rate, strategy, key):
    cover = np.random.default_rng(812).integers(0, 256, (512, 512), dtype=np.uint8)
    outputs = []
    for backend in ("0", "1"):
        monkeypatch.setenv("STEGOLAB_NATIVE_PRIMITIVES", backend)
        clear_layouts()
        stego, info = embed_pixels(cover, message, key, Profile(rate), strategy=strategy,
                                  random_bytes=random.Random(6739).randbytes)
        outputs.append((stego, info, encode_png(stego)))
    np.testing.assert_array_equal(outputs[0][0], outputs[1][0])
    assert outputs[0][2] == outputs[1][2]
    for field in outputs[0][1]:
        if field != "seconds":
            assert outputs[0][1][field] == outputs[1][1][field]
    # Read each backend's output using the other backend, without cached maps.
    for backend, output in zip(("1", "0"), outputs, strict=True):
        monkeypatch.setenv("STEGOLAB_NATIVE_PRIMITIVES", backend)
        clear_layouts()
        assert extract_pixels(output[0], key, Profile(output[1]["rate"])) == message
