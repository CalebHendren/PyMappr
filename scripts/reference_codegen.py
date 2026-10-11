r"""Reference code exports from PyMappr itself, for mappr-codegen's tests.

Run with PyMappr's environment:

    C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/reference_codegen.py <PyMappr dir> <command> [args]

Commands:
    tables OUT.json      PyMappr's layer, style and projection tables, as
                         crates/mappr-codegen/src/tables.json
    cases OUT_DIR        every reference case under OUT_DIR/<case>/:
                         input.json ({state, projectName, figureSize}) and
                         PyMappr's outputs for it (see write_case)
    app-inset OUT.json   a state with an inset, run through PyMappr's app so
                         the renderer supplies inset_export and the figure
                         size; writes the {state, projectName, figureSize}
                         input that `cases` then picks up as "app-inset"

The scripts are long: everything after the configuration block is the
template, pasted verbatim. Only the two sample-project cases keep the full
script; the others keep the header and configuration (the part before the
template), and this harness checks that the rest is the template exactly.
"""

import copy
import json
import math
import sys
from pathlib import Path

PYMAPPR = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(PYMAPPR))
HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "src" / "lib" / "fixtures"


# ------------------------------------------------------------------ tables

def tables(out):
    from pymappr.export import layers_config
    from pymappr.geo.layers import (BATHYMETRY_STEPS, CONTINENT_EXTENTS,
                                    LAYER_SPECS)
    from pymappr.geo.projections import (CAP_CLIP_RADIUS, PROJECTIONS,
                                         get_projection)
    from pymappr.renderer import tables as t
    from pymappr.updates import GITHUB_REPO
    from pymappr import __version__

    def projection(name):
        p = get_projection(name)
        return {"crs": p.crs, "bounds": list(p.bounds), "max_lat": p.max_lat,
                "min_lat": p.min_lat, "lon_0": p.lon_0, "lat_0": p.lat_0,
                "lon_halfspan": p.lon_halfspan, "hemisphere": p.hemisphere}

    data = {
        "pymappr_version": __version__,
        "repo": GITHUB_REPO,
        "cap_clip_radius": CAP_CLIP_RADIUS,
        "line_layers": {k: list(v) for k, v in t.LINE_LAYERS.items()},
        "fill_colors": [[k[0], k[1], v] for k, v in t.FILL_COLORS.items()],
        "fill_layers": {k: list(v) for k, v in t.FILL_LAYERS.items()},
        "bathymetry_colors": [[k, v] for k, v in t.BATHYMETRY_COLORS.items()],
        "bathymetry_steps": [list(s) for s in BATHYMETRY_STEPS],
        "point_layers": {k: list(v) for k, v in t.POINT_LAYERS.items()},
        "label_styles": [[k, v[0], [[fk, fv] for fk, fv in v[1].items()],
                          v[2], v[3]] for k, v in t.LABEL_STYLES.items()],
        "z": {"bathymetry": t.Z_BATHYMETRY, "ocean": t.Z_OCEAN,
              "lake_fill": t.Z_LAKE_FILL, "point_layers": t.Z_POINT_LAYERS},
        "margins_with_ticks": list(t.MARGINS_WITH_TICKS),
        "margins_plain": list(t.MARGINS_PLAIN),
        "layer_specs": {k: {"directory": s.directory, "geometry": s.geometry,
                            "label_cap": s.label_cap,
                            "shapefile": s.shapefile,
                            "resolutions": [list(r) for r in s.resolutions],
                            "label_column": s.label_column}
                        for k, s in LAYER_SPECS.items()},
        "category": layers_config._CATEGORY,
        "derived_sources": {k: [v[0], list(v[1])]
                            for k, v in layers_config._DERIVED_SOURCES.items()},
        "external_fills": layers_config._EXTERNAL_FILLS,
        "continent_extents": {k: list(v)
                              for k, v in CONTINENT_EXTENTS.items()},
        # Projections at their default origin, with pyproj's bounds; a custom
        # origin is computed in Rust.
        "projections": {name: projection(name) for name in PROJECTIONS},
    }
    Path(out).write_text(json.dumps(data, indent=1), encoding="utf-8")


