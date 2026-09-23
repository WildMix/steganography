"""Exact blueprint filter alignment; all optimization weights are integer-valued."""
import numpy as np
from scipy.ndimage import correlate1d, uniform_filter

from .coding import WET

LOW = np.array([
    -0.00011747678412476953, 0.0006754494064505693,
    -0.00039174037337694705, -0.004870352993451574,
    0.008746094047405777, 0.013981027917398282,
    -0.044088253930794755, -0.017369301001807547,
    0.12874742662047847, 0.0004724845739132828,
    -0.2840155429615824, -0.015829105256349306,
    0.5853546836542067, 0.6756307362972898,
    0.3128715909144659, 0.05441584224310401,
], dtype=np.float64)
HIGH = (-1.0) ** (np.arange(16) + 1) * LOW[::-1]
BANK = [(LOW, HIGH), (HIGH, LOW), (HIGH, HIGH)]


def correlation(image, vertical, horizontal, origin):
    return correlate1d(correlate1d(image, vertical, axis=0, mode="reflect", origin=origin),
                       horizontal, axis=1, mode="reflect", origin=origin)


def compute_costs(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    source = image.astype(np.float64)
    raw = np.zeros_like(source)
    for vertical, horizontal in BANK:
        # scipy's even-kernel anchor is 8+origin; the blueprint uses anchor 7.
        residual = correlation(source, vertical, horizontal, origin=-1)
        # Reversing a 16-tap kernel changes anchor 7 into anchor 8.
        raw += correlation(1.0 / (1.0 + np.abs(residual)),
                           np.abs(vertical[::-1]), np.abs(horizontal[::-1]), origin=0)
    if not np.isfinite(raw).all() or np.any(raw <= 0):
        raise ValueError("Invalid residual cost")
    integer = np.maximum(1, np.floor(raw * 1_000_000 + 0.5)).astype(np.uint32)
    # Rounded box-filter sums are exact integers for 25 8-bit samples.
    s1 = np.rint(uniform_filter(source, size=5, mode="reflect") * 25).astype(np.int64)
    s2 = np.rint(uniform_filter(source * source, size=5, mode="reflect") * 25).astype(np.int64)
    wet = (25 * s2 - s1 * s1) <= 625
    wet[:16] = True
    wet[-16:] = True
    wet[:, :16] = True
    wet[:, -16:] = True
    minus, plus = integer.copy(), integer.copy()
    minus[wet | (image == 0)] = WET
    plus[wet | (image == 255)] = WET
    return minus.ravel(), plus.ravel()

