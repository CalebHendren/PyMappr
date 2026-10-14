// What matplotlib's "best" legend placement keeps clear of (legend.py
// `_auto_legend_data`): every artist on the map axes. Texts and Rectangle
// patches are boxes, other patches and Line2Ds are vertex lists, and
// collections count by their offsets. Here: the place labels, the Natural
// Earth markers, the scale bar's bars and labels, the compass and the
// inset's extent box on the map. All in figure units.
import type { Rect, RenderedInset, RenderedMap, ScaleBar } from "./api";
import { compassGeometry } from "./compass";
import type { Figure } from "./layout";
import { mapToFigure, pxPerUnit } from "./layout";
import type { MapSettings } from "./model";
import { type HAlign, type TextFont, type VAlign, placeText, textShape } from "./mpltext.svelte";
import { LABEL_STYLES, SCALE_BAR } from "./styles";

export type Obstacles = { rects: Rect[]; lines: [number, number][][]; points: [number, number][] };

/** A text's box (matplotlib's window extent) in figure units, or null
 * until it has been measured. */
export function textBox(fig: Figure, text: string, x: number, y: number, font: TextFont, ha: HAlign, va: VAlign): Rect | null {
  const shape = textShape(text, font, fig.dpi, fig.vector ? "path" : "agg");
  if (!shape) return null;
  const k = pxPerUnit(fig);
  const b = placeText(shape, font.size, fig.dpi, ha, va).box;
  return { x: x + b.x / k, y: y + b.y / k, w: b.w / k, h: b.h / k };
}

/** The vertices of an SVG path made of M/L/Z commands (Z repeats the
 * subpath's first vertex, as a closed matplotlib path does). */
function pathVertices(d: string): [number, number][][] {
  const out: [number, number][][] = [];
  let cur: [number, number][] = [];
  for (const m of d.matchAll(/([MLZ])([^MLZ]*)/gi)) {
    const nums = m[2].trim().split(/[\s,]+/).filter(Boolean).map(Number);
    const cmd = m[1].toUpperCase();
    if (cmd === "M") {
      if (cur.length) out.push(cur);
      cur = [];
    }
    if (cmd === "Z") {
      if (cur.length) cur.push(cur[0]);
      continue;
    }
    for (let i = 0; i + 1 < nums.length; i += 2) cur.push([nums[i], nums[i + 1]]);
  }
  if (cur.length) out.push(cur);
  return out;
}

export function legendObstacles(args: {
  fig: Figure;
  view: Rect;
  map: RenderedMap;
  settings: MapSettings;
  scaleBar: ScaleBar | null;
  inset: RenderedInset | null;
  labelOffsets: Record<string, [number, number]>;
}): Obstacles {
  const { fig, view, map, settings, scaleBar, inset, labelOffsets } = args;
  const box = fig.box;
  const toFig = (x: number, y: number) => mapToFigure(view, box, x, y);
  const rects: Rect[] = [];
  const lines: [number, number][][] = [];
  const points: [number, number][] = map.markers.map((m) => toFig(m.x, m.y));

  for (const l of map.labels) {
    const s = LABEL_STYLES[l.layer] ?? LABEL_STYLES.states;
    const off = labelOffsets[`${l.layer}|${l.text}`] ?? [0, 0];
    const [fx, fy] = toFig(l.x + off[0], l.y + off[1]);
    const font = { size: s.size * l.fontScale, bold: !!s.bold, italic: !!s.italic, family: "" };
    const r = textBox(fig, l.text, fx, fy, font, "center", l.va === "bottom" ? "bottom" : "center");
    if (r) rects.push(r);
  }

  if (scaleBar && settings.scale_bar.show) {
    const sb = settings.scale_bar;
    const fy = (f: number) => box.y + (1 - f) * box.h;
    scaleBar.bars.forEach((bar, bi) => {
      const n = sb.style === "segmented" ? bar.segments : 1;
      for (let si = 0; si < n; si++) {
        rects.push({ x: box.x + (bar.x + (bar.width * si) / n) * box.w, y: fy(bar.y + SCALE_BAR.height), w: (bar.width / n) * box.w, h: SCALE_BAR.height * box.h });
      }
      const above = bi === 0;
      const y = fy(above ? bar.y + SCALE_BAR.height + SCALE_BAR.labelGap : bar.y - SCALE_BAR.labelGap);
      const r = textBox(fig, bar.label, box.x + (bar.x + bar.width / 2) * box.w, y, { size: sb.fontsize, bold: false, italic: false, family: "" }, "center", above ? "bottom" : "top");
      if (r) rects.push(r);
    });
  }

  const compass = compassGeometry(fig, settings.compass_options);
  if (compass) {
    const r = textBox(fig, "N", compass.label[0], compass.label[1], compass.font, "center", "center");
    if (r && compass.arrow) {
      const [x0, y0, x1, y1] = compass.arrow.extent;
      const left = Math.min(r.x, x0);
      const top = Math.min(r.y, y0);
      rects.push({ x: left, y: top, w: Math.max(r.x + r.w, x1) - left, h: Math.max(r.y + r.h, y1) - top });
    } else if (r) rects.push(r);
    if (compass.tri) lines.push([...compass.tri, compass.tri[0]]);
  }

  if (inset && settings.inset.show && settings.inset.box && inset.box.on === "map" && inset.box.d) {
    for (const part of pathVertices(inset.box.d)) lines.push(part.map(([x, y]) => toFig(x, y)));
  }
  return { rects, lines, points };
}
