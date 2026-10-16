// Where everything in the legend goes, worked out the way matplotlib lays a
// legend out (matplotlib/legend.py `_init_legend_box`, offsetbox.py's
// HPacker/VPacker/TextArea, `_get_anchored_bbox`, `_find_best_position`).
// Pure: text is measured through the `measure` function passed in, so the
// tests can feed matplotlib's own metrics and compare positions.
//
// Units are points. The result is in SVG coordinates: x right and y DOWN
// from the top-left corner of the map box (`boxPt`).

import type { LegendOptions } from "../../model";
import type { DrawnLegend, DrawnLegendRow } from "../../legend";
import { padFor } from "../../legend";
import { markerPaint, type PointStyle } from "../../symbology";
import { markerPathAt, markerShape } from "../../markers";

export type FontSpec = {
  /** Points. */
  size: number;
  bold: boolean;
  italic: boolean;
  /** LegendOptions.font_family: "", "sans-serif", "serif" or "monospace". */
  family: string;
};

/** Text metrics in points, as matplotlib's renderer reports them: the ink
 * width (leading spaces count), the ink height including the descent, and
 * the descent below the baseline. */
export type TextMetrics = { width: number; height: number; descent: number };

export type Measure = (text: string, font: FontSpec) => TextMetrics;

/** A font's line extent in points: its typographic ascent and descent
 * (OS/2 sTypoAscender / sTypoDescender), which matplotlib 3.11 lays single
 * lines of text out with. */
export type FontExtent = (font: FontSpec) => { ascent: number; descent: number };

/** sTypoAscender and -sTypoDescender per em of the faces in FONT_STACKS,
 * [regular, italic, bold, bold italic]. */
const TYPO_METRICS: Record<string, [number, number][]> = {
  arial: [
    [1491, 431],
    [1491, 425],
    [1491, 431],
    [1491, 431],
  ],
  times: [
    [1420, 442],
    [1422, 442],
    [1387, 442],
    [1387, 442],
  ],
  courier: [
    [1255, 386],
    [1255, 386],
    [1297, 428],
    [1297, 428],
  ],
};

/** The extent of the fonts RustyMappr draws with (Arial, Times New Roman,
 * Courier New). */
export const fontExtent: FontExtent = (font) => {
  const face = font.family === "serif" ? "times" : font.family === "monospace" ? "courier" : "arial";
  const [ascent, descent] = TYPO_METRICS[face][(font.bold ? 2 : 0) + (font.italic ? 1 : 0)];
  return { ascent: (ascent / 2048) * font.size, descent: (descent / 2048) * font.size };
};

/** The extent of matplotlib's DejaVu faces (Sans, Serif and Sans Mono
 * share it), which PyMappr's legend is laid out with. */
export const dejaVuExtent: FontExtent = (font) => ({
  ascent: (1556 / 2048) * font.size,
  descent: (492 / 2048) * font.size,
});

/** The font each LegendOptions.font_family draws with. Real font names, so
 * the screen and a rasterised export (resvg) pick the same faces. */
export const FONT_STACKS: Record<string, string> = {
  "": "Arial, Helvetica, sans-serif",
  "sans-serif": "Arial, Helvetica, sans-serif",
  serif: "'Times New Roman', Times, serif",
  monospace: "'Courier New', Courier, monospace",
};

/** matplotlib's own faces (DejaVu, shipped in matplotlib's mpl-data/fonts).
 * With these loaded in the page and the exporter, and DEJAVU_FONTS passed
 * to the legend, its geometry is PyMappr's. */
export const DEJAVU_STACKS: Record<string, string> = {
  "": "'DejaVu Sans', sans-serif",
  "sans-serif": "'DejaVu Sans', sans-serif",
  serif: "'DejaVu Serif', serif",
  monospace: "'DejaVu Sans Mono', monospace",
};

/** The faces a legend draws with: CSS stacks per font_family and their
 * line extent. */
