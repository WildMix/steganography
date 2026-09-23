"""Independent spatial steganalysis features (not a claim to implement full SRM)."""
from functools import lru_cache
import itertools

import numpy as np
from scipy.ndimage import correlate, uniform_filter

FILTERS = [
    np.array([[-1, 1]], dtype=np.int16),
    np.array([[-1], [1]], dtype=np.int16),
    np.array([[1, -2, 1]], dtype=np.int16),
    np.array([[1], [-2], [1]], dtype=np.int16),
    np.array([[-1, 3, -3, 1]], dtype=np.int16),
    np.array([[-1], [3], [-3], [1]], dtype=np.int16),
    np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.int16),
    np.array([[-1, 2, -1], [2, -4, 2], [-1, 2, -1]], dtype=np.int16),
    np.array([[-1, 0], [0, 1]], dtype=np.int16),
    np.array([[0, -1], [1, 0]], dtype=np.int16),
]


@lru_cache(maxsize=1)
def symmetry_map():
    patterns = list(itertools.product(range(5), repeat=4))
    canonical = [min(v, v[::-1], tuple(4-x for x in v), tuple(4-x for x in v[::-1]))
                 for v in patterns]
    classes = {v: i for i, v in enumerate(sorted(set(canonical)))}
    return np.array([classes[v] for v in canonical]), len(classes)


def cooccurrences(residual, quantization, mask=None):
    quantized = (np.sign(residual) * np.floor(np.abs(residual) / quantization + .5))
    quantized = np.clip(quantized, -2, 2).astype(np.int32) + 2
    mapping, dimension = symmetry_map()
    counts = np.zeros(dimension, dtype=np.float64)
    for sequence, selected in ((quantized, mask),
                                (quantized.T, None if mask is None else mask.T)):
        encoded = (sequence[:, :-3] * 125 + sequence[:, 1:-2] * 25
                   + sequence[:, 2:-1] * 5 + sequence[:, 3:])
        if selected is not None:
            encoded = encoded[selected[:, 1:-2]]
        counts += np.bincount(mapping[encoded.ravel()], minlength=dimension)
    total = counts.sum()
    return counts / total if total else counts


def extract_features(image):
    pixels = image.astype(np.int16)
    features = []
    residuals = [correlate(pixels, f, mode="reflect")[2:-2, 2:-2] for f in FILTERS]
    for residual in residuals:
        for quantization in (1, 2, 4):
            features.append(cooccurrences(residual, quantization))
    values = image.astype(np.float64)
    mean = uniform_filter(values, 5, mode="reflect")
    variance = np.maximum(0, uniform_filter(values * values, 5, mode="reflect") - mean * mean)[2:-2, 2:-2]
    # Selection-conditioned dependencies provide a detector the optimizer did not target.
    for residual in residuals[:4]:
        for low, high in ((0, 16), (16, 64), (64, 256), (256, float("inf"))):
            features.append(cooccurrences(residual, 1, (variance >= low) & (variance < high)))
    histogram = np.bincount(image.ravel(), minlength=256).astype(float) / image.size
    features.extend([histogram, histogram[::2] - histogram[1::2]])
    # RS-like smoothness responses. No calibration to a direct-LSB payload estimator is assumed.
    rs = []
    for values in (pixels, pixels.T):
        groups = values[:, :values.shape[1] // 4 * 4].reshape(-1, 4)
        rough = np.abs(np.diff(groups, axis=1)).sum(axis=1)
        for pattern in ((1, 0, 1, 0), (0, 1, 0, 1), (1, 1, 1, 1)):
            toggled = groups ^ np.array(pattern)
            difference = np.abs(np.diff(toggled, axis=1)).sum(axis=1) - rough
            rs.extend([np.mean(difference > 0), np.mean(difference < 0), np.mean(difference == 0)])
    features.append(np.asarray(rs))
    return np.concatenate(features).astype(np.float32)

