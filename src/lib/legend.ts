// Legend content: the rows that describe the styled points, and the list of
// entries the legend draws. A port of PyMappr's pymappr/styling/legend.py
// and of the row-building half of pymappr/renderer/points.py (the plain and
// the sectioned legend). Drawing the rows is components/legend/.

import type { LegendOptions, RowOverride } from "./model";
import {
  type Frame,
  type MapLayout,
  type PointStyle,
  applyOverride,
  columnValues,
  layoutGroups,
  ownerMap,
  pointStyle,
  resolveNesting,
  rowKey,
} from "./symbology";

/** Shape-only swatch colour in a crossed key. */
export const NEUTRAL_MARKER_COLOR = "#555555";

/** Every location matplotlib accepts, as the Legend tab lists them. */
export const LEGEND_LOCATIONS = [
  "best",
  "upper right",
  "upper left",
  "lower left",
  "lower right",
  "upper center",
  "lower center",
  "center left",
  "center right",
  "center",
];

/** Display name -> stored value, as PyMappr's combo boxes. */
export const HIERARCHY_MODES: Record<string, string> = {
  "Auto (detect)": "auto",
  "Always nest": "always",
  "Never nest": "never",
};
export const ENTRY_ORDERS: Record<string, string> = {
  "As in data": "data",
  "A – Z": "az",
  "Z – A": "za",
  "Count, high to low": "count_desc",
  "Count, low to high": "count_asc",
  Manual: "manual",
};
export const COUNT_FORMATS: Record<string, string> = { "(12)": "(n)", "12": "n", "(12, 34%)": "(n, %)", "34%": "%" };
export const GROUP_SWATCHES: Record<string, string> = {
  Circle: "circle",
  "Match first child": "child",
  "No swatch": "none",
};
export const FONT_FAMILIES: Record<string, string> = {
  Default: "",
  "Sans-serif": "sans-serif",
  Serif: "serif",
  Monospace: "monospace",
};
export const TITLE_ALIGNMENTS: Record<string, string> = { Left: "left", Centre: "center", Right: "right" };

/** The legend half of the built-in Standard preset. */
export const PUBLICATION_LEGEND: Partial<LegendOptions> = {
  frame: true,
  frame_color: "#ffffff",
  frame_alpha: 1.0,
  frame_edge_color: "#000000",
  frame_width: 0.5,
  rounded: false,
  shadow: false,
  label_italic: true,
  fontsize: 9.0,
  title_fontsize: 10.0,
};

/** Count-based ordering needs the counts even when they are not shown. */
export function ordersByCount(options: LegendOptions): boolean {
  return options.order === "count_desc" || options.order === "count_asc";
}

/** The leading spaces that indent a row at `depth`. */
export function indentFor(options: LegendOptions, depth: number): string {
  return " ".repeat(Math.max(options.indent * (depth + 1), 0));
}

/** The gap between swatch and text, in font sizes: the set value, or the
 * kind's own (tighter for a sectioned key). */
export function padFor(options: LegendOptions, sectioned: boolean): number {
  if (options.handle_text_pad !== null && options.handle_text_pad !== undefined) return Number(options.handle_text_pad);
  return sectioned ? 0.4 : 0.8;
}

// --------------------------------------------------------------- overrides

/** A row's replacement text, or null to use the data value. */
export function overrideLabel(override: RowOverride | null | undefined): string | null {
  if (!override) return null;
  const label = override.label;
  return label ? String(label) : null;
}

export function isHidden(override: RowOverride | null | undefined): boolean {
  return Boolean(override && override.hidden);
}

const UNPLACED = 1 << 30;

/** Where a row sits under manual ordering; unplaced rows sort last. */
export function manualOrder(override: RowOverride | null | undefined): number {
  if (!override || override.order === null || override.order === undefined) return UNPLACED;
  const value: unknown = override.order;
  if (typeof value === "number") return Number.isFinite(value) ? Math.trunc(value) : UNPLACED;
  if (typeof value === "boolean") return Number(value);
  if (typeof value === "string" && /^\s*[-+]?\d+\s*$/.test(value)) return parseInt(value, 10);
  return UNPLACED;
}

// ------------------------------------------------------------------ counts

/** A tagged count key: "total", or kind + NUL + value(s). */
export type CountKey = string;

export function countKey(kind: "total" | "color" | "symbol" | "pair", ...parts: string[]): CountKey {
  return [kind, ...parts].join("\x00");
}

