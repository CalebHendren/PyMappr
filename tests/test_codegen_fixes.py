"""Code export: the 1.31.3 fixes for label values, dataset styles and the
R legend and points."""

import pytest

from pymappr.export import codegen
from pymappr.files.data_loader import build_manual_dataset
from pymappr.files.projects import DatasetEntry
from pymappr.geo.projections import get_projection
from pymappr.styling.legend import row_key

from codegen_helpers import (make_state, manual_entry, exec_python,
                             run_r_harness, cities_entry, coded_entry,
                             ungrouped_entry, app_labels)


# ------------------------------------------------- export fixes (1.31.3)

@pytest.mark.parametrize("data_mode", ["inline", "files"])
def test_python_reads_label_values_as_text(tmp_path, data_mode):
    entry = coded_entry()
    if data_mode == "files":
        files = codegen.generate_working_directory(make_state(), [entry],
                                                   "Python", "P")
        for rel, text in files.items():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text(text, encoding="utf-8")
        code = files["recreate_map.py"]
    else:
        code = codegen.generate_code(make_state(), [entry], "Python")
    ns = exec_python(code)
    ns["SCRIPT_DIR"] = tmp_path
    spec = ns["DATASETS"][0]
    labels = list(ns["point_labels"](ns["load_points"](spec), spec))
    # "NA" is not missing, "007" keeps its zeros, "1.50" its trailing zero.
    assert labels == ["NA", "007", "T", "1.50", "(blank)"]
    assert labels == app_labels([entry])[0]
    assert list(spec["styles"]) == labels


@pytest.mark.parametrize("data_mode", ["inline", "files"])
def test_r_reads_label_values_as_text(tmp_path, data_mode):
    entry = coded_entry()
    if data_mode == "files":
        files = codegen.generate_working_directory(make_state(), [entry],
                                                   "R", "P")
        for rel, text in files.items():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text(text, encoding="utf-8")
        code = files["recreate_map.R"]
    else:
        code = codegen.generate_code(make_state(), [entry], "R")
    run_r_harness(tmp_path, code, """
spec <- DATASETS[[1]]
labels <- point_labels(load_points(spec), spec)
stopifnot(identical(labels, c("NA", "007", "T", "1.50", "(blank)")))
stopifnot(identical(names(STYLE_COLORS), labels))
points <- load_all_points()
stopifnot(identical(points$key, labels))
""")