# ------------------------------------------------------------------- cases

def load_fixture(name):
    document = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return document["name"], document["state"]


def inset_export(kind):
    """The stand-ins PyMappr's own tests use for MapRenderer.inset_export()."""
    sys.path.insert(0, str(PYMAPPR / "tests"))
    import test_codegen_inset

    return test_codegen_inset.inset_export(kind)


def base_state():
    _name, state = load_fixture("beetles-standard.pymappr")
    return copy.deepcopy(state)


def dataset(name, labels, rows, **settings):
    keys = [f"name{i + 1}" for i in range(len(labels))]
    entry = {"name": name, "visible": True,
             "source_path": f"C:\\data\\{name}",
             "columns": keys + ["lon", "lat"], "name_labels": labels,
             "rows": rows, "group_by": labels[0] if labels else "",
             "color_by": "", "symbol_by": "", "vary_symbols": False,
             "open_by": "", "open_values": [], "styles": {},
             "legend_overrides": {}, "manual": None}
    entry.update(settings)
    return entry


SEP = "\x00"


def cases():
    """name -> (state, project name, figure size)."""
    out = {}

    name, state = load_fixture("beetles-standard.pymappr")
    out["beetles-standard"] = (state, name, (6.692913, 4.866))
    name, state = load_fixture("hornbills-orchids.pymappr")
    out["hornbills-orchids"] = (state, name, None)

    # Every decoration and a good share of the layers, on Robinson.
    state = base_state()
    m = state["map"]
    m.update(projection="Robinson", graticule="5\N{DEGREE SIGN}",
             compass=True, ocean="blue", lake_fill="grey", bathymetry=True,
             capitals_only=True, line_width=1.5, dpi="300")
    m["compass_options"].update(show=True, position="lower right",
                                style="triangle", size=1.4)
    m["scale_bar"].update(show=True, units="both", position="upper left",
                          length_mode="fixed", fixed_length=500,
                          segments=5)
    m["lines"].update(states=True, rivers=True, wadis=True, eez=True,
                      disputed_lines=True, countries=False)
    m["fills"].update(land=True, deserts=True, biodiversity=True,
                      ecoregions=True)
    m["points"].update(cities=True, airports=True, ports=True)
    m["labels"].update(countries=True, cities=True, rivers=True,
                       regions=True, counties=True)
    state["view"] = {"xlim": [-8500000.0, -3000000.0],
                     "ylim": [-6000000.0, 1500000.0]}
    state["point_alpha"] = 0.85
    state["legend"].update(location="lower left", columns=2, counts=True,
                           count_format="(n, %)", title="Beetles",
                           show_title=True, label_underline=True,
                           shadow=True, handle_length=1.5)
    out["decorated"] = (state, "Decorated \"map\"", (9.0, 6.5))

    # Colour by genus, symbol by species: a nested key, with overrides and
    # open symbols for the holotypes.
    _name, horn = load_fixture("hornbills-orchids.pymappr")
    birds = copy.deepcopy(horn["datasets"][0])
    birds.update(group_by="Species", color_by="Genus", symbol_by="Species",
                 open_by="Type status", open_values=["Holotype"])
    birds["legend_overrides"] = {
        f"color{SEP}Buceros": {"label": "Buceros (great hornbills)",
                               "color": "#123456"},
        f"pair{SEP}Buceros{SEP}bicornis": {"marker": "Star", "size": 45.0},
        f"color{SEP}Anthracoceros": {"order": 0},
    }
    state = copy.deepcopy(horn)
    state["datasets"] = [birds]
    state["legend"].update(counts=True, order="manual", group_swatch="child",
                           bold_groups=False, title=None)
    state["map"]["palette"] = "Colourblind safe (Okabe-Ito)"
    out["nested"] = (state, "nested", (8.0, 6.0))

    # Crossed colour/symbol columns beside a plain dataset: a sectioned
    # legend with a titled plain section.
    crossed = dataset(
        "crossed.csv", ["Habitat", "Sex"],
        [["forest", "male", 10.0, 5.0], ["forest", "female", 11.0, 6.0],
         ["savanna", "male", 12.0, 7.0], ["savanna", "female", 13.0, 8.0],
         ["", "male", 14.5, 9.25]],
        group_by="Habitat", color_by="Habitat", symbol_by="Sex")
    crossed["legend_overrides"] = {f"symbol{SEP}female": {"hidden": True},
                                   f"color{SEP}savanna": {"label": "Grass"}}
    plain = copy.deepcopy(horn["datasets"][1])
    plain["legend_overrides"] = {f"group{SEP}Ophrys": {"label": "Bee orchids",
                                                       "color": "#00aa00"}}
    state = copy.deepcopy(horn)
    state["datasets"] = [crossed, plain]
    state["legend"].update(order="za", hierarchy="never", blank_label="?")
    out["crossed"] = (state, "crossed", None)

    # Several ungrouped datasets whose labels collide, with names that
    # clash as files; a hidden one and an empty one are skipped.
    a = dataset("Sites", [], [[-60.0, -10.0], [-61.5, -11.25]], group_by="")
    b = dataset("sites", [], [[-50.0, -5.0]], group_by="")
    c = dataset("CON.csv", ["Legend"], [["All points", -40.0, 0.0],
                                        ["Other", -41.0, 1.0]],
                vary_symbols=True)
    c["legend_overrides"] = {f"group{SEP}Other": {"hidden": True}}
    hidden = dataset("hidden.csv", ["Legend"], [["x", 1.0, 1.0]],
                     visible=False)
    empty = dataset("empty.csv", ["Legend"], [])
    state = base_state()
    state["datasets"] = [a, b, c, hidden, empty]
    state["map"]["palette"] = "Default"
    state["legend"].update(order="count_desc", counts=True, count_format="%",
                           title="", show_title=True)
    out["multi"] = (state, "multi", None)

    # Names that need escaping in both languages.
    tricky = dataset(
        "tri\"cky'name\\.csv", ["Na'me", "Tab\tbed"],
        [["O'Brien \"Jr\"", "back\\slash", 1.0, 2.0],
         ["caf\u00e9 \u2013 \u00fc", "line\nbreak", 3.0, 4.0],
         ["nul\x00here", "a,b", 5.5, -6.5],
         ["\u00a0nbsp", "", 7.0, 8.0]])
    tricky["source_path"] = "C:\\Field\\Notes\nrm -rf /"
    state = base_state()
    state["datasets"] = [tricky]
    state["legend"]["title"] = "Ti\"tle \\ 'x'"
    out["escapes"] = (state, "Field\\Notes \"x\"\n2", None)

    # No stored view: the continent preset, padded to the axes box.
    state = base_state()
    del state["view"]
    state["map"].update(continent="South America", graticule="10\N{DEGREE SIGN}",
                        hide_grid_labels=True)
    out["no-view"] = (state, "no view", (7.5, 5.0))

    # A regional projection and the globe, at their default centres.
    state = base_state()
    state["map"].update(projection="Lambert: Europe", graticule="10\N{DEGREE SIGN}")
    state["view"] = {"xlim": [-2500000.0, 2500000.0],
                     "ylim": [-2000000.0, 2200000.0]}
    out["lambert"] = (state, "lambert", None)
    state = base_state()
    state["map"].update(projection="Globe (Orthographic)",
                        graticule="10\N{DEGREE SIGN}", ocean="grey")
    state["view"] = {"xlim": [-6378137.0, 6378137.0],
                     "ylim": [-6378137.0, 6378137.0]}
    out["globe"] = (state, "globe", None)

    # Insets as PyMappr's tests hand them over.
    for kind in ("locator", "zoom", "globe"):
        state = base_state()
        state["map"]["inset"].update(show=True)
        state["inset_export"] = inset_export(kind)
        out[f"inset-{kind}"] = (state, f"inset {kind}", None)

    # A state run through the app (see app-inset), when it was made.
    app_input = HERE.parent / "crates" / "mappr-codegen" / "tests" / "data" \
        / "app-inset" / "input.json"
    if app_input.exists():
        data = json.loads(app_input.read_text(encoding="utf-8"))
        size = data["figureSize"]
        out["app-inset"] = (data["state"], data["projectName"],
                            tuple(size) if size else None)
    return out