/** Point counts for legend rows, tagged by channel, over the drawn rows. */
export function legendCounts(frame: Frame, colorKey: string | null, symbolKey: string | null): Map<CountKey, number> {
  const counts = new Map<CountKey, number>();
  if (frame.rows.length === 0) return counts;
  counts.set(countKey("total"), frame.rows.length);
  const has = (key: string | null): key is string => key !== null && frame.entry.columns.includes(key);
  const add = (key: CountKey) => counts.set(key, (counts.get(key) ?? 0) + 1);
  if (has(colorKey)) for (const v of columnValues(frame, colorKey)) add(countKey("color", v));
  if (has(symbolKey)) for (const v of columnValues(frame, symbolKey)) add(countKey("symbol", v));
  if (has(colorKey) && has(symbolKey)) {
    const colors = columnValues(frame, colorKey);
    columnValues(frame, symbolKey).forEach((s, i) => add(countKey("pair", colors[i], s)));
  }
  return counts;
}

/** Python's `f"{x:.0f}"`: ties go to the even neighbour. */
function fixed0(x: number): string {
  const floor = Math.floor(x);
  const rounded = x - floor === 0.5 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(x);
  return String(rounded);
}

/** A label with its point count in one of COUNT_FORMATS. */
export function formatCount(label: string, n: number, total: number, fmt: string): string {
  const pct = total ? (100.0 * n) / total : 0.0;
  if (fmt === "n") return `${label} ${n}`;
  if (fmt === "(n, %)") return `${label} (${n}, ${fixed0(pct)}%)`;
  if (fmt === "%") return `${label} ${fixed0(pct)}%`;
  return `${label} (${n})`;
}

function legendLabel(
  value: string,
  counts: Map<CountKey, number>,
  key: CountKey,
  options: LegendOptions,
  override: RowOverride | null | undefined,
): string {
  const label = overrideLabel(override) || value || options.blank_label;
  const n = counts.get(key);
  if (!options.counts || n === undefined) return label;
  return formatCount(label, n, counts.get(countKey("total")) ?? 0, options.count_format);
}

// ----------------------------------------------------------------- ordering

/** Python's str.casefold, near enough for sorting names. */
export function casefold(text: string): string {
  return (text ?? "").toLowerCase().replace(/ß/g, "ss").replace(/ς/g, "σ");
}

const compare = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/** Sort legend row values: "az", "za", "count_desc", "count_asc"; anything
 * else keeps their order. Count ties fall back to the label. */
export function orderLabels(values: string[], order: string, countOf?: (value: string) => number): string[] {
  const items = [...values];
  if (order === "az") return items.sort((a, b) => compare(casefold(a), casefold(b)));
  if (order === "za") return items.sort((a, b) => compare(casefold(b), casefold(a)));
  if (order === "count_desc" || order === "count_asc") {
    const count = countOf ?? (() => 0);
    const sign = order === "count_desc" ? -1 : 1;
    return items.sort((a, b) => sign * count(a) - sign * count(b) || compare(casefold(a), casefold(b)));
  }
  return items;
}

function orderedRows(
  values: string[],
  options: LegendOptions,
  countOf: (value: string) => number,
  overrideOf: (value: string) => RowOverride | undefined,
): string[] {
  if (options.order === "manual") {
    const first = (v: string) => values.indexOf(v);
    return [...values].sort((a, b) => manualOrder(overrideOf(a)) - manualOrder(overrideOf(b)) || first(a) - first(b));
  }
  return orderLabels(values, options.order, countOf);
}

// ----------------------------------------------------------------- sections

/** A legend row; `depth` indents it beneath the row above, and a null style
 * takes no swatch. */
export type LegendSectionRow = { label: string; style: PointStyle | null; depth: number };
export type LegendSection = { title: string; rows: LegendSectionRow[] };

export type SectionInputs = {
  /** Values still shown under a filter; null = no filter. */
  shownColors?: Set<string> | null;
  shownSymbols?: Set<string> | null;
  counts?: Map<CountKey, number>;
  prefix?: string;
  options: LegendOptions;
  overrides?: Record<string, RowOverride>;
};

/** Legend sections for a dataset styled by a colour and a symbol column: one
 * nested key when the symbol column nests in the colour column, otherwise
 * two independent keys with neutral symbol swatches. */
