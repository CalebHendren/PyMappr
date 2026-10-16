// Point symbology: which colour, shape and size every point is drawn with,
// and the legend rows that describe them. A port of PyMappr's
// pymappr/styling/styles.py and pymappr/styling/layout.py; the rules,
// orders and labels are PyMappr's, and the tests compare the output with
// PyMappr's own (scripts/reference_legend.py).
//
// Everything here is pure: a ProjectState (plus an optional filter) in,
// styles and legend rows out.

import { luminance } from "./colors";
import {
  type CountKey,
  type LegendSection,
  type LegendSectionRow,
  drawnLegend,
  type DrawnLegend,
  formatCount,
  isHidden,
  legendCounts,
  legendSections,
  manualOrder,
  orderLabels,
  overrideLabel,
} from "./legend";
import { OPEN_SUFFIX } from "./markers";
import type { DatasetEntry, LegendOptions, ProjectState, RowOverride } from "./model";

export { MARKERS, OPEN_SUFFIX } from "./markers";

// ---------------------------------------------------------------- styles

/** How a group of points is drawn. `size` is matplotlib's scatter area in
 * pt². `fill` is the inside of an open marker (null leaves it see-through). */
export type PointStyle = { color: string; marker: string; size: number; fill: string | null };

export const DEFAULT_STYLE: Readonly<PointStyle> = { color: "#d62728", marker: "Circle", size: 30, fill: null };

export function pointStyle(partial: Partial<PointStyle> = {}): PointStyle {
  return { ...DEFAULT_STYLE, ...partial };
}

/** Open markers draw only the outline (in the style's colour). */
export function isOpen(style: PointStyle): boolean {
  return style.marker.endsWith(OPEN_SUFFIX);
}

/** How many shapes stay tellable apart at map point sizes. */
export const LEGIBLE_MARKER_LIMIT = 6;

/** The order shapes are handed out in when symbols vary. */
export const MARKER_CYCLE = [
  "Circle",
  "Square",
  "Triangle",
  "Diamond",
  "Star",
  "Plus",
  "X",
  "Pentagon",
  "Triangle down",
  "Hexagon",
  "Thin diamond",
  "Triangle left",
  "Octagon",
  "Triangle right",
];

export const DEFAULT_PALETTE = [
  "#d62728",
  "#1f77b4",
  "#2ca02c",
  "#ff7f0e",
  "#9467bd",
  "#8c564b",
  "#e377c2",
  "#17becf",
  "#bcbd22",
  "#7f7f7f",
];

/** Okabe-Ito, in PyMappr's order (the first few far apart). */
export const OKABE_ITO = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9", "#f0e442", "#000000"];

export const BLACK_AND_WHITE = ["#000000", "#ffffff", "#808080"];

export const BLACK_AND_WHITE_NAME = "Black & white";
export const DEFAULT_PALETTE_NAME = "Default";

/** Palette names as projects store them, to their colours. */
export const PALETTES: Record<string, string[]> = {
  Default: DEFAULT_PALETTE,
  "Colourblind safe (Okabe-Ito)": OKABE_ITO,
  [BLACK_AND_WHITE_NAME]: BLACK_AND_WHITE,
};

/** The palette a name refers to, falling back to the default. */
export function paletteFor(name: string | null | undefined): string[] {
  return name && Object.hasOwn(PALETTES, name) ? PALETTES[name] : DEFAULT_PALETTE;
}

/** The outline around filled markers unless the project sets another. */
export const POINT_EDGE_COLOR = "#ffffff";
export const POINT_EDGE_WIDTH = 0.5;
/** The Standard preset's outline. */
export const PUBLICATION_POINT_EDGE = { color: "#000000", width: 0.6 };

/** The inside of an open symbol marking rows (see openForm). */
export const OPEN_FILL = "#ffffff";
/** The outline an open symbol gets when its own colour is too light. */
export const OPEN_LIGHT_OUTLINE = "#000000";
export const OPEN_LIGHT_LUMINANCE = 0.85;

/** A style as an open symbol marking a row: the outline of its symbol in its
 * colour and size, filled white; a colour too light to see on white is
 * outlined in black instead. */
export function openForm(style: PointStyle): PointStyle {
  const marker = isOpen(style) ? style.marker : style.marker + OPEN_SUFFIX;
  let color = style.color;
  const lum = luminance(color);
  if (lum !== null && lum > OPEN_LIGHT_LUMINANCE) color = OPEN_LIGHT_OUTLINE;
  return { color, marker, size: style.size, fill: OPEN_FILL };
}

/** Face, edge and edge width (pt) a marker is painted with: open markers
 * draw only an outline in their own colour, filled ones take the point
 * outline. PyMappr's `_marker_paint`; the map and the legend both use it. */