FULL = {"beetles-standard", "hornbills-orchids"}


def _template_split(code, template, case, label):
    """The script before the template, checking the rest is the template."""
    assert code.endswith(template), f"{case} {label}: template not at the end"
    return code[:-len(template)]


def write_case(out_dir, case, state, project, figure_size):
    from pymappr.export import codegen
    from pymappr.export.literals import _template
    from pymappr.files.projects import entry_from_dict

    folder = Path(out_dir) / case
    folder.mkdir(parents=True, exist_ok=True)
    data = {"state": state, "projectName": project,
            "figureSize": list(figure_size) if figure_size else None}
    (folder / "input.json").write_text(json.dumps(data, indent=1),
                                       encoding="utf-8", newline="")

    def entries():
        return [entry_from_dict(d) for d in state.get("datasets", [])]

    for language, ext in (("Python", "py"), ("R", "R")):
        template = _template("recreate_map." + ext)
        code = codegen.generate_code(copy.deepcopy(state), entries(),
                                     language, project,
                                     figure_size=figure_size)
        head = _template_split(code, template, case, language)
        if case in FULL:
            (folder / f"recreate_map.{ext}").write_text(
                code, encoding="utf-8", newline="")
        else:
            (folder / f"recreate_map.{ext}.head").write_text(
                head, encoding="utf-8", newline="")
        files = codegen.generate_working_directory(
            copy.deepcopy(state), entries(), language, project,
            figure_size=figure_size)
        workdir = folder / f"workdir-{ext}"
        manifest = []
        for rel, content in files.items():
            manifest.append(rel)
            if rel == f"recreate_map.{ext}":
                content = _template_split(content, template, case,
                                          language + " workdir")
                rel += ".head"
            dest = workdir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="")
        (workdir / "MANIFEST").write_text("\n".join(manifest) + "\n",
                                          encoding="utf-8", newline="")