def test_two_datasets_sharing_a_label_keep_their_own_styles(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    # Two ungrouped datasets with the same name both display as "Sites";
    # the app draws each in its own colour with a legend row each.
    entries = [ungrouped_entry("Sites", "#111111"),
               ungrouped_entry("Sites", "#222222")]
    assert app_labels(entries) == [["Sites"], ["Sites"]]
    ns = exec_python(codegen.generate_code(make_state(), entries, "Python"))
    # Styles are keyed by group value; label_map shows each as "Sites".
    colors = [spec["styles"]["All points"]["color"]
              for spec in ns["DATASETS"]]
    assert [spec["label_map"] for spec in ns["DATASETS"]] == [
        {"All points": "Sites"}] * 2
    assert colors == ["#111111", "#222222"]
    fig = matplotlib.figure.Figure()
    ax = fig.add_subplot(111)
    ns["add_legend"](ax)
    legend = ax.get_legend()
    assert [t.get_text() for t in legend.get_texts()] == ["Sites", "Sites"]
    assert [h.get_markerfacecolor() for h in legend.legend_handles] == colors

    code = codegen.generate_code(make_state(), entries, "R")
    run_r_harness(tmp_path, code, """
stopifnot(identical(names(STYLE_FILLS), c("Sites", "Sites [2]")))
stopifnot(identical(unname(STYLE_FILLS), c("#111111", "#222222")))
points <- load_all_points()
stopifnot(identical(points$key, c("Sites", "Sites", "Sites [2]",
                                  "Sites [2]")))
guide <- get_guide_data(ggplot() + point_layers(), "fill")
stopifnot(identical(guide$.label, c("Sites", "Sites")))
stopifnot(identical(guide$fill, c("#111111", "#222222")))
""")


def test_attribute_datasets_with_overlapping_values_keep_their_styles():
    # Symbol-by labels get no per-dataset dedupe: both datasets draw
    # "Site A", each with its own override.
    a = manual_entry("One", symbol_by="Label", group_by="")
    b = manual_entry("Two", symbol_by="Label", group_by="")
    a.legend_overrides = {row_key("symbol", "Site A"): {"marker": "Square"}}
    b.legend_overrides = {row_key("symbol", "Site A"): {"marker": "Diamond"}}
    ns = exec_python(codegen.generate_code(make_state(), [a, b], "Python"))
    markers = [spec["styles"]["Site A"]["marker"] for spec in ns["DATASETS"]]
    assert markers == ["s", "D"]
    r_code = codegen.generate_code(make_state(), [a, b], "R")
    shapes = r_code.split("STYLE_SHAPES <- c(")[1].split(")")[0]
    assert '"Site A" = 22' in shapes and '"Site A [2]" = 23' in shapes


def test_r_legend_follows_row_order_and_hides_rows(tmp_path):
    entry = coded_entry(labels=["Zeta", "Beta", "Alpha"], column="Name")
    entry.legend_overrides = {row_key("group", "Zeta"): {"hidden": True}}
    state = make_state(legend={"order": "az", "title": ""})
    code = codegen.generate_code(state, [entry], "R")
    run_r_harness(tmp_path, code, """
stopifnot(identical(LEGEND_ROWS, c("Alpha", "Beta")))
p <- ggplot() + point_layers()
guide <- get_guide_data(p, "colour")
stopifnot(identical(guide$.label, c("Alpha", "Beta")))
# Hiding a row keeps its points.
stopifnot(nrow(layer_data(p, 1)) == 3)
""")
    # Every row hidden is not "no ordering": the legend is empty.
    entry.legend_overrides = {row_key("group", label): {"hidden": True}
                              for label in ("Zeta", "Beta", "Alpha")}
    code = codegen.generate_code(state, [entry], "R")
    assert "LEGEND_ROWS <- character(0)" in code
    run_r_harness(tmp_path, code, """
p <- ggplot() + point_layers()
stopifnot(is.null(get_guide_data(p, "colour")))
stopifnot(nrow(layer_data(p, 1)) == 3)
""")


R_LEGEND_SWATCHES = """
legend_swatches <- function(p) {
  # Point glyphs drawn in the legend box.
  g <- ggplotGrob(p)
  flat <- function(x) {
    if (inherits(x, "gtable")) {
      return(unlist(lapply(x$grobs, flat), recursive = FALSE))
    }
    if (inherits(x, "gTree")) {
      return(unlist(lapply(x$children, flat), recursive = FALSE))
    }
    list(x)
  }
  box <- g$grobs[grepl("guide-box", g$layout$name)]
  grobs <- unlist(lapply(box, flat), recursive = FALSE)
  sum(vapply(grobs, inherits, logical(1), "points"))
}
"""


def test_r_keeps_legend_rows_whose_points_are_off_the_map(tmp_path):
    # Cape Town is on the far side of this globe: its row stays, with its
    # swatch, as in the app - and building the legend must not crash.
    state = make_state(map={"projection": "Globe (Orthographic)",
                            "proj_lon0": "-100", "proj_lat0": "40"})
    code = codegen.generate_code(state, [cities_entry()], "R")
    run_r_harness(tmp_path, code, R_LEGEND_SWATCHES + """
points <- project_points(load_all_points())
stopifnot(identical(unique(points$key), "Paris"))
p <- ggplot() + point_layers()
guide <- get_guide_data(p, "colour")
stopifnot(identical(guide$.label, c("Paris", "Cape Town")))
stopifnot(legend_swatches(p) == 2)
""")


def test_r_points_are_clamped_into_the_band_like_the_app(tmp_path):
    # Lambert: Europe stops at 30N; Cape Town sits on that edge in the app
    # (Projection._clip) rather than vanishing.
    state = make_state(map={"projection": "Lambert: Europe"})
    code = codegen.generate_code(state, [cities_entry()], "R")
    projection = get_projection("Lambert: Europe")
    x, y = projection.forward([18.42], [-33.92])
    run_r_harness(tmp_path, code, f"""
points <- project_points(load_all_points())
stopifnot(nrow(points) == 3)
xy <- sf::st_coordinates(points)[points$key == "Cape Town", ]
stopifnot(abs(xy[["X"]] - ({float(x[0])})) < 1)
stopifnot(abs(xy[["Y"]] - ({float(y[0])})) < 1)
""")


def test_r_points_wrap_round_the_centre_like_the_app(tmp_path):
    # Lambert: N. America keeps 186W..6W: a point at 175E is 185W, beside
    # Alaska, not clamped onto the eastern edge.
    aleutians = DatasetEntry(dataset=build_manual_dataset(
        "islands", "52.0,175.0, Attu\n"), name="islands", group_by="Label")
    state = make_state(map={"projection": "Lambert: N. America"})
    code = codegen.generate_code(state, [aleutians], "R")
    x, y = get_projection("Lambert: N. America").forward([175.0], [52.0])
    run_r_harness(tmp_path, code, f"""
points <- project_points(load_all_points())
xy <- sf::st_coordinates(points)
stopifnot(xy[1, "X"] < 0)
stopifnot(abs(xy[1, "X"] - ({float(x[0])})) < 1)
stopifnot(abs(xy[1, "Y"] - ({float(y[0])})) < 1)
""")


def test_r_drops_natural_earth_points_outside_the_region(tmp_path):
    # Cape Town clamps onto Lambert: Europe's edge as a user point, but a
    # Natural Earth marker there is dropped, as in the app.
    state = make_state(map={"projection": "Lambert: Europe"})
    code = codegen.generate_code(state, [cities_entry()], "R")
    assert 'project_points(data, clamp = FALSE)' in code
    run_r_harness(tmp_path, code, """
points <- project_points(load_all_points(), clamp = FALSE)
stopifnot(nrow(points) == 2)
stopifnot(!("Cape Town" %in% points$key))
""")


def test_r_draws_wrapped_world_copies(tmp_path):
    # Equirectangular from 100E to 260E: the right half is the next world
    # copy, where Hawaii sits at 203E.
    hawaii = DatasetEntry(dataset=build_manual_dataset(
        "islands", "19.9,-155.6, Hawaii\n"), name="islands",
        group_by="Label")
    state = make_state(map={"projection": "Equirectangular"},
                       view={"xlim": [100, 260], "ylim": [-40, 60]})
    code = codegen.generate_code(state, [hawaii], "R")
    run_r_harness(tmp_path, code, """
stopifnot(identical(wrap_offsets(), c(0, 360)))
points <- wrapped(project_points(load_all_points()))
x <- sf::st_coordinates(points)[, "X"]
stopifnot(isTRUE(all.equal(sort(x), c(-155.6, 204.4))))
""")
    # The globe never wraps.
    globe = codegen.generate_code(
        make_state(map={"projection": "Globe (Orthographic)"}), [hawaii], "R")
    run_r_harness(tmp_path, globe, "stopifnot(identical(wrap_offsets(), 0))")


def test_r_grid_is_drawn_above_the_fills_and_under_the_points(tmp_path):
    state = make_state(map={"projection": "Globe (Orthographic)",
                            "points": {"cities": True}})
    code = codegen.generate_code(state, [manual_entry()], "R")
    run_r_harness(tmp_path, code, """
# Stand-ins that record the draw order instead of loading Natural Earth.
base_layer_geom <- function(layer) {
  annotate("text", x = 0, y = 0, label = layer$name)
}
order <- function(p) {
  vapply(p$layers, function(l) {
    if (!is.null(l$aes_params$label)) l$aes_params$label
    else class(l$geom)[1]
  }, character(1))
}
p <- build_map()
drawn <- order(p)
grid_at <- which(drawn == "GeomSf")[1:2]  # graticule, then horizon
fills <- match(c("ocean", "land", "lakes"), drawn)
cities <- match("populated_places_simple", drawn)
stopifnot(all(fills < grid_at[1]), grid_at[2] < cities)
# The globe always gets its horizon circle, grid or not.
GRID_INTERVAL <- NULL
stopifnot(length(graticule_layers()) == 1)
""")


def test_r_legend_placement_frame_and_text_options(tmp_path):
    legend = {"location": "lower left", "frame": True,
              "frame_color": "#000000", "frame_alpha": 1.0,
              "frame_edge_color": "#ff0000", "frame_width": 2.13,
              "label_color": "#00ff00", "title_color": "#0000ff",
              "font_family": "serif", "fontsize": 9, "title": "Sites"}
    code = codegen.generate_code(make_state(legend=legend, view={}),
                                 [manual_entry()], "R")
    assert "Legend border width" not in code  # it is reproduced now
    run_r_harness(tmp_path, code, """
NE_LAYERS <- list()
p <- build_map()
th <- p$theme
stopifnot(identical(th$legend.position, "inside"))
stopifnot(identical(th$legend.justification.inside, c(0, 0)))
stopifnot(all(th$legend.position.inside > 0),
          all(th$legend.position.inside < 0.05))
stopifnot(identical(th$legend.background$colour, "#ff0000"))
stopifnot(identical(toupper(th$legend.background$fill), "#000000FF"))
stopifnot(abs(th$legend.background$linewidth - 1) < 0.01)
stopifnot(identical(th$legend.text$colour, "#00ff00"))
stopifnot(identical(th$legend.title$colour, "#0000ff"))
stopifnot(identical(th$legend.text$family, "serif"))
stopifnot(identical(legend_anchor("upper right"), c(1, 1)))
stopifnot(identical(legend_anchor("best"), c(1, 1)))
stopifnot(identical(legend_anchor("center left"), c(0, 0.5)))
stopifnot(identical(legend_anchor("right"), c(1, 0.5)))
stopifnot(identical(legend_anchor("lower center"), c(0.5, 0)))
invisible(ggplotGrob(p))
""")


def test_r_header_names_the_marker_approximations():
    entry = manual_entry()  # its one group is a Star
    code = codegen.generate_code(make_state(), [entry], "R")
    notes = code.split("NOT reproduced")[1].split("ensure_packages")[0]
    assert "stars are drawn as asterisks (R pch 8)" in notes
    plain = codegen.generate_code(
        make_state(), [manual_entry(legend_overrides={})], "R")
    assert "R has no exact equivalent" not in plain


def test_r_point_outlines_are_converted_from_points(tmp_path):
    entry = coded_entry(labels=["Filled", "Open"], column="Name")
    entry.legend_overrides = {
        row_key("group", "Open"): {"marker": "Circle (open)"}}
    state = make_state(point_edge={"color": "#333333", "width": 0.5})
    code = codegen.generate_code(state, [entry], "R")
    run_r_harness(tmp_path, code, """
stopifnot(identical(unname(STYLE_STROKES), c(0.5, 1.2)))
strokes <- layer_data(ggplot() + point_layers(), 1)$stroke
# ggplot2 strokes are not points: 0.5 pt is about 0.35 stroke units.
stopifnot(isTRUE(all.equal(strokes, c(0.5, 1.2) * 50.8 / 72)))
""")