export function legendSections(
  frame: Frame,
  colorKey: string | null,
  symbolKey: string | null,
  colorMap: Map<string, string>,
  symbolMap: Map<string, string>,
  colorLabel: string,
  symbolLabel: string,
  inputs: SectionInputs,
): LegendSection[] {
  const options = inputs.options;
  const all = inputs.overrides ?? {};
  const get = (key: string) => (Object.hasOwn(all, key) ? all[key] : undefined);
  const counts = inputs.counts ?? new Map();
  const prefix = inputs.prefix ?? "";
  const shownColors = inputs.shownColors ?? null;
  const shownSymbols = inputs.shownSymbols ?? null;
  if (resolveNesting(frame, colorKey, symbolKey, options.hierarchy)) {
    return nestedSections(frame, colorKey as string, symbolKey as string, colorMap, symbolMap, shownColors, shownSymbols, counts, prefix, colorLabel, symbolLabel, options, get);
  }
  return crossedSections(colorMap, symbolMap, shownColors, shownSymbols, counts, prefix, colorLabel, symbolLabel, options, get);
}

function groupSwatch(color: string, kids: string[], symbolMap: Map<string, string>, options: LegendOptions): PointStyle | null {
  const swatch: string = options.group_swatch;
  if (swatch === "none") return null;
  let marker = "Circle";
  // "child" is PyMappr's value; "first" is accepted as the same thing.
  if ((swatch === "child" || swatch === "first") && kids.length) marker = symbolMap.get(kids[0]) ?? "Circle";
  return pointStyle({ color, marker });
}

function nestedSections(
  frame: Frame,
  colorKey: string,
  symbolKey: string,
  colorMap: Map<string, string>,
  symbolMap: Map<string, string>,
  shownColors: Set<string> | null,
  shownSymbols: Set<string> | null,
  counts: Map<CountKey, number>,
  prefix: string,
  colorLabel: string,
  symbolLabel: string,
  options: LegendOptions,
  get: (key: string) => RowOverride | undefined,
): LegendSection[] {
  const owner = ownerMap(frame, symbolKey, colorKey);
  const children = new Map<string, string[]>([...colorMap.keys()].map((v) => [v, []]));
  for (const value of symbolMap.keys()) {
    if (shownSymbols === null || shownSymbols.has(value)) {
      const parent = owner.get(value) ?? "";
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent)!.push(value);
    }
  }
  const rows: LegendSectionRow[] = [];
  const parents = orderedRows(
    [...colorMap.keys()],
    options,
    (v) => counts.get(countKey("color", v)) ?? 0,
    (v) => get(rowKey("color", v)),
  );
  const filtering = shownSymbols !== null;
  for (const value of parents) {
    const color = colorMap.get(value) as string;
    const parent = get(rowKey("color", value));
    let kids = children.get(value) ?? [];
    if (shownColors !== null && !shownColors.has(value)) continue;
    if (!kids.length && filtering && !options.empty_groups) continue;
    kids = orderedRows(
      kids,
      options,
      (k) => counts.get(countKey("pair", value, k)) ?? 0,
      (k) => get(rowKey("pair", value, k)),
    );
    if (isHidden(parent)) continue;
    const visible = kids.filter((k) => !isHidden(get(rowKey("pair", value, k))));
    rows.push({
      label: legendLabel(value, counts, countKey("color", value), options, parent),
      style: applyOverride(groupSwatch(color, visible, symbolMap, options), parent),
      depth: 0,
    });
    for (const kid of visible) {
      const leaf = get(rowKey("pair", value, kid));
      rows.push({
        label: legendLabel(kid, counts, countKey("pair", value, kid), options, leaf),
        style: applyOverride(pointStyle({ color, marker: symbolMap.get(kid) as string }), leaf),
        depth: 1,
      });
    }
  }
  if (!rows.length) return [];
  return [{ title: sectionTitle(options, prefix, colorLabel, symbolLabel), rows }];
}

/** A section's heading, or "" with headings off (the dataset prefix goes
 * with it). */
export function sectionTitle(options: LegendOptions, prefix: string, ...parts: string[]): string {
  if (!options.section_titles) return "";
  const joined = parts.filter((p) => p).join(options.title_separator);
  return prefix + (joined || "Key");
}