def run_cases(out_dir):
    for case, (state, project, size) in cases().items():
        write_case(out_dir, case, state, project, size)
        print("wrote", case)


# ---------------------------------------------------------------- app inset

def app_inset(out):
    """A beetles map with a locator inset, through PyMappr's app."""
    sys.path.insert(0, str(HERE))
    from pymappr_reference import make_app
    from pymappr.ui.save_image import parse_print_width

    root, app = make_app()
    state = base_state()
    state["map"]["inset"].update(show=True, region="country",
                                 position="upper left")
    state["map"]["lines"]["states"] = True
    app._apply_state(state)
    root.update_idletasks()
    app.renderer.redraw() if hasattr(app.renderer, "redraw") else None
    collected = app._collect_state()
    exported = app.renderer.inset_export()
    if exported is None:
        raise SystemExit("the app drew no inset")
    collected["inset_export"] = json.loads(json.dumps(exported))
    try:
        width_cm = parse_print_width(app.panel.export_width_var.get())
    except ValueError:
        width_cm = None
    size = [float(v) for v in app.renderer.export_size_inches(width_cm)]
    data = {"state": collected, "projectName": "app inset",
            "figureSize": size}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(data, indent=1), encoding="utf-8",
                         newline="")
    root.destroy()


COMMANDS = {"tables": tables, "cases": run_cases, "app-inset": app_inset}

if __name__ == "__main__":
    COMMANDS[sys.argv[2]](*sys.argv[3:])
