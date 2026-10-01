"""What gets drawn: every visible dataset turned into styled point groups and
the legend rows that describe them.

The app draws from this and the code export writes its scripts from it, so
the two cannot disagree about a colour, a label or a legend row. It is pure
- no Tk, no matplotlib - which is also what lets the tests cover it directly.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from pymappr.files.projects import DatasetEntry
from pymappr.styling.legend import (LegendOptions, format_count, is_hidden,
                                    legend_counts, legend_sections,
                                    manual_order, order_labels, override_label)
from pymappr.styling.styles import (PointStyle, apply_override,
                                    attribute_style_maps, default_styles,
                                    group_points, owner_map, resolve_nesting,
                                    row_key, style_by_attributes)

__all__ = ["DatasetLayout", "MapLayout", "column_key", "group_styles",
           "layout_points", "with_default_title", "editor_rows",
           "parent_name_column", "organise_publication_legend"]


@dataclass
class DatasetLayout:
    """One dataset as drawn."""

    entry: DatasetEntry
    # (label, style, rows) per drawn group, in draw order. Hidden legend rows
    # are still here: hiding a row keeps its points on the map.
    groups: list = field(default_factory=list)
    # Group-by mode: raw group value -> the label drawn for it.
    label_map: dict = field(default_factory=dict)
    # Group-by mode: the legend rows, in legend order, hidden ones left out.
    rows: list = field(default_factory=list)
    # Symbol-by mode: this dataset's legend sections.
    sections: list = field(default_factory=list)
    attribute: bool = False
    # Group-by mode: where this dataset's colours start in the palette, so
    # several datasets on one map get distinct default colours.
    palette_offset: int = 0


@dataclass
class MapLayout:
    datasets: list
    # The sectioned legend, when any dataset is styled by Symbol by ...
    sections: list | None
    # ... otherwise the plain legend's rows, in order.
    row_order: list | None

    @property
    def groups(self) -> list:
        return [group for dataset in self.datasets for group in dataset.groups]


def column_key(entry: DatasetEntry, label: str) -> str | None:
    """The frame column (name1, name2, ...) for a name-column label, or None
    for "" / "None"."""
    if not label or label == "None":
        return None
    keys = dict(zip(entry.dataset.name_labels, entry.dataset.name_keys))
    return keys.get(label)


def parent_name_column(dataset, group_by: str) -> str:
    """The label of the name column that *group_by* is built on, or "".

    Genus is the parent of a combined "Genus Species" column: it has fewer
    distinct values, and each row's Genus is the start of that row's full
    name. Colouring the full-name groups by their parent puts the species of
    one genus in one shade and lets their shapes restart inside it. The
    species epithet is not a parent - it does not lead the name - and a
    column with a blank cell is not either, since a blank prefixes every
    name. With several candidates the one closest to *group_by* (the most
    distinct values) wins. Returns "" when nothing qualifies.
    """
    keys = dict(zip(dataset.name_labels, dataset.name_keys))
    group_key = keys.get(group_by)
    if group_key is None:
        return ""
    frame = dataset.frame

    def text(key):
        return frame[key].fillna("").astype(str).str.strip()

    names = text(group_key)
    best, best_count = "", 0
    for label, key in keys.items():
        if key == group_key:
            continue
        parts = text(key)
        count = parts.nunique()
        if (count >= names.nunique() or count <= best_count
                or (parts == "").any()
                or not all(name.startswith(part)
                           for name, part in zip(names, parts))):
            continue
        best, best_count = label, count
    return best


def organise_publication_legend(entries,
                                options: LegendOptions) -> LegendOptions:
    """Arrange the legend for a journal figure: species rows sorted A-Z, each
    genus a block in its own shade.

    Three shades alone cannot separate every species, but shade by genus plus
    a shape that restarts within each genus can, and sorting keeps a genus's
    rows together. A dataset already coloured by a column keeps that choice,
    and a manual order is the user's own arrangement, so neither is touched.
    Sets ``color_by`` on the entries and returns the adjusted *options*.
    """
    for entry in entries:
        if not entry.color_by:
            entry.color_by = parent_name_column(entry.dataset,
                                                entry.group_by)
    if options.order == "manual":
        return options
    return dataclasses.replace(options, order="az")


def _visible(entries) -> list[DatasetEntry]:
    return [e for e in entries if e.visible and len(e.dataset)]


def with_default_title(entries, options: LegendOptions) -> LegendOptions:
    """*options* with the title defaulted: a single dataset in group-by mode
    is titled by its group-by column. In Symbol-by mode the sections name the
    columns, and with several datasets no one column fits."""
    if options.title is not None:
        return options
    visible = _visible(entries)
    if len(visible) == 1 and column_key(visible[0],
                                        visible[0].symbol_by) is None:
        return dataclasses.replace(options,
                                   title=visible[0].group_by or None)
    return options


def group_styles(entry: DatasetEntry, palette: list[str],
                 palette_offset: int = 0) -> dict[str, PointStyle]:
    """Group label -> style in group-by mode, from the whole dataset (so a
    group keeps its look while the filter hides others), with the user's
    per-row customizations applied."""
    frame = entry.dataset.frame
    groups = group_points(frame, column_key(entry, entry.group_by))
    labels = [label for label, _sub in groups]
    color_key = column_key(entry, entry.color_by)
    color_keys = None
    if color_key is not None and color_key in frame.columns:
        # One colour per group: its value in the Color by column, so every
        # cat group shares "Felines"' colour.
        color_keys = [str(sub[color_key].iloc[0]) if len(sub) else ""
                      for _label, sub in groups]
    fresh = default_styles(labels, color_keys=color_keys,
                           vary_symbols=entry.vary_symbols,
                           palette_offset=palette_offset, palette=palette)
    return {label: apply_override(fresh[label], entry.legend_overrides.get(
                row_key("group", label)))
            for label in labels}


def _plain_layout(entry, shown, palette, palette_offset, multi, used,
                  options) -> tuple[DatasetLayout, int]:
    """The dataset's layout and where the next dataset's colours start."""
    styles = group_styles(entry, palette, palette_offset)
    layout = DatasetLayout(entry=entry, palette_offset=palette_offset)
    groups = group_points(shown, column_key(entry, entry.group_by))
    total = sum(len(sub) for _label, sub in groups)
    counts: dict[str, int] = {}
    placed: dict[str, int] = {}
    for label, sub in groups:
        override = entry.legend_overrides.get(row_key("group", label))
        display = override_label(override)
        if display is None:
            # With several datasets, a lone "All points" group takes its
            # dataset's name and a label another dataset already used gets
            # the name appended. A row the user named is left alone.
            display = label
            if multi and label == "All points":
                display = entry.name
            elif multi and label in used:
                display = f"{label} ({entry.name})"
        used.add(display)
        if options.counts:
            display = format_count(display, len(sub), total,
                                   options.count_format)
        style = styles.get(label, PointStyle())
        layout.label_map[label] = display
        layout.groups.append((display, style, sub))
        if is_hidden(override):
            continue
        layout.rows.append((display, style))
        counts[display] = len(sub)
        placed[display] = manual_order(override)
    if options.order == "manual":
        order = sorted(counts, key=lambda text: placed[text])
    else:
        order = order_labels(list(counts), options.order,
                             lambda text: counts.get(text, 0))
    rank = {text: i for i, text in enumerate(order)}
    layout.rows.sort(key=lambda row: rank[row[0]])
    return layout, palette_offset + len(styles)


def _attribute_layout(entry, shown, palette, multi,
                      options) -> DatasetLayout:
    frame = entry.dataset.frame
    color_key = column_key(entry, entry.color_by)
    symbol_key = column_key(entry, entry.symbol_by)
    # Colours and shapes come from the whole dataset, so they stay put while
    # the filter hides values.
    color_map, symbol_map = attribute_style_maps(
        frame, color_key, symbol_key, options.hierarchy, palette=palette)
    nested = resolve_nesting(frame, color_key, symbol_key, options.hierarchy)
    groups = style_by_attributes(shown, color_key, symbol_key, color_map,
                                 symbol_map, entry.legend_overrides, nested,
                                 palette=palette)
    filtering = shown is not frame

    def shown_values(key):
        # None means "no filter", which the legend treats differently from
        # "every value happens to be shown".
        if not filtering or key is None or key not in shown.columns:
            return None
        return set(shown[key].fillna(""))

    counts = (legend_counts(shown, color_key, symbol_key)
              if (options.counts or options.orders_by_count) else {})
    sections = legend_sections(
        frame, color_key, symbol_key, color_map, symbol_map, entry.color_by,
        entry.symbol_by, shown_colors=shown_values(color_key),
        shown_symbols=shown_values(symbol_key), counts=counts,
        prefix=(f"{entry.name}: " if multi and options.dataset_prefix
                else ""),
        options=options, overrides=entry.legend_overrides)
    return DatasetLayout(entry=entry, groups=groups, sections=sections,
                         attribute=True)


def layout_points(entries, options: LegendOptions, palette: list[str],
                  shown=None) -> MapLayout:
    """Every visible dataset's point groups and legend.

    *shown(entry)* returns the rows to draw - the filter bar's selection in
    the app; every row when omitted, as in the code export. A dataset with a
    Symbol by column gets the sectioned color + symbol key; when any dataset
    does, the rest join it as titled sections of their own.
    """
    visible = _visible(entries)
    multi = len(visible) > 1
    sectioned = any(column_key(e, e.symbol_by) for e in visible)
    datasets: list[DatasetLayout] = []
    sections: list = []
    row_order: list[str] = []
    palette_offset = 0
    used: set[str] = set()
    for entry in visible:
        rows = shown(entry) if shown else entry.dataset.frame
        if column_key(entry, entry.symbol_by):
            layout = _attribute_layout(entry, rows, palette, multi, options)
            sections += layout.sections
        else:
            layout, palette_offset = _plain_layout(
                entry, rows, palette, palette_offset, multi, used, options)
            row_order += [text for text, _style in layout.rows]
            if sectioned and layout.rows:
                sections.append((entry.name if options.section_titles
                                 else "", layout.rows))
        datasets.append(layout)
    return MapLayout(datasets=datasets,
                     sections=sections if sectioned else None,
                     row_order=None if sectioned else row_order)


# ------------------------------------------------------------ legend editor

def editor_rows(entry: DatasetEntry, options: LegendOptions,
                palette: list[str], palette_offset: int = 0) -> list:
    """The dataset's legend rows for the row editor, as
    ``(key, value, PointStyle, depth)`` in the order the legend draws them.

    In group-by mode these are the groups; with Symbol by they are the colour
    values, the symbol values, or the nested pairs, whichever the key is made
    of - so the editor lists exactly what the legend shows.
    """
    frame = entry.dataset.frame
    color_key = column_key(entry, entry.color_by)
    symbol_key = column_key(entry, entry.symbol_by)
    if symbol_key is None:
        return _ordered(
            [(row_key("group", label), label, style, 0) for label, style
             in group_styles(entry, palette, palette_offset).items()], entry)

    color_map, symbol_map = attribute_style_maps(
        frame, color_key, symbol_key, options.hierarchy, palette=palette)
    if resolve_nesting(frame, color_key, symbol_key, options.hierarchy):
        owner = owner_map(frame, symbol_key, color_key)
        rows: list = []
        for value, color in color_map.items():
            rows.append((row_key("color", value), value,
                         PointStyle(color=color, marker="Circle"), 0))
            rows += _ordered(
                [(row_key("pair", value, kid), kid,
                  PointStyle(color=color, marker=symbol_map[kid]), 1)
                 for kid in symbol_map if owner.get(kid, "") == value],
                entry)
        return _ordered(rows, entry, blocks=True)
    return (_ordered([(row_key("color", value), value,
                       PointStyle(color=color, marker="Circle"), 0)
                      for value, color in color_map.items()], entry)
            + _ordered([(row_key("symbol", value), value,
                         PointStyle(color=options.symbol_swatch_color,
                                    marker=marker), 0)
                        for value, marker in symbol_map.items()], entry))


def _ordered(rows: list, entry: DatasetEntry, blocks: bool = False) -> list:
    """Editor rows in manual order, rows never placed keeping the order the
    data gave them. With *blocks*, each depth-0 row carries the children that
    follow it, so moving a genus moves its species too."""
    def position(key):
        return manual_order(entry.legend_overrides.get(key))

    if not blocks:
        return [row for _i, row in sorted(
            enumerate(rows), key=lambda item: (position(item[1][0]),
                                               item[0]))]
    grouped: list = []
    for row in rows:
        if row[3] == 0:
            grouped.append([row])
        elif grouped:
            grouped[-1].append(row)
    ordered = sorted(enumerate(grouped),
                     key=lambda item: (position(item[1][0][0]), item[0]))
    return [row for _i, block in ordered for row in block]