export type FontSet = { stacks: Record<string, string>; extent: FontExtent };

export function fontStack(family: string, stacks: Record<string, string> = FONT_STACKS): string {
  return stacks[family] ?? stacks[""];
}

/** A Measure backed by a canvas, using the fonts in `stacks`. */
export function canvasMeasure(stacks: Record<string, string> = FONT_STACKS): Measure {
  const context = document.createElement("canvas").getContext("2d");
  const cache = new Map<string, TextMetrics>();
  const SCALE = 100;
  return (text, font) => {
    const key = `${font.size}|${font.bold}|${font.italic}|${font.family}|${text}`;
    const hit = cache.get(key);
    if (hit) return hit;
    let metrics: TextMetrics = { width: 0, height: 0, descent: 0 };
    if (context && text.trim()) {
      context.font = `${font.italic ? "italic " : ""}${font.bold ? "bold " : ""}${SCALE}px ${fontStack(font.family, stacks)}`;
      const m = context.measureText(text);
      const k = font.size / SCALE;
      const inkStart = -m.actualBoundingBoxLeft;
      // A leading space puts the box's left edge at the pen's start, as
      // FreeType's string box does; otherwise the ink starts it.
      const left = /^\s/.test(text) ? Math.min(0, inkStart) : inkStart;
      metrics = {
        width: Math.max(m.actualBoundingBoxRight - left, 0) * k,
        height: (m.actualBoundingBoxAscent + m.actualBoundingBoxDescent) * k,
        descent: m.actualBoundingBoxDescent * k,
      };
    }
    cache.set(key, metrics);
    return metrics;
  };
}

export type Rect = { x: number; y: number; w: number; h: number };

/** A scale bar or inset sharing the legend's corner: the legend sits beyond
 * it. `frac` is the axes fraction (from the bottom) of its far edge,
 * `liftPt` an extra lift in points (PyMappr's `_scale_bar_clear` /
 * `_inset_clear`). */
export type LegendClearance = { corner: string; frac: number; liftPt?: number };

export type LegendInputs = {
  legend: DrawnLegend;
  options: LegendOptions;
  /** The map box in points. */
  boxPt: { w: number; h: number };
  measure: Measure;
  /** The fonts' line extent; RustyMappr's fonts by default. */
  fontExtent?: FontExtent;
  /** Swatch area (pt²) for a row; the row's own area by default. */
  markerSize?: (row: DrawnLegendRow) => number;
  /** The points on the map, in the same coordinates, for "best". */
  pointsPt?: [number, number][];
  /** Other boxes for "best" to keep clear of (scale bar, inset…). */
  avoidPt?: Rect[];
  /** Other shapes "best" keeps clear of, as vertex lists (a closed shape
   * repeats its first vertex). */
  linesPt?: [number, number][][];
  clear?: LegendClearance | null;
  /** The point outline, which filled swatches share with the map. */
  pointEdge?: { color: string; width: number };
  /** Raster pixels per point (an underline sits at least a pixel below its
   * text); 100 dpi by default. */
  pxPerPt?: number;
};

export type PlacedText = {
  text: string;
  /** Left end of the baseline. */
  x: number;
  y: number;
  font: FontSpec;
  color: string;
  /** The text's box (matplotlib's window extent). */
  box: Rect;
  underline: { x1: number; x2: number; y: number; width: number } | null;
};

export type PlacedMarker = {
  cx: number;
  cy: number;
  /** Marker size in points (√area × marker_scale, at least 2 × scale). */
  size: number;
  style: PointStyle;
  d: string;
  face: string;
  edge: string;
  edgeWidth: number;
  join: "miter" | "round" | "bevel";
};

