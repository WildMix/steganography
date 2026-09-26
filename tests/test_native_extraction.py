"""Fused extraction is an exact evaluation of the existing parity matrix."""
import hmac
from types import SimpleNamespace

import numpy as np
import pytest

from stegolab import coding, primitives as p, system


@pytest.fixture(autouse=True)
def clean_backend(monkeypatch):
    monkeypatch.setenv("STEGOLAB_NATIVE_PRIMITIVES", "1")
    monkeypatch.delenv("STEGOLAB_NATIVE_EXTRACT", raising=False)
    cached_functions = (p.columns, p.split_positions, p.body_positions)
    for function in cached_functions:
        function.cache_clear()
    yield
    for function in cached_functions:
        function.cache_clear()


@pytest.fixture
def native():
    backend = p._native_backend()
    if backend is None or not hasattr(backend, "wire_extract"):
        pytest.skip("Rebuild the optional Windows native extraction backend")
    return backend


def independent_columns(n, m, height, key):
    result = np.empty(n, dtype=np.uint16)
    for row in range(m):
        for col in range(row * n // m, (row + 1) * n // m):
            data = b"STEG-BP/1/column\x00" + row.to_bytes(4, "big") + col.to_bytes(8, "big")
            digest = hmac.digest(key, data, "sha256")
            mask = int.from_bytes(digest[:2], "big") | 1 | (1 << (height - 1))
            result[col] = mask & ((1 << min(height, m - row)) - 1)
    return result


@pytest.mark.parametrize("height", range(1, 16))
@pytest.mark.parametrize("pattern", ["zeros", "ones", "mixed"])
def test_fused_matches_independent_matrix(native, height, pattern):
    n, m = 103, 19  # Unequal block sizes and truncated final rows.
    parity = {"zeros": np.zeros(n, dtype=np.uint8), "ones": np.ones(n, dtype=np.uint8),
              "mixed": np.random.default_rng(741).integers(0, 2, n, dtype=np.uint8)}[pattern]
    key = bytes(range(32))
    matrix = independent_columns(n, m, height, key)
    expected = np.zeros(m, dtype=np.uint8)
    for row in range(m):
        for col in range(row * n // m, (row + 1) * n // m):
            for bit in range(min(height, m - row)):
                expected[row + bit] ^= parity[col] * ((int(matrix[col]) >> bit) & 1)
    np.testing.assert_array_equal(coding.extract(parity, m, matrix, height), expected)
    np.testing.assert_array_equal(p.extract_syndrome(parity, m, height, key), expected)
    assert p.columns.cache_info().misses == 0  # No full-matrix allocation/cache population.


@pytest.mark.parametrize("n,m,height", [(1, 1, 1), (33, 1, 10), (17, 17, 15), (4096, 3, 15)])
@pytest.mark.parametrize("key", [b"", b"x", bytes(range(32)), bytes(range(64)), bytes(range(100))])
def test_boundaries_and_key_lengths(native, n, m, height, key):
    # Strided input is accepted and normalized at the Python/native boundary.
    parity = np.random.default_rng(n).integers(0, 2, n * 2, dtype=np.uint8)[::2]
    expected = coding.extract(parity, m, independent_columns(n, m, height, key), height)
    np.testing.assert_array_equal(p.extract_syndrome(parity, m, height, key), expected)


@pytest.mark.parametrize("reason", ["old_dll", "unavailable", "disabled", "all_disabled", "reuse"])
def test_dispatch_falls_back_to_existing_matrix_path(monkeypatch, reason):
    key, parity = bytes(32), np.arange(71, dtype=np.uint8) & 1
    expected = coding.extract(parity, 13, independent_columns(71, 13, 10, key))
    if reason == "old_dll":
        monkeypatch.setattr(p, "_accelerator", lambda: SimpleNamespace())
    elif reason == "unavailable":
        monkeypatch.setattr(p, "_accelerator", lambda: None)
    elif reason == "disabled":
        monkeypatch.setenv("STEGOLAB_NATIVE_EXTRACT", "0")
    elif reason == "all_disabled":
        monkeypatch.setenv("STEGOLAB_NATIVE_PRIMITIVES", "0")
    # Prepopulate before replacing columns; an old DLL still provides wire_columns.
    matrix = independent_columns(71, 13, 10, key)
    calls = []

    def cached_columns(*args):
        calls.append(args)
        return matrix

    monkeypatch.setattr(p, "columns", cached_columns)
    actual = p.extract_syndrome(parity, 13, 10, key, reuse_columns=reason == "reuse")
    np.testing.assert_array_equal(actual, expected)
    assert calls == [(71, 13, 10, key)]


def test_native_failure_is_not_hidden_by_fallback(monkeypatch):
    monkeypatch.setattr(p, "_accelerator", lambda: SimpleNamespace(wire_extract=lambda *args: -1))
    with pytest.raises(RuntimeError, match="Native wire primitive failed: -1"):
        p.extract_syndrome(np.zeros(20, dtype=np.uint8), 5, 10, bytes(32))
    assert p.columns.cache_info().misses == 0


@pytest.mark.parametrize("parity,m,height", [([], 1, 10), ([0], 0, 10), ([0], 2, 10),
    ([0], 1, 0), ([0], 1, 16), ([2], 1, 10), ([-1], 1, 10), ([256], 1, 10),
    ([0.5], 1, 10), ([[0, 1]], 1, 10)])
def test_invalid_input_rejected(parity, m, height):
    with pytest.raises(ValueError, match="Invalid extraction"):
        p.extract_syndrome(np.asarray(parity), m, height, bytes(32))


@pytest.mark.parametrize("n,m,height", [(1, 0, 10), (1, 2, 10), (1, 1, 0),
                                        (1, 1, 16), (1 << 63, 3, 10),
                                        ((1 << 32) + 1, (1 << 32) + 1, 10)])
def test_native_rejects_invalid_dimensions_before_access(native, n, m, height):
    value = np.zeros(1, dtype=np.uint8)
    assert native.wire_extract(value, n, m, height, bytes(32), 32, value) == -2


def test_native_rejects_nonbinary_values(native):
    assert native.wire_extract(np.array([2], dtype=np.uint8), 1, 1, 10,
                               bytes(32), 32, np.zeros(1, dtype=np.uint8)) == -2


@pytest.mark.parametrize("key", [bytes(range(32)), None])
def test_embedding_self_check_reuses_matrices_then_standalone_uses_fused(native, monkeypatch, key):
    cover = np.random.default_rng(91).integers(0, 256, (512, 512), dtype=np.uint8)
    actual_fused, calls = native.wire_extract, []

    def counted(*args):
        calls.append(1)
        return actual_fused(*args)

    monkeypatch.setattr(native, "wire_extract", counted)
    message = b"self-check keeps its cached matrices" * 30
    encoded = system.encrypt_and_embed(system.encode_png(cover), message, key, system.Profile("0.05"))
    assert not calls
    assert p.columns.cache_info().misses == 2
    assert p.columns.cache_info().hits == 2
    assert system.extract_and_decrypt(encoded, key, system.Profile("0.05")) == message
    assert len(calls) == 2
    if key is not None:
        with pytest.raises(system.ExtractionError, match="No valid authenticated payload"):
            system.extract_and_decrypt(encoded, bytes(32), system.Profile("0.05"))
        with pytest.raises(system.ExtractionError, match="No valid authenticated payload"):
            system.extract_and_decrypt(encoded, key, system.Profile("0.04"))