export function markerPaint(
  style: PointStyle,
  edge: { color: string; width: number },
): { face: string; edge: string; edgeWidth: number } {
  if (isOpen(style)) return { face: style.fill ?? "none", edge: style.color, edgeWidth: 1.2 };
  return { face: style.color, edge: edge.color || POINT_EDGE_COLOR, edgeWidth: Math.max(edge.width, 0) };
}

/** Legend rows are keyed by a tagged key so a value in both the colour and
 * the symbol column keeps two rows. NUL cannot occur in a data value. */
export const ROW_SEP = "\x00";

/** A legend row's identity: `rowKey("pair", genus, species)`. `kind` is
 * "group", "color", "symbol" or "pair". */
export function rowKey(kind: "group" | "color" | "symbol" | "pair", ...parts: string[]): string {
  return [kind, ...parts.map(String)].join(ROW_SEP);
}

/** A style with whatever colour/marker/size the user pinned for its row. */
export function applyOverride(style: PointStyle | null, override: RowOverride | null | undefined): PointStyle | null {
  if (!override || Object.keys(override).length === 0 || style === null) return style;
  return {
    color: override.color || style.color,
    marker: override.marker || style.marker,
    size: Number(override.size || style.size),
    fill: null,
  };
}

function overrideOf(entry: DatasetEntry, key: string): RowOverride | undefined {
  const all = entry.legend_overrides ?? {};
  return Object.hasOwn(all, key) ? all[key] : undefined;
}

// ---------------------------------------------------------------- frames

/** Some rows of a dataset (indices into `entry.rows`), standing in for the
 * pandas frames PyMappr works on. */
export type Frame = { entry: DatasetEntry; rows: number[] };

export function wholeFrame(entry: DatasetEntry): Frame {
  return { entry, rows: entry.rows.map((_r, i) => i) };
}

function hasColumn(frame: Frame, key: string | null): key is string {
  return key !== null && frame.entry.columns.includes(key);
}