export type LegendLayout = {
  /** The legend's box: the frame, padding included. */
  box: Rect;
  /** Frame outline (rounded corners included) and its shadow, or null. */
  frame: { d: string; fill: string; stroke: string; alpha: number; width: number; shadow: { d: string; fill: string } | null } | null;
  title: PlacedText | null;
  rows: { text: PlacedText; marker: PlacedMarker | null }[];
  /** The lower-left corner as axes fractions (y up), the form a dragged
   * legend's `anchor` takes. */
  anchor: [number, number];
  /** The matplotlib location code used (0 when anchored). */
  location: number;
};

const HANDLE_HEIGHT = 0.7;
const BORDER_AXES_PAD = 0.5;

/** Location names to matplotlib codes. */
export const LOCATION_CODES: Record<string, number> = {
  best: 0,
  "upper right": 1,
  "upper left": 2,
  "lower left": 3,
  "lower right": 4,
  right: 5,
  "center left": 6,
  "center right": 7,
  "lower center": 8,
  "upper center": 9,
  center: 10,
};

/** Anchor coefficients (x, y up) for each location code. */
const ANCHORS: [number, number][] = [
  [0, 0],
  [1, 1],
  [0, 1],
  [0, 0],
  [1, 0],
  [1, 0.5],
  [0, 0.5],
  [1, 0.5],
  [0.5, 0],
  [0.5, 1],
  [0.5, 0.5],
];

type Box = { x0: number; y0: number; x1: number; y1: number };

/** Lower-left of a w×h box anchored at `code` inside `parent` shrunk by
 * `pad` (matplotlib's `_get_anchored_bbox`; y up). */
function anchored(code: number, w: number, h: number, parent: Box, pad: number): [number, number] {
  const [cx, cy] = ANCHORS[code];
  const l = parent.x0 + pad;
  const b = parent.y0 + pad;
  const cw = parent.x1 - parent.x0 - 2 * pad;
  const ch = parent.y1 - parent.y0 - 2 * pad;
  return [l + cx * (cw - w), b + cy * (ch - h)];
}

function textFont(options: LegendOptions, header: boolean, size: number): FontSpec {
  return {
    size,
    bold: header ? options.title_bold : options.label_bold,
    italic: header ? options.title_italic : options.label_italic,
    family: options.font_family ?? "",
  };
}

/** A TextArea's box (matplotlib offsetbox): width, height and descent,
 * and the text's own (layout) height. */
function textArea(measure: Measure, extent: FontExtent, text: string, font: FontSpec) {
  const m = text ? measure(text, font) : { width: 0, height: 0, descent: 0 };
  const line = extent(font);
  const a = Math.max(m.height - m.descent, line.ascent);
  const d = Math.max(m.descent, line.descent);
  const lp = measure("lp", font);
  return { w: m.width, h: Math.max(lp.height - lp.descent, a) + d, d, layoutH: a + d };
}

function underline(box: Rect, font: FontSpec, pxPerPt: number): PlacedText["underline"] {
  // PyMappr strokes it a tenth of the text's height (at least a pixel)
  // below the text box, max(size / 11, 0.6) points thick.
  const y = box.y + box.h + Math.max(box.h * 0.1, 1 / pxPerPt);
  return { x1: box.x, x2: box.x + box.w, y, width: Math.max(font.size / 11, 0.6) };
}

