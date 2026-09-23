import hashlib
import itertools
import math
import struct

import numpy as np
import pytest

from stegolab import coding
from stegolab.costs import BANK, compute_costs, correlation
from stegolab.primitives import Stream, bits, columns, mac, octets, permute
from stegolab.system import (ExtractionError, Profile, decode_png, embed_pixels,
                             encode_png, extract_pixels)


def direct_syndrome(y, matrix, m):
    result = np.zeros(m, dtype=np.uint8)
    n = len(y)
    for row in range(m):
        for i in range(row * n // m, (row + 1) * n // m):
            for bit in range(min(10, m - row)):
                result[row + bit] ^= int(y[i]) * ((int(matrix[i]) >> bit) & 1)
    return result


def test_native_exhaustive():
    rng = np.random.default_rng(42)
    for n in range(1, 8):
        for m in range(1, n + 1):
            matrix = columns(n, m, 10, bytes(range(32)))
            x = rng.integers(0, 2, n, dtype=np.uint8)
            for wet in (False, True):
                costs = rng.integers(1, 30, n, dtype=np.uint32)
                if wet:
                    costs[::2] = coding.WET
                solutions = {}
                for y in itertools.product((0, 1), repeat=n):
                    sy = tuple(direct_syndrome(y, matrix, m))
                    distance = sum(int(costs[i]) if costs[i] != coding.WET else math.inf
                                   for i in range(n) if y[i] != x[i])
                    solutions[sy] = min(solutions.get(sy, math.inf), distance)
                for target in itertools.product((0, 1), repeat=m):
                    expected = solutions.get(target, math.inf)
                    if math.isinf(expected):
                        with pytest.raises(coding.EmbeddingError):
                            coding.embed(x, costs, target, matrix)
                    else:
                        y, distance = coding.embed(x, costs, target, matrix)
                        assert distance == expected
                        np.testing.assert_array_equal(coding.extract(y, m, matrix), target)
                        np.testing.assert_array_equal(direct_syndrome(y, matrix, m), target)


def test_stream_and_shuffle_are_wire_compatible():
    key = bytes(range(32))
    expected = b"".join(mac(key, b"STEG-BP/1/stream\x00" + i.to_bytes(8, "big")) for i in range(5))
    stream = Stream(key)
    assert stream.take(3) + stream.take(51) + stream.take(106) == expected
    simple = list(range(17))
    stream = Stream(key)
    for i in range(16, 0, -1):
        while True:
            value = int.from_bytes(stream.take(8), "big")
            if value < (1 << 64) - (1 << 64) % (i + 1):
                break
        j = value % (i + 1)
        simple[i], simple[j] = simple[j], simple[i]
    np.testing.assert_array_equal(permute(np.arange(17), key), simple)
    assert octets(bits(bytes(range(256)))) == bytes(range(256))


def reflect(index, length):
    value = index % (2 * length)
    return value if value < length else 2 * length - 1 - value


def test_filter_alignment_and_cost_impulse():
    image = np.random.default_rng(1).integers(0, 256, (64, 64), dtype=np.uint8)
    rho = 0.0
    for vertical, horizontal in BANK:
        kernel = np.outer(vertical, horizontal)
        residual = correlation(image.astype(float), vertical, horizontal, -1)
        for row, col in [(0, 0), (16, 16), (47, 47), (63, 63)]:
            direct = sum(kernel[u, v] * int(image[reflect(row + u - 7, 64),
                                                     reflect(col + v - 7, 64)])
                         for u in range(16) for v in range(16))
            assert residual[row, col] == pytest.approx(direct, abs=1e-10)
        row, col = 16, 16
        rho += sum(abs(kernel[u, v]) / (1 + abs(residual[row - u + 7, col - v + 7]))
                   for u in range(16) for v in range(16))
    minus, plus = compute_costs(image)
    assert minus[16 * 64 + 16] == max(1, math.floor(rho * 1e6 + 0.5))
    assert np.all(minus.reshape(64, 64)[:16] == coding.WET)
    flat_costs = compute_costs(np.full((64, 64), 127, dtype=np.uint8))
    assert all(np.all(cost == coding.WET) for cost in flat_costs)


@pytest.fixture(scope="module")
def cover():
    # Synthetic images are used for correctness, never as evidence of photographic security.
    return np.random.default_rng(331).integers(10, 245, (512, 512), dtype=np.uint8)


@pytest.mark.parametrize("message", [b"", bytes(range(256)), b"compressible" * 10000],
                         ids=["empty", "all-byte-values", "compressed"])
def test_authenticated_round_trip(cover, message):
    key = hashlib.sha256(b"test key only").digest()
    stego, info = embed_pixels(cover, message, key)
    assert info["gross_bits"] == 13104
    assert extract_pixels(decode_png(encode_png(stego)), key) == message
    assert np.max(np.abs(stego.astype(int) - cover.astype(int))) <= 1
    np.testing.assert_array_equal(stego[:16], cover[:16])
    with pytest.raises(ExtractionError):
        extract_pixels(stego, bytes(32))
    corrupted = stego.copy()
    corrupted[::2, ::2] ^= 1
    with pytest.raises(ExtractionError):
        extract_pixels(corrupted, key)


def test_boundaries_and_rejection(cover):
    with pytest.raises(coding.EmbeddingError):
        embed_pixels(np.full_like(cover, 127), b"x", bytes(32))
    with pytest.raises(coding.EmbeddingError):
        embed_pixels(cover, np.random.default_rng(11).bytes(2000), bytes(32))
    assert Profile().capacity(512 * 512) - 66 == 1572
    assert Profile("0.01").capacity(512 * 512) - 66 == 261
    for wrong in [cover.astype(np.uint16), cover[..., None], cover[:200]]:
        with pytest.raises(ValueError):
            embed_pixels(wrong, b"x", bytes(32))


def test_balancing_preserves_recovery(cover):
    from stegolab.balance import balance_signs
    key = hashlib.sha256(b"balance test key").digest()
    stego, _ = embed_pixels(cover, b"parity invariance", key, Profile("0.01"))
    balanced, info = balance_signs(cover, stego)
    np.testing.assert_array_equal(balanced & 1, stego & 1)
    np.testing.assert_array_equal(balanced != cover, stego != cover)
    assert np.max(np.abs(balanced.astype(int) - cover.astype(int))) <= 1
    assert info["balance_objective_after"] <= info["balance_objective_before"]
    assert extract_pixels(balanced, key, Profile("0.01")) == b"parity invariance"
