"""The inset map: its options, the region it shows, and how it is drawn.

The region and box rules are plain functions and run anywhere; drawing the
inset needs the Natural Earth data, so those tests skip without it.
"""

from __future__ import annotations

import json
import tkinter as tk

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import PathCollection
from matplotlib.figure import Figure

from pymappr.geo.layers import CONTINENT_EXTENTS, LayerStore
from pymappr.geo.regions import around_extent, containing_extent, inset_extent
from pymappr.renderer import MapRenderer
from pymappr.styling.decorations import (InsetOptions, ScaleBarOptions,
                                         inset_box_target)
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import PointStyle

# Lancaster County, Nebraska, and the Great Smoky Mountains.
LANCASTER = (-97.3, -96.2, 40.5, 41.4)
SMOKIES = (-84.2, -82.9, 35.2, 36.0)
HAWAII = (-160.5, -154.5, 18.7, 22.4)


class _MouseEvent:
    def __init__(self, ax, x, y, button=1):
        self.inaxes = ax
        self.x, self.y = x, y
        self.button = button
        self.xdata = self.ydata = 0.0


@pytest.fixture(scope="module")
def store():
    store = LayerStore()
    if store.check_data():
        pytest.skip("map data not downloaded")
    return store


def _renderer(store, extent=LANCASTER, **inset) -> MapRenderer:
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, store)
    r.set_layer("countries", True)
    r.set_extent(extent)
    if inset:
        r.set_inset(InsetOptions(show=True, **inset))
    return r


# ---------------------------------------------------------------- options

def test_options_round_trip_through_a_dict():
    inset = InsetOptions(show=True, position="upper left", size=0.4,
                         region="custom", lon_min=-10.0, lon_max=5.0,
                         lat_min=40.0, lat_max=50.0, projection="Globe",
                         counties=True, ocean="blue", box_color="#000000",
                         draggable=True, anchor_x=0.1, anchor_y=0.2)
    assert InsetOptions.from_dict(inset.to_dict()) == inset


def test_a_project_saved_before_insets_has_none():
    assert InsetOptions.from_dict(None) == InsetOptions()
    assert not InsetOptions.from_dict({}).show


def test_a_custom_extent_needs_all_four_sides_in_order():
    assert InsetOptions(region="custom").custom_extent is None
    assert InsetOptions(lon_min=5.0, lon_max=-5.0, lat_min=0.0,
                        lat_max=1.0).custom_extent is None
    assert InsetOptions(lon_min=-5.0, lon_max=5.0, lat_min=0.0,
                        lat_max=1.0).custom_extent == (-5.0, 5.0, 0.0, 1.0)


def test_only_view_dependent_regions_follow_the_map():
    assert InsetOptions(region="state").follows_view()
    assert InsetOptions(region="around").follows_view()
    assert not InsetOptions(region="World").follows_view()
    assert InsetOptions(region="World", projection="Globe").follows_view()


# ----------------------------------------------------------- region rules

def test_a_wider_inset_marks_the_view_on_itself():
    assert inset_box_target((-105, -95, 40, 43), LANCASTER) == "inset"


def test_a_smaller_inset_is_marked_on_the_map():
    assert inset_box_target(HAWAII, CONTINENT_EXTENTS["World"]) == "main"


def test_unrelated_or_equal_areas_get_no_box():
    assert inset_box_target(HAWAII, LANCASTER) is None
    assert inset_box_target(LANCASTER, LANCASTER) is None


def test_around_grows_the_view_and_stays_on_the_globe():
    lon0, lon1, lat0, lat1 = around_extent((-10, 10, 0, 10), 4)
    assert (lon1 - lon0, lat1 - lat0) == (80, 40)
    assert around_extent((170, 179, 80, 89), 10)[1] == 180.0
    assert around_extent((170, 179, 80, 89), 10)[3] == 90.0


def test_fixed_regions_need_no_layer_data():
    view, centre = LANCASTER, (-96.7, 41.0)
    assert inset_extent(None, InsetOptions(region="Europe"), view,
                        centre) == CONTINENT_EXTENTS["Europe"]
    custom = InsetOptions(region="custom", lon_min=1.0, lon_max=2.0,
                          lat_min=3.0, lat_max=4.0)
    assert inset_extent(None, custom, view, centre) == (1.0, 2.0, 3.0, 4.0)
    # Half-typed: the whole world until the box is complete.
    assert inset_extent(None, InsetOptions(region="custom"), view,
                        centre) == CONTINENT_EXTENTS["World"]