/** Lay the legend out. Returns null when it is not drawn. */
export function legendLayout(inputs: LegendInputs): LegendLayout | null {
  const { legend, options, boxPt } = inputs;
  const measure = inputs.measure;
  const extent = inputs.fontExtent ?? fontExtent;
  if (!legend.visible) return null;
  const f = Number(options.fontsize);
  const handleLength = Math.max(Number(options.handle_length), 0) * f;
  const textPad = Math.max(padFor(options, legend.sectioned), 0) * f;
  const labelSep = Math.max(Number(options.label_spacing), 0) * f;
  const columnSep = Math.max(Number(options.column_spacing), 0) * f;
  const borderPad = Math.max(Number(options.border_pad), 0) * f;
  const markerScale = Math.max(Number(options.marker_scale), 0.1);
  const handleH = HANDLE_HEIGHT * f;

  // Each entry: handle box beside its text, aligned on the baseline.
  const items = legend.rows.map((row) => {
    const font = textFont(options, row.header, f);
    const area = textArea(measure, extent, row.label, font);
    const above = Math.max(handleH, area.h - area.d);
    return { row, font, area, above, below: area.d, width: handleLength + textPad + area.w };
  });

  // np.array_split into columns, filled down each column first.
  const ncols = Math.max(Math.trunc(Number(options.columns)) || 1, 1);
  const columns: (typeof items)[] = [];
  const base = Math.floor(items.length / ncols);
  const extra = items.length % ncols;
  let start = 0;
  for (let c = 0; c < ncols; c++) {
    const size = base + (c < extra ? 1 : 0);
    if (size) columns.push(items.slice(start, start + size));
    start += size;
  }

  // Columns side by side, their first baselines level.
  type Column = { items: typeof items; tops: number[]; width: number; above: number; height: number; x: number };
  const cols: Column[] = [];
  let x = 0;
  for (const column of columns) {
    const tops: number[] = [];
    let y = 0;
    for (const item of column) {
      tops.push(y);
      y += item.above + item.below + labelSep;
    }
    const height = y - labelSep;
    const width = Math.max(...column.map((i) => i.width));
    cols.push({ items: column, tops, width, above: column[0].above, height, x });
    x += width + columnSep;
  }
  const handlesW = cols.length ? x - columnSep : 0;
  const handlesTop = cols.length ? Math.max(...cols.map((c) => c.above)) : 0;
  const handlesBottom = cols.length ? Math.max(...cols.map((c) => c.height - c.above)) : 0;
  const handlesH = handlesTop + handlesBottom;

  // Title over the entries.
  const titleFont = textFont(options, true, Number(options.title_fontsize));
  const titleArea = legend.title ? textArea(measure, extent, legend.title, titleFont) : null;
  const innerW = Math.max(handlesW, titleArea ? titleArea.w : 0);
  const innerH = (titleArea ? titleArea.h + labelSep : 0) + handlesH;
  const w = innerW + 2 * borderPad;
  const h = innerH + 2 * borderPad;
  const align = (width: number) =>
    options.title_align === "left" ? 0 : options.title_align === "right" ? innerW - width : (innerW - width) / 2;

  // Placement, in matplotlib's axes points (y up).
  const W = boxPt.w;
  const H = boxPt.h;
  const axes: Box = { x0: 0, y0: 0, x1: W, y1: H };
  const pad = BORDER_AXES_PAD * f;
  let code = LOCATION_CODES[options.location] ?? 0;
  let left: number;
  let bottom: number;
  if (options.anchor) {
    code = 0;
    left = options.anchor[0] * W;
    bottom = options.anchor[1] * H;
  } else if (inputs.clear && inputs.clear.corner === options.location) {
    const px = inputs.clear.corner.endsWith("left") ? 0 : W;
    const py = inputs.clear.frac * H + (inputs.clear.liftPt ?? 0);
    [left, bottom] = anchored(code, w, h, { x0: px, y0: py, x1: px, y1: py }, pad);
  } else if (code === 0) {
    [code, left, bottom] = bestPosition(w, h, axes, pad, inputs.pointsPt ?? [], inputs.avoidPt ?? [], H, inputs.linesPt ?? []);
  } else {
    [left, bottom] = anchored(code, w, h, axes, pad);
  }

  // Into SVG coordinates (y down).
  const box: Rect = { x: left, y: H - bottom - h, w, h };
  const innerX = box.x + borderPad;
  const innerY = box.y + borderPad;
  const placeText = (text: string, x0: number, top: number, area: ReturnType<typeof textArea>, font: FontSpec, color: string, under: boolean): PlacedText => {
    const baseline = top + (area.h - area.d);
    const textBox = { x: x0, y: baseline + area.d - area.layoutH, w: area.w, h: area.layoutH };
    return { text, x: x0, y: baseline, font, color, box: textBox, underline: under ? underline(textBox, font, inputs.pxPerPt ?? 100 / 72) : null };
  };

  const title =
    legend.title && titleArea
      ? placeText(legend.title, innerX + align(titleArea.w), innerY, titleArea, titleFont, options.title_color, legend.titleUnderline)
      : null;
  const handlesX = innerX + align(handlesW);
  const handlesY = innerY + (titleArea ? titleArea.h + labelSep : 0);
  const edge = inputs.pointEdge ?? { color: "#ffffff", width: 0.5 };
  const rows: LegendLayout["rows"] = [];
  for (const col of cols) {
    col.items.forEach((item, i) => {
      const top = handlesY + (handlesTop - col.above) + col.tops[i];
      const baseline = top + item.above;
      const text = placeText(
        item.row.label,
        handlesX + col.x + handleLength + textPad,
        baseline - (item.area.h - item.area.d),
        item.area,
        item.font,
        item.row.header ? options.title_color : options.label_color,
        item.row.underline,
      );
      let marker: PlacedMarker | null = null;
      const style = item.row.style;
      if (style) {
        const area = inputs.markerSize ? inputs.markerSize(item.row) : item.row.area;
        const size = Math.max(Math.sqrt(Math.max(area, 0)), 2) * markerScale;
        const cx = handlesX + col.x + handleLength / 2;
        const cy = baseline - handleH / 2;
        const paint = markerPaint(style, edge);
        marker = { cx, cy, size, style, d: markerPathAt(style.marker, size, cx, cy), ...paint, join: markerShape(style.marker).join };
      }
      rows.push({ text, marker });
    });
  }

  const frame = options.frame ? frameShape(box, options, f) : null;
  return {
    box,
    frame,
    title,
    rows,
    anchor: [W ? left / W : 0, H ? bottom / H : 0],
    location: code,
  };
}