/** A cell as text, blank for a missing value (pandas' `fillna("")`). */
function cell(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

/** One column's values over the frame's rows, blanks as "". */
export function columnValues(frame: Frame, key: string): string[] {
  const at = frame.entry.columns.indexOf(key);
  return frame.rows.map((r) => cell(frame.entry.rows[r]?.[at]));
}

function unique<T>(values: Iterable<T>): T[] {
  return [...new Set(values)];
}

/** Split a frame into (label, rows) groups in order of first appearance;
 * one "All points" group without a usable group column. */
export function groupPoints(frame: Frame, groupBy: string | null): [string, Frame][] {
  if (frame.rows.length === 0) return [];
  if (!hasColumn(frame, groupBy)) return [["All points", frame]];
  const values = columnValues(frame, groupBy);
  const groups = new Map<string, number[]>();
  values.forEach((value, i) => {
    const rows = groups.get(value);
    if (rows) rows.push(frame.rows[i]);
    else groups.set(value, [frame.rows[i]]);
  });
  return [...groups].map(([value, rows]) => [value || "(blank)", { entry: frame.entry, rows }]);
}

/** Default styles for group labels: palette colours round-robin (shapes too
 * when `varySymbols`), or, with `colorKeys`, one colour per key with the
 * shape cycling inside each colour. */
export function defaultStyles(
  labels: string[],
  colorKeys: string[] | null = null,
  varySymbols = false,
  paletteOffset = 0,
  palette: string[] | null = null,
): Record<string, PointStyle> {
  const colors = palette && palette.length ? palette : DEFAULT_PALETTE;
  const styles: Record<string, PointStyle> = {};
  if (colorKeys === null) {
    labels.forEach((label, i) => {
      styles[label] = pointStyle({
        color: colors[(i + paletteOffset) % colors.length],
        marker: varySymbols ? MARKER_CYCLE[i % MARKER_CYCLE.length] : "Circle",
      });
    });
    return styles;
  }
  const colorOrder = unique(colorKeys);
  const seen = new Map<string, number>();
  labels.forEach((label, i) => {
    const key = colorKeys[i];
    const shape = seen.get(key) ?? 0;
    seen.set(key, shape + 1);
    styles[label] = pointStyle({
      color: colors[(colorOrder.indexOf(key) + paletteOffset) % colors.length],
      marker: MARKER_CYCLE[shape % MARKER_CYCLE.length],
    });
  });
  return styles;
}

/** True when every value of the inner column occurs under exactly one value
 * of the outer column: a hierarchy (genus/species), not a cross-product. */
export function nestsWithin(frame: Frame, outerKey: string | null, innerKey: string | null): boolean {
  if (!outerKey || !innerKey || frame.rows.length === 0) return false;
  if (!hasColumn(frame, outerKey) || !hasColumn(frame, innerKey)) return false;
  const outer = columnValues(frame, outerKey);
  const inner = columnValues(frame, innerKey);
  const owners = new Map<string, string>();
  for (let i = 0; i < inner.length; i++) {
    const seen = owners.get(inner[i]);
    if (seen === undefined) owners.set(inner[i], outer[i]);
    else if (seen !== outer[i]) return false;
  }
  return true;
}

/** Whether to treat the two columns as a hierarchy, honouring the
 * Hierarchy setting ("auto" detects it). */
export function resolveNesting(
  frame: Frame,
  colorKey: string | null,
  symbolKey: string | null,
  mode: string = "auto",
): boolean {
  if (!colorKey || !symbolKey || frame.rows.length === 0) return false;
  if (!hasColumn(frame, colorKey) || !hasColumn(frame, symbolKey)) return false;
  if (mode === "never") return false;
  if (mode === "always") return true;
  return nestsWithin(frame, colorKey, symbolKey);
}

/** Symbol value -> the colour group it belongs to, first occurrence wins. */
export function ownerMap(frame: Frame, symbolKey: string, colorKey: string): Map<string, string> {
  const owner = new Map<string, string>();
  const symbols = columnValues(frame, symbolKey);
  const colors = columnValues(frame, colorKey);
  symbols.forEach((symbol, i) => {
    if (!owner.has(symbol)) owner.set(symbol, colors[i]);
  });
  return owner;
}

/** How many shapes the reader has to tell apart (the largest number inside
 * one colour group under nesting, otherwise every symbol value). */
export function markerLoad(
  frame: Frame,
  colorKey: string | null,
  symbolKey: string | null,
  hierarchy = "auto",
): number {
  if (!symbolKey || !hasColumn(frame, symbolKey) || frame.rows.length === 0) return 0;
  const symbols = columnValues(frame, symbolKey);
  if (!resolveNesting(frame, colorKey, symbolKey, hierarchy)) return new Set(symbols).size;
  const colors = columnValues(frame, colorKey as string);
  const per = new Map<string, Set<string>>();
  symbols.forEach((symbol, i) => {
    const set = per.get(colors[i]) ?? new Set();
    set.add(symbol);
    per.set(colors[i], set);
  });
  return Math.max(...[...per.values()].map((s) => s.size));
}

/** Value -> colour and value -> marker for two-attribute styling, from the
 * whole dataset so they stay put while points are filtered. Shapes restart
 * in each colour group when the symbol column nests in the colour column. */
export function attributeStyleMaps(
  frame: Frame,
  colorKey: string | null,
  symbolKey: string | null,
  hierarchy = "auto",
  palette: string[] | null = null,
): [Map<string, string>, Map<string, string>] {
  const colors = palette && palette.length ? palette : DEFAULT_PALETTE;
  const colorMap = new Map<string, string>();
  if (colorKey && hasColumn(frame, colorKey)) {
    for (const value of unique(columnValues(frame, colorKey))) colorMap.set(value, colors[colorMap.size % colors.length]);
  }
  const symbolMap = new Map<string, string>();
  if (symbolKey && hasColumn(frame, symbolKey)) {
    const nested = resolveNesting(frame, colorKey, symbolKey, hierarchy);
    const owner = nested ? ownerMap(frame, symbolKey, colorKey as string) : new Map<string, string>();
    const seen = new Map<string, number>();
    for (const value of unique(columnValues(frame, symbolKey))) {
      const group = owner.get(value) ?? "";
      const index = seen.get(group) ?? 0;
      seen.set(group, index + 1);
      symbolMap.set(value, MARKER_CYCLE[index % MARKER_CYCLE.length]);
    }
  }
  return [colorMap, symbolMap];
}

export type DrawGroup = { label: string; style: PointStyle; rows: number[] };

/** Split a frame into draw groups by (colour value, symbol value), with the
 * legend rows' customisations applied: under a nested key the leaf row owns
 * the combination; a crossed key takes the colour from its colour row and
 * the shape from its symbol row. */
export function styleByAttributes(
  frame: Frame,
  colorKey: string | null,
  symbolKey: string | null,
  colorMap: Map<string, string>,
  symbolMap: Map<string, string>,
  overrides: Record<string, RowOverride> | null = null,
  nested = false,
  palette: string[] | null = null,
): DrawGroup[] {
  if (frame.rows.length === 0) return [];
  const all = overrides ?? {};
  const ckey = colorKey && hasColumn(frame, colorKey) ? colorKey : null;
  const skey = symbolKey && hasColumn(frame, symbolKey) ? symbolKey : null;
  const blank = frame.rows.map(() => "");
  const cvals = ckey ? columnValues(frame, ckey) : blank;
  const svals = skey ? columnValues(frame, skey) : blank;
  const defaultColor = colorMap.values().next().value || (palette && palette.length ? palette : DEFAULT_PALETTE)[0];
  const pairs = new Map<string, { cval: string; sval: string; rows: number[] }>();
  frame.rows.forEach((row, i) => {
    const id = cvals[i] + ROW_SEP + svals[i];
    const pair = pairs.get(id);
    if (pair) pair.rows.push(row);
    else pairs.set(id, { cval: cvals[i], sval: svals[i], rows: [row] });
  });
  const groups: DrawGroup[] = [];
  for (const { cval, sval, rows } of pairs.values()) {
    const label = [cval, sval].filter((p) => p).join(" / ") || "All points";
    let style = pointStyle({ color: colorMap.get(cval) ?? defaultColor, marker: symbolMap.get(sval) ?? "Circle" });
    if (Object.keys(all).length) style = overrideFor(style, all, cval, sval, nested, ckey !== null);
    groups.push({ label, style, rows });
  }
  return groups;
}

function overrideFor(
  style: PointStyle,
  overrides: Record<string, RowOverride>,
  cval: string,
  sval: string,
  nested: boolean,
  hasColorKey: boolean,
): PointStyle {
  const get = (key: string) => (Object.hasOwn(overrides, key) ? overrides[key] : undefined);
  if (nested) return applyOverride(style, get(rowKey("pair", cval, sval))) as PointStyle;
  const base = style;
  style = applyOverride(style, get(rowKey("symbol", sval))) as PointStyle;
  if (hasColorKey) style = pointStyle({ color: base.color, marker: style.marker, size: style.size });
  const color = get(rowKey("color", cval))?.color;
  return pointStyle({ color: color || style.color, marker: style.marker, size: style.size });
}

// ---------------------------------------------------------------- layout

/** One dataset as drawn. */
export type DatasetLayout = {
  entry: DatasetEntry;
  /** Index of the dataset in the project. */
  index: number;
  /** Draw groups in draw order; hidden legend rows are still here. */
  groups: DrawGroup[];
  /** Group-by mode: raw group value -> the label drawn for it. */
  labelMap: Record<string, string>;
  /** Group-by mode: the legend rows in order, hidden ones left out. */
  rows: { label: string; style: PointStyle }[];
  /** Symbol-by mode: this dataset's legend sections. */
  sections: LegendSection[];
  attribute: boolean;
  /** Group-by mode: where this dataset's colours start in the palette. */
  paletteOffset: number;
  /** Rows drawn with open symbols, over the groups (labels "_open: …"). */
  openGroups: DrawGroup[];
};

export type MapLayout = {
  datasets: DatasetLayout[];
  /** The sectioned legend, when any dataset is styled by Symbol by… */
  sections: LegendSection[] | null;
  /** …otherwise the plain legend's rows, in order. */
  rowOrder: string[] | null;
  /** The last legend row, saying what open symbols mark. */
  openNote: { label: string; style: PointStyle } | null;
};

/** Everything to draw, in draw order: open symbols last, on top. */
export function layoutGroups(layout: MapLayout): (DrawGroup & { dataset: number })[] {
  return [
    ...layout.datasets.flatMap((d) => d.groups.map((g) => ({ ...g, dataset: d.index }))),
    ...layout.datasets.flatMap((d) => d.openGroups.map((g) => ({ ...g, dataset: d.index }))),
  ];
}

export const OPEN_GROUP_PREFIX = "_open: ";

/** The frame column (name1, name2, …) for a name-column label, or null for
 * "" and "None". */
export function columnKey(entry: DatasetEntry, label: string | null | undefined): string | null {
  if (!label || label === "None") return null;
  let key: string | null = null;
  entry.name_labels.forEach((l, i) => {
    if (l === label) key = `name${i + 1}`;
  });
  return key;
}

/** Which of the frame's rows draw with open symbols, or null when none can. */
export function openMask(entry: DatasetEntry, frame: Frame): boolean[] | null {
  const key = columnKey(entry, entry.open_by);
  if (key === null || !hasColumn(frame, key) || !entry.open_values?.length) return null;
  const values = new Set(entry.open_values.map(String));
  return columnValues(frame, key).map((v) => values.has(v));
}

/** The distinct non-blank values of a name column, trimmed and sorted. */
export function nameColumnValues(entry: DatasetEntry, label: string): string[] {
  const key = columnKey(entry, label);
  const frame = wholeFrame(entry);
  if (key === null || !hasColumn(frame, key)) return [];
  return unique(columnValues(frame, key).map((v) => v.trim()))
    .filter((v) => v)
    .sort(compareCodePoints);
}

function compareCodePoints(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

const TYPE_STATUS_NAMES = ["type status", "typestatus", "type", "status", "type material"];

/** [column, value] marking the holotypes, when a type-status column has a
 * "Holotype" value; null otherwise. */
export function holotypeMarking(entry: DatasetEntry): [string, string] | null {
  for (const label of entry.name_labels) {
    if (!TYPE_STATUS_NAMES.includes(label.trim().toLowerCase())) continue;
    for (const value of nameColumnValues(entry, label)) {
      if (value.toLowerCase() === "holotype") return [label, value];
    }
  }
  return null;
}

/** The open-symbol value a newly chosen Open column starts on: "Holotype"
 * when there is one, else the first value (PyMappr's on_open_by). */
export function defaultOpenValues(entry: DatasetEntry, column: string): string[] {
  const values = column ? nameColumnValues(entry, column) : [];
  const chosen = values.find((v) => v.toLowerCase() === "holotype") ?? values[0] ?? "";
  return chosen ? [chosen] : [];
}

function splitOpen(layout: DatasetLayout): void {
  const kept: DrawGroup[] = [];
  for (const group of layout.groups) {
    const mask = openMask(layout.entry, { entry: layout.entry, rows: group.rows });
    if (mask === null || !mask.some(Boolean)) {
      kept.push(group);
      continue;
    }
    kept.push({ ...group, rows: group.rows.filter((_r, i) => !mask[i]) });
    layout.openGroups.push({
      label: OPEN_GROUP_PREFIX + group.label,
      style: openForm(group.style),
      rows: group.rows.filter((_r, i) => mask[i]),
    });
  }
  layout.groups = kept;
}

function openNote(datasets: DatasetLayout[], options: LegendOptions): MapLayout["openNote"] {
  const values: string[] = [];
  for (const dataset of datasets) {
    if (dataset.openGroups.length) {
      for (const v of dataset.entry.open_values) if (!values.includes(v)) values.push(v);
    }
  }
  if (!values.length) return null;
  return {
    label: values.join(", "),
    style: openForm(pointStyle({ color: options.symbol_swatch_color, marker: "Circle", size: 30 })),
  };
}

/** The label of the name column `groupBy` is built on (Genus for a combined
 * "Genus Species"), or "". */
export function parentNameColumn(entry: DatasetEntry, groupBy: string): string {
  const keys = new Map<string, string>();
  entry.name_labels.forEach((l, i) => keys.set(l, `name${i + 1}`));
  const groupKey = keys.get(groupBy);
  if (groupKey === undefined) return "";
  const frame = wholeFrame(entry);
  const text = (key: string) => (hasColumn(frame, key) ? columnValues(frame, key) : frame.rows.map(() => "")).map((v) => v.trim());
  const names = text(groupKey);
  const nameCount = new Set(names).size;
  let best = "";
  let bestCount = 0;
  for (const [label, key] of keys) {
    if (key === groupKey) continue;
    const parts = text(key);
    const count = new Set(parts).size;
    if (
      count >= nameCount ||
      count <= bestCount ||
      parts.some((p) => p === "") ||
      !names.every((name, i) => name.startsWith(parts[i]))
    )
      continue;
    best = label;
    bestCount = count;
  }
  return best;
}

/** Arrange the legend for a journal figure: entries without a Color by are
 * shaded by their parent column, and rows sort A–Z unless the order is
 * manual. Returns new entries and options. */
export function organisePublicationLegend(
  entries: DatasetEntry[],
  options: LegendOptions,
): { entries: DatasetEntry[]; options: LegendOptions } {
  const out = entries.map((entry) =>
    entry.color_by ? entry : { ...entry, color_by: parentNameColumn(entry, entry.group_by) },
  );
  return { entries: out, options: options.order === "manual" ? options : { ...options, order: "az" } };
}

function visibleEntries(entries: DatasetEntry[]): [DatasetEntry, number][] {
  return entries.map((e, i) => [e, i] as [DatasetEntry, number]).filter(([e]) => e.visible && e.rows.length > 0);
}

/** Options with the title defaulted: one plain dataset is titled by its
 * Group by column; with the title off there is none. */
export function withDefaultTitle(entries: DatasetEntry[], options: LegendOptions): LegendOptions {
  if (!options.show_title) return { ...options, title: null };
  if (options.title !== null && options.title !== undefined) return options;
  const visible = visibleEntries(entries);
  if (visible.length === 1 && columnKey(visible[0][0], visible[0][0].symbol_by) === null) {
    return { ...options, title: visible[0][0].group_by || null };
  }
  return options;
}

/** Group label -> style in group-by mode, from the whole dataset, with the
 * rows' customisations applied. */
export function groupStyles(entry: DatasetEntry, palette: string[], paletteOffset = 0): Record<string, PointStyle> {
  const frame = wholeFrame(entry);
  const groups = groupPoints(frame, columnKey(entry, entry.group_by));
  const labels = groups.map(([label]) => label);
  const colorKey = columnKey(entry, entry.color_by);
  let colorKeys: string[] | null = null;
  if (colorKey !== null && hasColumn(frame, colorKey)) {
    colorKeys = groups.map(([, sub]) => (sub.rows.length ? columnValues(sub, colorKey)[0] : ""));
  }
  const fresh = defaultStyles(labels, colorKeys, entry.vary_symbols, paletteOffset, palette);
  const out: Record<string, PointStyle> = {};
  for (const label of labels) {
    out[label] = applyOverride(fresh[label], overrideOf(entry, rowKey("group", label))) as PointStyle;
  }
  return out;
}

function plainLayout(
  entry: DatasetEntry,
  index: number,
  shown: Frame,
  palette: string[],
  paletteOffset: number,
  multi: boolean,
  used: Set<string>,
  options: LegendOptions,
): [DatasetLayout, number] {
  const styles = groupStyles(entry, palette, paletteOffset);
  const layout: DatasetLayout = {
    entry,
    index,
    groups: [],
    labelMap: {},
    rows: [],
    sections: [],
    attribute: false,
    paletteOffset,
    openGroups: [],
  };
  const groups = groupPoints(shown, columnKey(entry, entry.group_by));
  const total = groups.reduce((n, [, sub]) => n + sub.rows.length, 0);
  const counts = new Map<string, number>();
  const placed = new Map<string, number>();
  for (const [label, sub] of groups) {
    const override = overrideOf(entry, rowKey("group", label));
    let display = overrideLabel(override);
    if (display === null) {
      display = label;
      if (multi && label === "All points") display = entry.name;
      else if (multi && used.has(label)) display = `${label} (${entry.name})`;
    }
    used.add(display);
    if (options.counts) display = formatCount(display, sub.rows.length, total, options.count_format);
    const style = Object.hasOwn(styles, label) ? styles[label] : pointStyle();
    layout.labelMap[label] = display;
    layout.groups.push({ label: display, style, rows: sub.rows });
    if (isHidden(override)) continue;
    layout.rows.push({ label: display, style });
    counts.set(display, sub.rows.length);
    placed.set(display, manualOrder(override));
  }
  const labels = [...counts.keys()];
  const order =
    options.order === "manual"
      ? [...labels].sort((a, b) => (placed.get(a) as number) - (placed.get(b) as number))
      : orderLabels(labels, options.order, (text) => counts.get(text) ?? 0);
  const rank = new Map(order.map((text, i) => [text, i]));
  layout.rows.sort((a, b) => (rank.get(a.label) as number) - (rank.get(b.label) as number));
  return [layout, paletteOffset + Object.keys(styles).length];
}

function attributeLayout(
  entry: DatasetEntry,
  index: number,
  shown: Frame,
  filtering: boolean,
  palette: string[],
  multi: boolean,
  options: LegendOptions,
): DatasetLayout {
  const frame = wholeFrame(entry);
  const colorKey = columnKey(entry, entry.color_by);
  const symbolKey = columnKey(entry, entry.symbol_by);
  const [colorMap, symbolMap] = attributeStyleMaps(frame, colorKey, symbolKey, options.hierarchy, palette);
  const nested = resolveNesting(frame, colorKey, symbolKey, options.hierarchy);
  const groups = styleByAttributes(shown, colorKey, symbolKey, colorMap, symbolMap, entry.legend_overrides, nested, palette);
  const shownValues = (key: string | null) =>
    !filtering || key === null || !hasColumn(shown, key) ? null : new Set(columnValues(shown, key));
  const ordersByCount = options.order === "count_desc" || options.order === "count_asc";
  const counts = options.counts || ordersByCount ? legendCounts(shown, colorKey, symbolKey) : new Map<CountKey, number>();
  const sections = legendSections(frame, colorKey, symbolKey, colorMap, symbolMap, entry.color_by, entry.symbol_by, {
    shownColors: shownValues(colorKey),
    shownSymbols: shownValues(symbolKey),
    counts,
    prefix: multi && options.dataset_prefix ? `${entry.name}: ` : "",
    options,
    overrides: entry.legend_overrides,
  });
  return {
    entry,
    index,
    groups,
    labelMap: {},
    rows: [],
    sections,
    attribute: true,
    paletteOffset: 0,
    openGroups: [],
  };
}

/** The filter bar's selection: show only rows of `dataset` whose `key`
 * column (name1, name2, …) holds one of `allowed` ("" for blanks). */
export type PointFilter = { dataset: number; key: string; allowed: string[] };

/** The rows a filter leaves, or null when it does not apply to `index`
 * (PyMappr's `_filtered_frame`: a filter on a missing column is no filter). */
export function filteredRows(entry: DatasetEntry, index: number, filter: PointFilter | null | undefined): Frame | null {
  if (!filter || filter.dataset !== index) return null;
  const frame = wholeFrame(entry);
  if (!hasColumn(frame, filter.key)) return null;
  const allowed = new Set(filter.allowed);
  const values = columnValues(frame, filter.key);
  return { entry, rows: frame.rows.filter((_r, i) => allowed.has(values[i])) };
}

/** Every visible dataset's draw groups and legend. `shown(entry, index)`
 * returns the rows to draw, or null for all of them. */
export function layoutPoints(
  entries: DatasetEntry[],
  options: LegendOptions,
  palette: string[],
  shown: ((entry: DatasetEntry, index: number) => Frame | null) | null = null,
): MapLayout {
  const visible = visibleEntries(entries);
  const multi = visible.length > 1;
  const sectioned = visible.some(([e]) => columnKey(e, e.symbol_by) !== null);
  const datasets: DatasetLayout[] = [];
  const sections: LegendSection[] = [];
  const rowOrder: string[] = [];
  let paletteOffset = 0;
  const used = new Set<string>();
  for (const [entry, index] of visible) {
    const filtered = shown ? shown(entry, index) : null;
    const rows = filtered ?? wholeFrame(entry);
    let layout: DatasetLayout;
    if (columnKey(entry, entry.symbol_by) !== null) {
      layout = attributeLayout(entry, index, rows, filtered !== null, palette, multi, options);
      sections.push(...layout.sections);
    } else {
      [layout, paletteOffset] = plainLayout(entry, index, rows, palette, paletteOffset, multi, used, options);
      rowOrder.push(...layout.rows.map((r) => r.label));
      if (sectioned && layout.rows.length) {
        sections.push({
          title: options.section_titles ? entry.name : "",
          rows: layout.rows.map((r): LegendSectionRow => ({ label: r.label, style: r.style, depth: 0 })),
        });
      }
    }
    splitOpen(layout);
    datasets.push(layout);
  }
  return {
    datasets,
    sections: sectioned ? sections : null,
    rowOrder: sectioned ? null : rowOrder,
    openNote: openNote(datasets, options),
  };
}

// ---------------------------------------------------------------- warnings

/** The legend warning PyMappr shows in the status bar, or null: forced
 * nesting on crossed columns, or a symbol column needing more shapes than
 * stay legible. `visible` are the drawn datasets' entries. */
export function legendWarning(visible: DatasetEntry[], options: LegendOptions): string | null {
  if (options.hierarchy === "always") {
    for (const entry of visible) {
      const colorKey = columnKey(entry, entry.color_by);
      const symbolKey = columnKey(entry, entry.symbol_by);
      if (symbolKey === null || colorKey === null) continue;
      if (resolveNesting(wholeFrame(entry), colorKey, symbolKey, "auto")) continue;
      return (
        `${entry.name}: “${entry.symbol_by}” does not nest inside “${entry.color_by}”, so each ` +
        "shape is listed under the first colour it appears in. Set Hierarchy to Auto for two independent keys."
      );
    }
  }
  let worst = 0;
  let worstEntry: DatasetEntry | null = null;
  for (const entry of visible) {
    const symbolKey = columnKey(entry, entry.symbol_by);
    if (symbolKey === null) continue;
    const load = markerLoad(wholeFrame(entry), columnKey(entry, entry.color_by), symbolKey, options.hierarchy);
    if (load > worst) {
      worst = load;
      worstEntry = entry;
    }
  }
  if (worst > LEGIBLE_MARKER_LIMIT && worstEntry !== null) {
    return (
      `${worstEntry.name}: “${worstEntry.symbol_by}” needs ${worst} shapes, more than the ` +
      `${LEGIBLE_MARKER_LIMIT} that stay easy to tell apart. Consider a Color by column that groups them, ` +
      "or filtering to fewer values."
    );
  }
  return null;
}

/** When the palette changes to one with white in it while points are
 * outlined in white, PyMappr switches the outline to black. Returns the new
 * point edge and the status note, or null when nothing changes. */
export function paletteOutlineSwitch(
  palette: string,
  edge: { color: string; width: number },
): { edge: { color: string; width: number }; status: string } | null {
  if (paletteFor(palette).includes("#ffffff") && ["#ffffff", "white"].includes(edge.color.toLowerCase())) {
    return {
      edge: { color: "#000000", width: edge.width },
      status: "Point outline set to black so white points stay visible.",
    };
  }
  return null;
}

/** The status line after a filter change (PyMappr's on_filter). */
export function filterStatus(entry: DatasetEntry, shown: number): string {
  const total = entry.rows.length;
  return shown === total
    ? `Showing all ${total} points of ${entry.name}.`
    : `Filter: showing ${shown} of ${total} points of ${entry.name}.`;
}

// ---------------------------------------------------------------- the whole map

export type Symbology = {
  /** The legend options as drawn: the title defaulted. */
  options: LegendOptions;
  layout: MapLayout;
  /** Draw groups in draw order (open symbols last), with their dataset. */
  groups: (DrawGroup & { dataset: number })[];
  /** Per dataset, per row: the style the point is drawn with, or null when
   * it is not drawn (dataset hidden or the row filtered out). */
  points: (PointStyle | null)[][];
  /** What the legend draws, row by row. */
  legend: DrawnLegend;
  /** The legend warning for the status bar, or null. */
  warning: string | null;
};

/** Style every point and build the legend for a project, as PyMappr's
 * `_push_points` does. */
export function symbology(state: ProjectState, filter: PointFilter | null = null): Symbology {
  const options = withDefaultTitle(state.datasets, state.legend);
  const layout = layoutPoints(state.datasets, options, paletteFor(state.map.palette), (entry, index) =>
    filteredRows(entry, index, filter),
  );
  const groups = layoutGroups(layout);
  const points: (PointStyle | null)[][] = state.datasets.map((d) => d.rows.map(() => null));
  for (const group of groups) for (const row of group.rows) points[group.dataset][row] = group.style;
  return {
    options,
    layout,
    groups,
    points,
    legend: drawnLegend(layout, options),
    warning: legendWarning(
      layout.datasets.map((d) => d.entry),
      options,
    ),
  };
}

// ---------------------------------------------------------------- legend editor

export type EditorRow = { key: string; value: string; style: PointStyle; depth: number };

/** The dataset's legend rows for the row editor, in the order the legend
 * draws them: groups, or colour values, symbol values or nested pairs. */
export function editorRows(
  entry: DatasetEntry,
  options: LegendOptions,
  palette: string[],
  paletteOffset = 0,
): EditorRow[] {
  const frame = wholeFrame(entry);
  const colorKey = columnKey(entry, entry.color_by);
  const symbolKey = columnKey(entry, entry.symbol_by);
  if (symbolKey === null) {
    return ordered(
      Object.entries(groupStyles(entry, palette, paletteOffset)).map(([label, style]) => ({
        key: rowKey("group", label),
        value: label,
        style,
        depth: 0,
      })),
      entry,
    );
  }
  const [colorMap, symbolMap] = attributeStyleMaps(frame, colorKey, symbolKey, options.hierarchy, palette);
  if (resolveNesting(frame, colorKey, symbolKey, options.hierarchy)) {
    const owner = ownerMap(frame, symbolKey, colorKey as string);
    const rows: EditorRow[] = [];
    for (const [value, color] of colorMap) {
      rows.push({ key: rowKey("color", value), value, style: pointStyle({ color, marker: "Circle" }), depth: 0 });
      rows.push(
        ...ordered(
          [...symbolMap.keys()]
            .filter((kid) => (owner.get(kid) ?? "") === value)
            .map((kid) => ({
              key: rowKey("pair", value, kid),
              value: kid,
              style: pointStyle({ color, marker: symbolMap.get(kid) as string }),
              depth: 1,
            })),
          entry,
        ),
      );
    }
    return ordered(rows, entry, true);
  }
  return [
    ...ordered(
      [...colorMap].map(([value, color]) => ({
        key: rowKey("color", value),
        value,
        style: pointStyle({ color, marker: "Circle" }),
        depth: 0,
      })),
      entry,
    ),
    ...ordered(
      [...symbolMap].map(([value, marker]) => ({
        key: rowKey("symbol", value),
        value,
        style: pointStyle({ color: options.symbol_swatch_color, marker }),
        depth: 0,
      })),
      entry,
    ),
  ];
}

function ordered(rows: EditorRow[], entry: DatasetEntry, blocks = false): EditorRow[] {
  const position = (key: string) => manualOrder(overrideOf(entry, key));
  const byPosition = <T>(items: T[], keyOf: (item: T) => string) =>
    items
      .map((item, i) => ({ item, i, p: position(keyOf(item)) }))
      .sort((a, b) => a.p - b.p || a.i - b.i)
      .map((x) => x.item);
  if (!blocks) return byPosition(rows, (r) => r.key);
  const grouped: EditorRow[][] = [];
  for (const row of rows) {
    if (row.depth === 0) grouped.push([row]);
    else if (grouped.length) grouped[grouped.length - 1].push(row);
  }
  return byPosition(grouped, (block) => block[0].key).flat();
}

/** The editor's palette offset for a dataset: where its colours start on
 * the map, which depends on the datasets drawn before it. */
export function editorPaletteOffset(state: ProjectState, datasetIndex: number): number {
  const options = withDefaultTitle(state.datasets, state.legend);
  const layout = layoutPoints(state.datasets, options, paletteFor(state.map.palette));
  return layout.datasets.find((d) => d.index === datasetIndex)?.paletteOffset ?? 0;
}