def test_the_state_holding_the_map_is_found(store):
    lon0, lon1, lat0, lat1 = containing_extent(store, "states", -96.7, 40.9)
    # Nebraska, with a little room around it.
    assert -106 < lon0 < -104 and -95 < lon1 < -94
    assert 39 < lat0 < 40 and 43 < lat1 < 44


def test_a_country_inset_keeps_to_the_part_holding_the_map(store):
    lon0, lon1, lat0, lat1 = containing_extent(store, "countries", -83.5, 35.6)
    # The contiguous United States: no Alaska, Hawaii or Aleutians.
    assert -132 < lon0 < -124 and -68 < lon1 < -60
    assert lat1 < 53


def test_open_sea_falls_back_to_the_area_around_the_view(store):
    view = (-40.0, -30.0, -10.0, 0.0)
    options = InsetOptions(region="state", zoom_out=3)
    assert inset_extent(store, options, view, (-35.0, -5.0)) == around_extent(
        view, 3)


# ---------------------------------------------------------------- drawing

def test_no_inset_until_it_is_switched_on(store):
    r = _renderer(store)
    assert r._inset_ax is None and not r.ax.child_axes
    r.set_inset(InsetOptions(show=True))
    assert r.ax.child_axes == [r._inset_ax]
    r.set_inset(InsetOptions(show=False))
    assert r._inset_ax is None and not r.ax.child_axes


def test_the_inset_sits_in_its_corner_inside_the_map(store):
    for corner in ("lower left", "lower right", "upper left", "upper right"):
        r = _renderer(store, position=corner)
        x, y, w, h = r._inset_rect
        assert 0 <= x and x + w <= 1 and 0 <= y and y + h <= 1
        assert (x > 0.5) == corner.endswith("right")
        assert (y > 0.3) == corner.startswith("upper")


def test_a_state_locator_marks_the_view_on_the_inset(store):
    r = _renderer(store, region="state", states=True, counties=True)
    target, xs, ys = r.inset_box_xy()
    assert target == "inset"
    assert r._inset_box_artists and not r._inset_main_artists
    # The box is the view, inside Nebraska.
    assert np.nanmin(xs) == pytest.approx(r.ax.get_xlim()[0], abs=1e-6)
    x0, x1, y0, y1 = r._inset_limits
    assert x0 < np.nanmin(xs) < np.nanmax(xs) < x1
    assert y0 < np.nanmin(ys) < np.nanmax(ys) < y1


def test_a_zoomed_inset_is_boxed_on_the_world_map(store):
    lon0, lon1, lat0, lat1 = HAWAII
    r = _renderer(store, extent="World", region="custom", lon_min=lon0,
                  lon_max=lon1, lat_min=lat0, lat_max=lat1)
    assert r.inset_box_xy()[0] == "main"
    assert r._inset_main_artists and not r._inset_box_artists
    assert r._inset_main_artists[0].axes is r.ax


def test_a_pan_moves_the_box_without_rebuilding_the_inset(store):
    r = _renderer(store, region="state")
    inset = r._inset_ax
    before = r.inset_box_xy()[1].copy()
    x0, x1 = r.ax.get_xlim()
    r.ax.set_xlim(x0 + 0.1, x1 + 0.1)
    assert r._inset_ax is inset
    assert r.inset_box_xy()[1] == pytest.approx(before + 0.1)


def test_the_inset_survives_a_projection_change(store):
    r = _renderer(store, region="country")
    r.set_projection("Lambert: N. America")
    assert r._inset_ax is not None
    assert r._inset_proj is r.proj      # the region fits the projection
    r.set_projection("Robinson")
    assert r._inset_proj.name == "Robinson"


def test_a_globe_inset_is_a_disk_centred_on_the_map(store):
    r = _renderer(store, extent=(41, 53, -27, -11), projection="Globe")
    assert r._inset_proj.hemisphere
    assert r._inset_proj.lon_0 == pytest.approx(47, abs=1)
    assert not any(s.get_visible() for s in r._inset_ax.spines.values())
    x, y, w, h = r._inset_rect
    # Square on the page: the map box is wider than tall.
    assert w * r._map_box_aspect() == pytest.approx(h, rel=1e-3)
    assert r.inset_box_xy()[0] == "inset"