function frameShape(box: Rect, options: LegendOptions, f: number): NonNullable<LegendLayout["frame"]> {
  const d = framePath(box, options.rounded ? 0.2 * f : 0);
  let shadow: { d: string; fill: string } | null = null;
  if (options.shadow) {
    // matplotlib's Shadow: 2 pt right, 2 pt down, 30% of the face colour.
    shadow = { d: framePath({ ...box, x: box.x + 2, y: box.y + 2 }, options.rounded ? 0.2 * f : 0), fill: darken(options.frame_color, 0.3) };
  }
  return {
    d,
    fill: options.frame_color,
    stroke: options.frame_edge_color,
    alpha: Number(options.frame_alpha),
    width: Math.max(Number(options.frame_width), 0),
    shadow,
  };
}

const n = (v: number) => String(Math.round(v * 1000) / 1000);

/** A box, its corners rounded as matplotlib's "round" box style does
 * (quadratic curves with the control point on the corner). */
export function framePath(r: Rect, radius: number): string {
  const x0 = r.x;
  const y0 = r.y;
  const x1 = r.x + r.w;
  const y1 = r.y + r.h;
  const dr = Math.min(radius, r.w / 2, r.h / 2);
  if (dr <= 0) return `M${n(x0)} ${n(y0)}H${n(x1)}V${n(y1)}H${n(x0)}Z`;
  return (
    `M${n(x0 + dr)} ${n(y0)}H${n(x1 - dr)}Q${n(x1)} ${n(y0)} ${n(x1)} ${n(y0 + dr)}` +
    `V${n(y1 - dr)}Q${n(x1)} ${n(y1)} ${n(x1 - dr)} ${n(y1)}` +
    `H${n(x0 + dr)}Q${n(x0)} ${n(y1)} ${n(x0)} ${n(y1 - dr)}` +
    `V${n(y0 + dr)}Q${n(x0)} ${n(y0)} ${n(x0 + dr)} ${n(y0)}Z`
  );
}

