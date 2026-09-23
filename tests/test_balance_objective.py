import numpy as np
import pytest
from scipy.ndimage import correlate, uniform_filter

from stegolab.balance import balance_signs


def reference_objective(cover, stego):
    kernels = [
        [[0,0,0],[0,-1,1],[0,0,0]], [[0,0,0],[0,-1,0],[0,1,0]],
        [[0,0,0],[1,-2,1],[0,0,0]], [[0,1,0],[0,-2,0],[0,1,0]],
        [[0,0,0],[0,-1,0],[0,0,1]], [[0,0,0],[0,-1,0],[1,0,0]],
        [[0,1,0],[1,-4,1],[0,1,0]], [[-1,2,-1],[2,-4,2],[-1,2,-1]],
    ]
    x = cover.astype(float)
    activity = np.maximum(0, uniform_filter(x*x, 5) - uniform_filter(x, 5)**2)
    groups = np.digitize(activity, [16, 64, 256])[2:-2, 2:-2]
    objective = 0.0
    for kernel in kernels:
        a = correlate(cover.astype(np.int16), np.array(kernel))[2:-2, 2:-2]
        b = correlate(stego.astype(np.int16), np.array(kernel))[2:-2, 2:-2]
        for q in (1, 2, 4):
            def bins(residual):
                rounded = np.sign(residual) * ((np.abs(residual) + q // 2) // q)
                return np.clip(rounded, -8, 8).astype(int) + 8
            aq, bq = bins(a), bins(b)
            for group in range(4):
                original = np.bincount(aq[groups == group], minlength=17)
                current = np.bincount(bq[groups == group], minlength=17)
                objective += np.sum((current-original)**2 / (original+32))
    return objective


def test_incremental_objective_matches_independent_recomputation():
    rng = np.random.default_rng(691)
    cover = rng.integers(0, 256, (64, 64), dtype=np.uint8)
    cover[:32] = rng.integers(120, 140, (32, 64), dtype=np.uint8)
    stego = cover.copy()
    sub = stego[17:47:3, 17:47:3]
    sub[:] = np.where(sub == 255, 254, sub.astype(int) + 1)
    result, info = balance_signs(cover, stego)
    assert info["balance_objective_before"] == pytest.approx(reference_objective(cover, stego), abs=1e-10)
    assert info["balance_objective_after"] == pytest.approx(reference_objective(cover, result), abs=1e-10)
    np.testing.assert_array_equal(result != cover, stego != cover)