def test_points_are_drawn_on_the_inset_too(store):
    r = _renderer(store, region="state")
    style = PointStyle(color="#ff0000", marker="o", size=30)
    r.set_point_groups([("A", style, [-96.7, -96.5], [40.8, 41.0])])
    points = [c for c in r._inset_ax.collections
              if isinstance(c, PathCollection)]
    assert any(len(c.get_offsets()) == 2 for c in points)
    r.set_inset(InsetOptions(show=True, region="state", points=False))
    assert not any(isinstance(c, PathCollection) and len(c.get_offsets()) == 2
                   for c in r._inset_ax.collections)


def test_the_inset_steps_above_a_scale_bar_in_its_corner(store):
    r = _renderer(store)
    r.set_scale_bar(ScaleBarOptions(show=True, position="lower right"))
    r.set_inset(InsetOptions(show=True, position="lower right"))
    _corner, frac, _points = r._scale_bar_clear
    assert r._inset_rect[1] > frac


def test_a_legend_in_the_insets_corner_sits_beyond_it(store):
    r = _renderer(store, position="upper left")
    r.set_legend(LegendOptions(location="upper left"))
    placement = r._legend_placement()
    x, y, w, h = r._inset_rect
    assert placement["bbox_to_anchor"][1] < y


def test_dragging_moves_the_inset_and_a_right_click_resets_it(store):
    r = _renderer(store, draggable=True)
    r.fig.canvas.draw()
    bbox = r._inset_ax.bbox
    cx, cy = (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2
    start = r._inset_rect
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx - 200, cy + 100))
    r._on_canvas_release(_MouseEvent(r.ax, cx - 200, cy + 100))
    assert r.inset_anchor() is not None
    assert r._inset_rect[0] < start[0] and r._inset_rect[1] > start[1]
    r.fig.canvas.draw()
    bbox = r._inset_ax.bbox
    r._on_canvas_press(_MouseEvent(r.ax, (bbox.x0 + bbox.x1) / 2,
                                   (bbox.y0 + bbox.y1) / 2, button=3))
    assert r.inset_anchor() is None
    assert r._inset_rect == pytest.approx(start)


def test_an_inset_that_cannot_be_dragged_lets_the_press_through(store):
    r = _renderer(store, region="state")
    r.fig.canvas.draw()
    bbox = r._inset_ax.bbox
    assert not r._inset_press(_MouseEvent(r.ax, bbox.x0 + 5, bbox.y0 + 5))


def test_the_inset_is_in_a_saved_portrait_map(store, tmp_path):
    r = _renderer(store, region="state")
    r.set_orientation("portrait")
    size = tuple(r.fig.get_size_inches())
    path = tmp_path / "map.png"
    r.save_image(str(path), fmt="png", dpi=60, width_cm=8)
    assert path.stat().st_size > 0
    assert tuple(r.fig.get_size_inches()) == size
    assert r._inset_ax is not None


def test_the_export_description_is_plain_json(store):
    r = _renderer(store, region="state", states=True)
    data = r.inset_export()
    json.dumps(data)
    assert data["box"]["target"] == "inset"
    assert [layer[0] for layer in data["layers"]] == ["land", "states",
                                                      "countries"]
    assert _renderer(store).inset_export() is None


# ------------------------------------------------------------------ panel

class _FakeApp:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


@pytest.fixture(scope="module")
def panel():
    try:
        root = tk.Tk()
    except tk.TclError as exc:                      # pragma: no cover
        pytest.skip(f"no Tk display: {exc}")
    root.withdraw()
    from pymappr.ui.control_panel import ControlPanel

    widget = ControlPanel(root, _FakeApp())
    yield widget
    root.destroy()


def test_panel_defaults_match_the_dataclass(panel):
    panel.set_inset_options(InsetOptions())
    assert panel.inset_options() == InsetOptions()


def test_every_inset_option_round_trips_through_the_widgets(panel):
    custom = InsetOptions(
        show=True, position="upper left", size=0.45, region="custom",
        zoom_out=10.0, lon_min=-160.5, lon_max=-154.5, lat_min=18.7,
        lat_max=22.4, projection="Robinson", countries=False, states=True,
        counties=True, land=False, ocean="blue", points=False, box=False,
        box_color="#123456", draggable=True)
    panel.set_inset_options(custom)
    assert panel.inset_options() == custom
    assert panel.inset_options((0.1, 0.2)).anchor == (0.1, 0.2)


def test_extent_boxes_are_live_only_for_a_custom_region(panel):
    panel.set_inset_options(InsetOptions(region="state"))
    assert str(panel.inset_extent_spins[0].cget("state")) == "disabled"
    panel.set_inset_options(InsetOptions(region="custom"))
    assert str(panel.inset_extent_spins[0].cget("state")) == "normal"