function darken(color: string, factor: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(color.trim());
  if (!m) return "#4d4d4d";
  const v = parseInt(m[1], 16);
  const c = [(v >> 16) & 255, (v >> 8) & 255, v & 255].map((x) => Math.round(x * factor));
  return "#" + c.map((x) => x.toString(16).padStart(2, "0")).join("");
}

/** matplotlib's segment_intersects_rectangle (_path.h). */
function segmentHitsBox(x1: number, y1: number, x2: number, y2: number, cx: number, cy: number, w: number, h: number): boolean {
  return (
    Math.abs(x1 + x2 - 2 * cx) < w + Math.abs(x1 - x2) &&
    Math.abs(y1 + y2 - 2 * cy) < h + Math.abs(y1 - y2) &&
    2 * Math.abs((x1 - cx) * (y1 - y2) - (y1 - cy) * (x1 - x2)) < w * Math.abs(y1 - y2) + h * Math.abs(x1 - x2)
  );
}

/** matplotlib's "best" (legend.py `_find_best_position`): the first
 * location with nothing in the way, else the least bad (ties to the lower
 * code). Badness counts the points inside, the boxes (texts, rectangles)
 * it overlaps, and for each other shape its vertices inside plus one if
 * an edge crosses it. */
function bestPosition(
  w: number,
  h: number,
  axes: Box,
  pad: number,
  points: [number, number][],
  avoid: Rect[],
  H: number,
  lines: [number, number][][] = [],
): [number, number, number] {
  let best: [number, number, number, number] | null = null;
  for (let code = 1; code < ANCHORS.length; code++) {
    const [l, b] = anchored(code, w, h, axes, pad);
    // To SVG y for the comparisons.
    const x0 = l;
    const x1 = l + w;
    const y0 = H - b - h;
    const y1 = H - b;
    let badness = 0;
    for (const [px, py] of points) if (x0 < px && px < x1 && y0 < py && py < y1) badness++;
    for (const r of avoid) if (x0 < r.x + r.w && r.x < x1 && y0 < r.y + r.h && r.y < y1) badness++;
    for (const line of lines) {
      for (const [px, py] of line) if (x0 < px && px < x1 && y0 < py && py < y1) badness++;
      const hit = line.some((p, i) => i > 0 && segmentHitsBox(line[i - 1][0], line[i - 1][1], p[0], p[1], (x0 + x1) / 2, (y0 + y1) / 2, w, h));
      if (hit) badness++;
    }
    if (badness === 0) return [code, l, b];
    if (best === null || badness < best[0]) best = [badness, code, l, b];
  }
  return [best![1], best![2], best![3]];
}

/** The `anchor` (axes fractions of the lower-left corner) for a legend box
 * dragged to `box` (SVG points) in a map box `boxPt`. */
export function anchorForBox(box: Rect, boxPt: { w: number; h: number }): [number, number] {
  return [boxPt.w ? box.x / boxPt.w : 0, boxPt.h ? (boxPt.h - box.y - box.h) / boxPt.h : 0];
}

/** The SVG font attributes for a placed text. */
export function fontAttrs(font: FontSpec, stacks: Record<string, string> = FONT_STACKS) {
  return {
    "font-family": fontStack(font.family, stacks),
    "font-size": font.size,
    "font-weight": font.bold ? "bold" : "normal",
    "font-style": font.italic ? "italic" : "normal",
  };
}

/** Arial / Times New Roman / Courier New: on every Windows machine and in
 * resvg's system fonts, so the screen and the export agree. */
export const SYSTEM_FONTS: FontSet = { stacks: FONT_STACKS, extent: fontExtent };
/** matplotlib's DejaVu faces: PyMappr's exact geometry, when loaded. */
export const DEJAVU_FONTS: FontSet = { stacks: DEJAVU_STACKS, extent: dejaVuExtent };
