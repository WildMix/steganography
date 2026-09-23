"""Experimental source-conditioned residual balancing, developed in this workspace.

No claim of literature novelty is made. Only modification signs change; this
preserves all payload parity constraints and the original unit-change locations.
Independent steganalyzers must check whether improving this surrogate helps.
"""
import ctypes

import numpy as np
from scipy.ndimage import uniform_filter

from .coding import library


def balance_signs(cover, stego, rounds=6):
    if cover.dtype != np.uint8 or cover.ndim != 2 or stego.shape != cover.shape:
        raise ValueError("Invalid balancing images")
    delta = stego.astype(np.int16) - cover.astype(np.int16)
    if np.max(np.abs(delta)) > 1:
        raise ValueError("Sign balancing requires only unit changes")
    values = cover.astype(np.float64)
    mean = uniform_filter(values, 5, mode="reflect")
    variance = np.maximum(0, uniform_filter(values * values, 5, mode="reflect") - mean * mean)
    strata = np.digitize(variance, [16, 64, 256]).astype(np.uint8)
    result = np.array(stego, order="C", copy=True)
    source = np.ascontiguousarray(cover)
    raw = np.ctypeslib.ndpointer(dtype=np.uint8, ndim=1, flags="C_CONTIGUOUS")
    function = library().balance_signs
    function.argtypes = [raw, raw, raw, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
    function.restype = ctypes.c_int
    before, after = ctypes.c_double(), ctypes.c_double()
    accepted = function(source.ravel(), result.ravel(), strata.ravel(), *cover.shape, rounds,
                        ctypes.byref(before), ctypes.byref(after))
    if accepted < 0:
        raise RuntimeError("Native balancing failed")
    if not np.array_equal(result & 1, stego & 1):
        raise RuntimeError("Balancing corrupted parity")
    return result, {"balance_flips": accepted, "balance_objective_before": before.value,
                    "balance_objective_after": after.value}
