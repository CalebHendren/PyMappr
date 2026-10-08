"""Renderer tests: the legend - dragging it, its text styles, nested rows and
the options that reach it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styling.decorations import ScaleBarOptions  # noqa: E402
from pymappr.styling.legend import LegendOptions  # noqa: E402
from pymappr.styling.styles import PointStyle  # noqa: E402
from renderer_helpers import _renderer, _MouseEvent  # noqa: E402


# ------------------------------------------------------------- legend dragging


def _legend_renderer() -> MapRenderer:
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("A", PointStyle(color="#d62728"),
                         np.array([-60.0]), np.array([-15.0]))])
    r.set_legend(LegendOptions(location="upper right"))
    r.fig.canvas.draw()
    return r


def _legend_center_px(r: MapRenderer):
    bbox = r.ax.get_legend().get_window_extent()
    return (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2


def test_legend_drag_moves_and_anchors_without_a_jump():
    r = _legend_renderer()
    r.set_legend_dragging(True)
    before = r._legend_lowerleft_axes(r.ax.get_legend())
    cx, cy = _legend_center_px(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    # Grabbing an auto-placed legend pins it in place (no hop on press).
    assert r._legend_anchor is not None
    pinned = r._legend_lowerleft_axes(r.ax.get_legend())
    assert pinned == pytest.approx(before, abs=1e-3)
    # Dragging down-left moves the legend and stores the new anchor.
    r._on_canvas_motion(_MouseEvent(r.ax, cx - 120, cy - 120))
    r._on_canvas_release(_MouseEvent(r.ax, cx - 120, cy - 120))
    assert r._legend_drag is None
    after = r._legend_lowerleft_axes(r.ax.get_legend())
    assert after[0] < before[0]
    assert after[1] < before[1]


def test_legend_drag_ignored_when_disabled():
    r = _legend_renderer()
    r.set_legend_dragging(False)
    cx, cy = _legend_center_px(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    assert r._legend_drag is None
    assert r._legend_anchor is None


def test_legend_right_click_and_clear_reset_anchor():
    r = _legend_renderer()
    r.set_legend_dragging(True)
    cx, cy = _legend_center_px(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx - 40, cy - 40))
    r._on_canvas_release(_MouseEvent(r.ax, cx - 40, cy - 40))
    assert r._legend_anchor is not None
    # A right-click on the (now moved) legend restores automatic placement.
    ncx, ncy = _legend_center_px(r)
    r._on_canvas_press(_MouseEvent(r.ax, ncx, ncy, button=3))
    assert r._legend_anchor is None
    # Re-drag, then clearing (e.g. picking a preset position) also resets it.
    r._on_canvas_press(_MouseEvent(r.ax, *_legend_center_px(r)))
    r._on_canvas_motion(_MouseEvent(r.ax, cx - 30, cy - 30))
    r._on_canvas_release(_MouseEvent(r.ax, cx - 30, cy - 30))
    assert r._legend_anchor is not None
    r.clear_legend_anchor()
    assert r._legend_anchor is None


# ------------------------------------------------------- legend text formatting


def test_legend_text_formatting_applies_and_collects_underlines():
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("Alpha", PointStyle(color="#d62728"),
                         np.array([-60.0]), np.array([-15.0]))])
    r.set_legend(LegendOptions(
        title="Sites", label_bold=True, label_italic=True,
        label_underline=True, title_bold=True, title_italic=False,
        title_underline=True))
    leg = r.ax.get_legend()
    text = leg.get_texts()[0]
    assert text.get_fontweight() == "bold"
    assert text.get_fontstyle() == "italic"
    title = leg.get_title()
    assert title.get_fontweight() == "bold"
    assert title.get_fontstyle() == "normal"
    # The label and the title are both flagged for underlining.
    assert set(r._legend_underline_texts) == {text, title}


def test_legend_underlines_cleared_when_hidden():
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("Alpha", PointStyle(color="#d62728"),
                         np.array([-60.0]), np.array([-15.0]))])
    r.set_legend(LegendOptions(label_underline=True))
    assert r._legend_underline_texts
    # Legend hidden: nothing left to draw an underline under.
    r.set_legend(LegendOptions(show=False, label_underline=True))
    assert r._legend_underline_texts == []


# ---------------------------------------------------------- nested legend


def _beetle_sections(**kwargs):
    import pandas as pd

    from pymappr.styling.legend import legend_counts, legend_sections
    from pymappr.styling.styles import attribute_style_maps
    path = (Path(__file__).resolve().parent.parent / "sample_data"
            / "south_america_beetles.csv")
    frame = pd.read_csv(path).rename(columns={"Genus": "name1",
                                              "Species": "name2"})
    cmap, smap = attribute_style_maps(frame, "name1", "name2")
    counts = (legend_counts(frame, "name1", "name2")
              if kwargs.pop("counts", False) else None)
    return frame, legend_sections(frame, "name1", "name2", cmap, smap,
                                  "Genus", "Species", counts=counts,
                                  **kwargs)


def _legend_rows(renderer):
    legend = renderer.ax.get_legend()
    return [(t.get_text(), t.get_fontweight()) for t in legend.get_texts()]


def test_nested_legend_indents_species_under_their_genus():
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right"))
    rows = _legend_rows(r)
    texts = [text for text, _weight in rows]
    assert "   Eleusis" in texts          # genus: one indent
    assert "      chapadensis" in texts   # species: two


def test_nested_legend_bolds_the_genus_rows_only():
    # Every swatch sits in the same column, so indentation alone reads too
    # weakly - the group rows take the header weight as well.
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right", title_bold=True,
                               label_bold=False))
    weights = dict(_legend_rows(r))
    assert weights["   Eleusis"] == "bold"
    assert weights["      chapadensis"] == "normal"


def test_crossed_legend_keeps_every_row_at_one_indent():
    import pandas as pd

    from pymappr.styling.legend import legend_sections
    from pymappr.styling.styles import attribute_style_maps
    frame = pd.DataFrame({
        "name1": ["forest", "forest", "scrub", "scrub"],
        "name2": ["male", "female", "male", "female"],
        "lon": [1.0, 2.0, 3.0, 4.0], "lat": [1.0, 2.0, 3.0, 4.0],
    })
    cmap, smap = attribute_style_maps(frame, "name1", "name2")
    sections = legend_sections(frame, "name1", "name2", cmap, smap,
                               "Habitat", "Sex")
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right", title_bold=True,
                               label_bold=False))
    rows = _legend_rows(r)
    entries = [(text, weight) for text, weight in rows if text.strip()
               and text not in ("Habitat", "Sex")]
    assert all(text.startswith("   ") and not text.startswith("      ")
               for text, _w in entries)
    # Only the two section titles are bold here, never the value rows.
    assert all(weight == "normal" for _t, weight in entries)


def test_legacy_two_tuple_entries_still_draw():
    # Plain-mode sections are (label, style) pairs; they must keep working
    # alongside the (label, style, depth) rows a nested key emits.
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend([("Dataset", [("Site A", PointStyle())])])
    r.set_legend(LegendOptions(location="upper right"))
    assert "   Site A" in [text for text, _w in _legend_rows(r)]


# ------------------------------------------------- legend option plumbing


def _legend_of(renderer):
    return renderer.ax.get_legend()


def test_default_options_reproduce_the_previous_legend_exactly():
    # The settings below were hard-coded before they became options. If a
    # default drifts, every existing project's legend silently changes, so
    # pin them here rather than trusting the dataclass.
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right"))
    leg = _legend_of(r)
    assert leg.get_frame().get_alpha() == pytest.approx(0.85)
    assert leg.get_frame().get_linewidth() == pytest.approx(0.8)
    # Three-space indent per level, group rows bold, blank spacer rows.
    texts = [t.get_text() for t in leg.get_texts()]
    assert "   Eleusis" in texts
    assert "      chapadensis" in texts
    assert " " in texts                       # the spacer between groups
    weights = {t.get_text(): t.get_fontweight() for t in leg.get_texts()}
    assert weights["   Eleusis"] == "bold"
    assert weights["      chapadensis"] == "normal"


def test_indent_width_is_configurable():
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right", indent=1))
    texts = [t.get_text() for t in _legend_of(r).get_texts()]
    assert " Eleusis" in texts
    assert "  chapadensis" in texts

    r.set_legend(LegendOptions(location="upper right", indent=0))
    texts = [t.get_text() for t in _legend_of(r).get_texts()]
    assert "Eleusis" in texts
    assert "chapadensis" in texts


def test_group_rows_can_lose_their_bold_and_their_spacer():
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right", bold_groups=False,
                               group_spacer=False))
    leg = _legend_of(r)
    weights = {t.get_text(): t.get_fontweight() for t in leg.get_texts()}
    assert weights["   Eleusis"] == "normal"
    # Only the section title row is left; no blank rows between groups.
    assert [t.get_text() for t in leg.get_texts()].count(" ") == 0


def test_section_titles_off_removes_the_title_row():
    _frame, sections = _beetle_sections(
        options=LegendOptions(section_titles=False))
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right"))
    texts = [t.get_text() for t in _legend_of(r).get_texts()]
    assert "Genus / Species" not in texts
    assert "   Eleusis" in texts


def test_frame_and_text_colours_reach_the_artists():
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("Alpha", PointStyle(), np.array([0.0]),
                         np.array([0.0]))])
    r.set_legend(LegendOptions(
        title="Key", location="upper right", frame_color="#102030",
        frame_edge_color="#405060", frame_width=2.5, frame_alpha=0.5,
        label_color="#a0b0c0", title_color="#d0e0f0"))
    leg = _legend_of(r)
    frame = leg.get_frame()
    assert frame.get_facecolor()[:3] == pytest.approx(
        (0x10 / 255, 0x20 / 255, 0x30 / 255), abs=1e-3)
    assert frame.get_edgecolor()[:3] == pytest.approx(
        (0x40 / 255, 0x50 / 255, 0x60 / 255), abs=1e-3)
    assert frame.get_linewidth() == pytest.approx(2.5)
    assert frame.get_alpha() == pytest.approx(0.5)
    assert leg.get_texts()[0].get_color() == "#a0b0c0"
    assert leg.get_title().get_color() == "#d0e0f0"


def test_font_family_applies_to_labels_and_title():
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("Alpha", PointStyle(), np.array([0.0]),
                         np.array([0.0]))])
    r.set_legend(LegendOptions(title="Key", font_family="monospace"))
    leg = _legend_of(r)
    assert leg.get_texts()[0].get_fontfamily() == ["monospace"]
    assert leg.get_title().get_fontfamily() == ["monospace"]


def test_a_row_with_no_swatch_still_draws():
    # group_swatch="none" emits a None style; the handle must be blank
    # rather than crash or fall back to a circle.
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend([("Key", [("Headline", None, 0),
                                      ("Child", PointStyle(), 1)])])
    r.set_legend(LegendOptions(location="upper right"))
    texts = [t.get_text() for t in _legend_of(r).get_texts()]
    assert "   Headline" in texts
    assert "      Child" in texts


def test_plain_legend_row_order_follows_the_app_and_not_draw_order():
    r = _renderer(9.0, 6.5)
    groups = [(name, PointStyle(), np.array([0.0]), np.array([0.0]))
              for name in ("Charlie", "Alpha", "Bravo")]
    r.set_point_groups(groups)
    r.set_legend(LegendOptions(location="upper right"))
    assert [t.get_text() for t in _legend_of(r).get_texts()] == [
        "Charlie", "Alpha", "Bravo"]

    r.set_legend_row_order(["Alpha", "Bravo", "Charlie"])
    assert [t.get_text() for t in _legend_of(r).get_texts()] == [
        "Alpha", "Bravo", "Charlie"]
    # Draw order is untouched: reordering the key must not restack points.
    assert [label for label, *_rest in r._point_groups] == [
        "Charlie", "Alpha", "Bravo"]


def test_legend_anchor_round_trips_for_saving():
    r = _renderer(9.0, 6.5)
    assert r.legend_anchor() is None
    r.set_legend_anchor((0.25, 0.75))
    assert r.legend_anchor() == (0.25, 0.75)
    r.set_legend_anchor(None)
    assert r.legend_anchor() is None


def test_point_outline_reaches_the_map_and_the_legend():
    from matplotlib.colors import to_hex

    r = _renderer(9.0, 6.5)
    white = PointStyle(color="#ffffff", marker="Square")
    hollow = PointStyle(color="#123456", marker="Circle (open)")
    r.set_point_groups([("white", white, [0.0], [0.0]),
                        ("open", hollow, [10.0], [10.0])])
    r.set_legend(LegendOptions(location="upper right"))
    # Unchanged by default: filled markers keep their white edge.
    assert to_hex(r._point_artists[0].get_edgecolors()[0]) == "#ffffff"

    r.set_point_edge("#000000", 0.8)
    filled, outlined = r._point_artists
    assert to_hex(filled.get_edgecolors()[0]) == "#000000"
    assert filled.get_linewidths()[0] == pytest.approx(0.8)
    # Open markers still outline in their own colour.
    assert to_hex(outlined.get_edgecolors()[0]) == "#123456"
    handle = _legend_of(r).legend_handles[0]
    assert handle.get_markeredgecolor() == "#000000"
    assert handle.get_markeredgewidth() == pytest.approx(0.8)


def test_a_legend_only_change_leaves_the_points_as_drawn():
    r = _renderer(9.0, 6.5)
    groups = [("a", PointStyle(), [0.0], [0.0]),
              ("b", PointStyle(color="#000000"), [5.0], [5.0])]
    r.set_points(groups, None, None, LegendOptions())
    drawn = list(r._point_artists)
    r.set_points(groups, None, ["b", "a"],
                 LegendOptions(location="upper left", counts=True))
    assert r._point_artists == drawn        # same scatter objects
    assert [t.get_text() for t in _legend_of(r).get_texts()] == ["b", "a"]
    moved = [("a", PointStyle(), [1.0], [0.0]), groups[1]]
    r.set_points(moved, None, None, LegendOptions())
    assert r._point_artists != drawn        # the points really changed


def _legend_and_bar_boxes(r):
    r.fig.canvas.draw()
    renderer = r.fig.canvas.get_renderer()
    legend = r.ax.get_legend().get_window_extent(renderer)
    bar = mtransforms_union([a.get_window_extent(renderer)
                             for a in r._artists["scale_bar"]])
    return legend, bar


def mtransforms_union(boxes):
    from matplotlib.transforms import Bbox
    return Bbox.union(boxes)


@pytest.mark.parametrize("corner", ["lower left", "upper right"])
def test_a_legend_in_the_scale_bars_corner_leaves_the_bar_visible(corner):
    r = _renderer(9.0, 6.5)
    r.set_extent((-100.0, -77.0, 6.0, 21.0))
    r.set_point_groups([(f"Taxon {i}", PointStyle(color="#000000"),
                         np.array([-90.0 + i]), np.array([15.0]))
                        for i in range(5)])
    r.set_legend(LegendOptions(location=corner))
    r.set_scale_bar(ScaleBarOptions(show=True, position=corner))
    legend, bar = _legend_and_bar_boxes(r)
    assert not legend.overlaps(bar)
    # Still clear when the map is saved at another size.
    r.fig.set_size_inches(17 / 2.54, 17 / 2.54 * 6.5 / 9.0)
    legend, bar = _legend_and_bar_boxes(r)
    assert not legend.overlaps(bar)


def test_a_legend_elsewhere_keeps_its_corner():
    r = _renderer(9.0, 6.5)
    r.set_extent((-100.0, -77.0, 6.0, 21.0))
    r.set_point_groups([("A", PointStyle(color="#000000"),
                         np.array([-90.0]), np.array([15.0]))])
    r.set_legend(LegendOptions(location="upper left"))
    r.set_scale_bar(ScaleBarOptions(show=True, position="lower left"))
    assert r._legend_placement() == {"loc": "upper left"}
