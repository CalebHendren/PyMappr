"""Point-density heatmap: 2D histogram smoothed with a gaussian kernel."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

__all__ = ["compute_heatmap"]

GRID = 512  # cells along the longer side of the data extent


def compute_heatmap(lons, lats, radius: float = 10.0,
                    grid: int = GRID) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Return (density image, extent) for imshow.

    *radius* is the gaussian sigma in grid cells (the UI exposes it as a
    "radius" slider). The extent is the data bounding box padded by three
    sigmas so the blur never clips at the edges. The returned image is
    oriented for ``imshow(..., origin="lower")`` and normalised to [0, 1].
    """
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    if lons.size == 0:
        raise ValueError("no points to build a heatmap from")

    x0, x1 = float(lons.min()), float(lons.max())
    y0, y1 = float(lats.min()), float(lats.max())
    span = max(x1 - x0, y1 - y0, 1e-6)
    cell = span / grid
    pad = max(3.0 * radius * cell, cell * 8)
    x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad

    nx = max(int(round((x1 - x0) / cell)), 8)
    ny = max(int(round((y1 - y0) / cell)), 8)
    hist, _, _ = np.histogram2d(lats, lons, bins=(ny, nx),
                                range=((y0, y1), (x0, x1)))
    density = gaussian_filter(hist, sigma=radius)
    peak = density.max()
    if peak > 0:
        density /= peak
    return density, (x0, x1, y0, y1)