function crossedSections(
  colorMap: Map<string, string>,
  symbolMap: Map<string, string>,
  shownColors: Set<string> | null,
  shownSymbols: Set<string> | null,
  counts: Map<CountKey, number>,
  prefix: string,
  colorLabel: string,
  symbolLabel: string,
  options: LegendOptions,
  get: (key: string) => RowOverride | undefined,
): LegendSection[] {
  const sections: LegendSection[] = [];
  const build = (
    source: Map<string, string>,
    kind: "color" | "symbol",
    shown: Set<string> | null,
    base: (v: string) => PointStyle,
    label: string,
  ) => {
    let picked = [...source.keys()].filter((v) => shown === null || shown.has(v));
    picked = orderedRows(
      picked,
      options,
      (v) => counts.get(countKey(kind, v)) ?? 0,
      (v) => get(rowKey(kind, v)),
    );
    const rows = picked
      .filter((v) => !isHidden(get(rowKey(kind, v))))
      .map((v) => ({
        label: legendLabel(v, counts, countKey(kind, v), options, get(rowKey(kind, v))),
        style: applyOverride(base(v), get(rowKey(kind, v))),
        depth: 0,
      }));
    if (rows.length) sections.push({ title: sectionTitle(options, prefix, label), rows });
  };
  if (colorMap.size) {
    build(colorMap, "color", shownColors, (v) => pointStyle({ color: colorMap.get(v) as string, marker: "Circle" }), colorLabel || "Color");
  }
  if (symbolMap.size) {
    build(
      symbolMap,
      "symbol",
      shownSymbols,
      (v) => pointStyle({ color: options.symbol_swatch_color, marker: symbolMap.get(v) as string }),
      symbolLabel || "Symbol",
    );
  }
  return sections;
}

// ------------------------------------------------------------ drawn legend

/** One row of the drawn legend. `header` rows (section titles, spacers and,
 * in a nested key, the group rows when bold) take the title's text style
 * at the label size; `area` is the swatch's matplotlib area (pt²), before
 * marker_scale. */
export type DrawnLegendRow = {
  label: string;
  style: PointStyle | null;
  area: number;
  header: boolean;
  underline: boolean;
};

export type DrawnLegend = {
  /** False when the legend is switched off or there are no points. */
  visible: boolean;
  /** The sectioned (Symbol by) legend, which has the tighter text pad. */
  sectioned: boolean;
  title: string | null;
  titleUnderline: boolean;
  rows: DrawnLegendRow[];
};

/** Swatch area of every row in the sectioned legend. */
export const SECTIONED_SWATCH_AREA = 45;

/** The rows the legend draws, as PyMappr's renderer builds them from the
 * layout (points.py `_update_legend` / `_draw_structured_legend`). */
export function drawnLegend(layout: MapLayout, options: LegendOptions): DrawnLegend {
  const groups = layoutGroups(layout);
  const title = options.show_title && options.title ? options.title : null;
  const legend: DrawnLegend = {
    visible: Boolean(options.show) && groups.length > 0,
    sectioned: layout.sections !== null,
    title,
    titleUnderline: Boolean(title && options.title_underline && title.trim()),
    rows: [],
  };
  const notes = layout.openNote ? [layout.openNote] : [];
  const row = (label: string, style: PointStyle | null, area: number, header: boolean): DrawnLegendRow => ({
    label,
    style,
    area,
    header,
    underline: (header ? options.title_underline : options.label_underline) && label.trim() !== "",
  });
  if (layout.sections === null) {
    const rank = new Map<string, number>();
    (layout.rowOrder ?? []).forEach((label, i) => rank.set(label, i));
    const shown = groups.filter((g) => rank.has(g.label));
    shown.sort((a, b) => (rank.get(a.label) as number) - (rank.get(b.label) as number));
    legend.rows = [...shown, ...notes].map((g) => row(g.label, g.style, g.style.size, false));
    return legend;
  }
  const sections: LegendSection[] = [...layout.sections];
  if (notes.length) sections.push({ title: "", rows: notes.map((n) => ({ label: n.label, style: n.style, depth: 0 })) });
  const rows: DrawnLegendRow[] = [];
  const spacer = () => rows.push(row(" ", null, 0, true));
  for (const { title: heading, rows: entries } of sections) {
    if (rows.length) spacer();
    if (heading) rows.push(row(heading, null, 0, true));
    const nested = entries.some((e) => e.depth);
    entries.forEach((entry, index) => {
      let header = false;
      if (nested && entry.depth === 0) {
        if (index && options.group_spacer) spacer();
        header = Boolean(options.bold_groups);
      }
      rows.push(row(indentFor(options, entry.depth) + entry.label, entry.style, SECTIONED_SWATCH_AREA, header));
    });
  }
  legend.rows = rows;
  return legend;
}
