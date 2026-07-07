import numpy as np
import pytest

from ezmaps.heatmap import compute_heatmap


def cluster(n=50, cx=0.0, cy=0.0, spread=1.0, seed=0):
    rng = np.random.default_rng(seed)
    return (cx + rng.normal(0, spread, n), cy + rng.normal(0, spread, n))


def test_basic_density_normalised():
    lons, lats = cluster()
    density, extent = compute_heatmap(lons, lats)
    assert density.max() == pytest.approx(1.0)
    assert density.min() >= 0.0
    x0, x1, y0, y1 = extent
    assert x0 < lons.min() and x1 > lons.max()
    assert y0 < lats.min() and y1 > lats.max()


def test_empty_raises():
    with pytest.raises(ValueError):
        compute_heatmap([], [])


def test_blur_smooths():
    """Extra blur spreads the density: more non-trivial cells."""
    lons, lats = cluster(n=20, spread=0.3)
    sharp, _ = compute_heatmap(lons, lats, radius=4, blur=0)
    smooth, _ = compute_heatmap(lons, lats, radius=4, blur=10)
    assert (smooth > 0.05).sum() > (sharp > 0.05).sum()


def test_intensity_gamma():
    lons, lats = cluster()
    base, _ = compute_heatmap(lons, lats, intensity=1.0)
    boosted, _ = compute_heatmap(lons, lats, intensity=3.0)
    dimmed, _ = compute_heatmap(lons, lats, intensity=0.5)
    mid = (base > 0.05) & (base < 0.95)
    assert (boosted[mid] >= base[mid]).all()
    assert (dimmed[mid] <= base[mid]).all()


def test_threshold_clips_faint_areas():
    lons, lats = cluster()
    density, _ = compute_heatmap(lons, lats, threshold=0.4)
    nonzero = density[density > 0]
    assert (nonzero >= 0.4).all()


def test_levels_quantise():
    lons, lats = cluster()
    density, _ = compute_heatmap(lons, lats, levels=5)
    values = np.unique(np.round(density, 6))
    expected = np.round(np.arange(0, 6) / 5.0, 6)
    assert set(values).issubset(set(expected))
    assert len(values) <= 6


def test_weights_shift_peak():
    """A heavily weighted point away from the cluster becomes the peak."""
    lons = np.array([0.0, 0.1, -0.1, 5.0])
    lats = np.array([0.0, 0.1, -0.1, 5.0])
    weights = np.array([1.0, 1.0, 1.0, 50.0])
    density, extent = compute_heatmap(lons, lats, radius=5, weights=weights)
    ny, nx = density.shape
    iy, ix = np.unravel_index(density.argmax(), density.shape)
    x0, x1, y0, y1 = extent
    peak_lon = x0 + (ix + 0.5) / nx * (x1 - x0)
    peak_lat = y0 + (iy + 0.5) / ny * (y1 - y0)
    assert peak_lon == pytest.approx(5.0, abs=0.5)
    assert peak_lat == pytest.approx(5.0, abs=0.5)


def test_sample_datasets_load():
    """The bundled Wyoming and dog-breed sample CSVs parse cleanly."""
    from pathlib import Path

    from ezmaps.data_loader import load_csv

    root = Path(__file__).resolve().parent.parent / "sample_data"

    wyoming = load_csv(str(root / "wyoming_cities.csv"))
    assert wyoming.skipped == []
    assert wyoming.name_labels == ["Country", "State", "County", "City"]
    assert len(wyoming) >= 20
    density, _ = compute_heatmap(wyoming.frame["lon"], wyoming.frame["lat"])
    assert density.max() == pytest.approx(1.0)

    dogs = load_csv(str(root / "dog_breeds.csv"))
    assert dogs.skipped == []
    assert dogs.name_labels == ["Species", "Breed"]
    assert len(dogs) >= 80
    density, _ = compute_heatmap(dogs.frame["lon"], dogs.frame["lat"],
                                 radius=15, intensity=1.5)
    assert density.max() == pytest.approx(1.0)
