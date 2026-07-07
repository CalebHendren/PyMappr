"""Point-density heatmap: 2D histogram smoothed with a gaussian kernel.

Supports the full set of UI options: radius (bandwidth), extra blur
(smoothing), intensity (weight/gamma), a low-density threshold, discrete
classification levels, and an optional bloom/glow layer computed by the
renderer from the same density grid.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

__all__ = ["compute_heatmap"]

GRID = 512  # cells along the longer side of the data extent


def compute_heatmap(lons, lats, radius: float = 10.0, blur: float = 0.0,
                    intensity: float = 1.0, threshold: float = 0.0,
                    levels: int = 0, weights=None,
                    grid: int = GRID) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Return (density image, extent) for imshow.

    *radius* is the gaussian bandwidth in grid cells (the area of influence
    of each point). *blur* adds extra gaussian smoothing on top of the
    bandwidth. *intensity* is a gamma-style weight: values above 1 boost
    faint areas, values below 1 emphasise only the hottest spots.
    *threshold* (0-1) clips densities below that fraction of the peak to
    zero. *levels* > 1 quantises the density into that many discrete
    classes. *weights* optionally weighs each point in the histogram.

    The extent is the data bounding box padded by three sigmas so the blur
    never clips at the edges. The returned image is oriented for
    ``imshow(..., origin="lower")`` and normalised to [0, 1].
    """
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    if lons.size == 0:
        raise ValueError("no points to build a heatmap from")

    x0, x1 = float(lons.min()), float(lons.max())
    y0, y1 = float(lats.min()), float(lats.max())
    span = max(x1 - x0, y1 - y0, 1e-6)
    cell = span / grid
    sigma = radius + blur
    pad = max(3.0 * sigma * cell, cell * 8)
    x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad

    nx = max(int(round((x1 - x0) / cell)), 8)
    ny = max(int(round((y1 - y0) / cell)), 8)
    hist, _, _ = np.histogram2d(lats, lons, bins=(ny, nx),
                                range=((y0, y1), (x0, x1)), weights=weights)
    density = gaussian_filter(hist, sigma=radius)
    if blur > 0:
        density = gaussian_filter(density, sigma=blur)
    peak = density.max()
    if peak > 0:
        density /= peak

    if intensity > 0 and intensity != 1.0:
        # Gamma curve: intensity > 1 lifts faint regions, < 1 suppresses.
        density = np.power(density, 1.0 / intensity)

    if threshold > 0:
        density = np.where(density >= threshold, density, 0.0)

    if levels > 1:
        # Classify into equal-interval bins; keep zeros fully transparent.
        quantised = np.ceil(density * levels) / levels
        density = np.where(density > 0, quantised, 0.0)

    return density, (x0, x1, y0, y1)
