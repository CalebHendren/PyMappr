// Figure layout: where the map box (matplotlib's axes) sits in the figure,
// on screen and when printed. Units are whatever the caller draws in: CSS
// pixels on screen, points in an export. PyMappr keeps the tick-label
// gutters at their on-screen size in inches and scales the map box to the
// print width (pymappr/renderer/view.py export_geometry).
import type { Rect } from "./api";
import { MARGINS_PLAIN, MARGINS_WITH_TICKS, PORTRAIT_ASPECT, SCREEN_DPI } from "./styles";

export type Figure = {
  /** Figure size in drawing units. */
  w: number;
  h: number;
  /** Drawing units per typographic point. */
  perPt: number;
  /** The map box (axes) in drawing units, from the figure's top-left. */
  box: Rect;
  /** Portrait maps leave a mat around a narrower box. */
  mat: boolean;
  /** Raster pixels per inch: text is measured and snapped at this dpi, as
   * matplotlib does when it draws at it. */
  dpi: number;
  /** A vector export: text stays editable text, laid out with matplotlib's
   * vector (unhinted) metrics. */
  vector?: boolean;
};

/** Raster pixels per figure unit. */
export function pxPerUnit(fig: Figure): number {
  return fig.dpi / (72 * fig.perPt);
}

/** Whether the graticule tick labels need gutters. */
export function hasTicks(graticule: string, hideLabels: boolean, globe: boolean): boolean {
  return graticule !== "Off" && !hideLabels && !globe;
}

/** The on-screen figure filling a canvas of `w`×`h` CSS pixels. */
export function screenFigure(w: number, h: number, ticks: boolean, portrait: boolean): Figure {
  const [l, b, r, t] = ticks ? MARGINS_WITH_TICKS : MARGINS_PLAIN;
  let box: Rect = { x: l * w, y: (1 - t) * h, w: (r - l) * w, h: (t - b) * h };
  if (portrait) {
    // Shrink the long side to the portrait ratio and centre the box.
    const want = PORTRAIT_ASPECT;
    if (box.w / box.h > want) {
      const nw = box.h * want;
      box = { ...box, x: box.x + (box.w - nw) / 2, w: nw };
    } else {
      const nh = box.w / want;
      box = { ...box, y: box.y + (box.h - nh) / 2, h: nh };
    }
  }
  return { w, h, perPt: SCREEN_DPI / 72, box, mat: portrait, dpi: SCREEN_DPI };
}

/** PyMappr caps an exported figure at 25 cm tall. */
const MAX_HEIGHT_CM = 25;

/** The printed figure, in points, for a print width in cm (null = as on
 * screen): the map box is scaled to fill the width while the gutters keep
 * their on-screen inches; portrait mats are cropped off. `dpi` is the raster
 * resolution it is drawn at (vector exports: 72, with `vector`). */
export function printFigure(screen: Figure, widthCm: number | null, dpi = 72, vector = false): Figure {
  const ptPerScreenPx = 72 / SCREEN_DPI;
  // Gutters around the box, in points (screen px at 100 dpi -> inches -> pt).
  const left = screen.mat ? 0 : screen.box.x * ptPerScreenPx;
  const top = screen.mat ? 0 : screen.box.y * ptPerScreenPx;
  const right = screen.mat ? 0 : (screen.w - screen.box.x - screen.box.w) * ptPerScreenPx;
  const bottom = screen.mat ? 0 : (screen.h - screen.box.y - screen.box.h) * ptPerScreenPx;
  // A cropped portrait figure keeps a hairline of white around the frame.
  const aspect = screen.box.h / screen.box.w;
  const totalW = widthCm === null ? (screen.mat ? screen.box.w : screen.w) * ptPerScreenPx : (widthCm / 2.54) * 72;
  let boxW = totalW - left - right;
  let boxH = boxW * aspect;
  const maxH = (MAX_HEIGHT_CM / 2.54) * 72;
  if (boxH + top + bottom > maxH) {
    boxH = maxH - top - bottom;
    boxW = boxH / aspect;
  }
  return {
    w: boxW + left + right,
    h: boxH + top + bottom,
    perPt: 1,
    box: { x: left, y: top, w: boxW, h: boxH },
    mat: false,
    dpi,
    vector,
  };
}

/** Pixel width of a printed figure at `dpi`. */
export function printPixels(fig: Figure, dpi: number): { w: number; h: number } {
  return { w: Math.max(1, Math.round((fig.w / 72) * dpi)), h: Math.max(1, Math.round((fig.h / 72) * dpi)) };
}

/** A box `w`×`h` (units) placed in a corner of `box` with a pad given as a
 * fraction of the box, matplotlib-style. */
export function cornerPlace(box: Rect, corner: string, w: number, h: number, pad: number): { x: number; y: number } {
  const right = corner.includes("right");
  const upper = corner.includes("upper");
  return {
    x: right ? box.x + box.w * (1 - pad) - w : box.x + box.w * pad,
    y: upper ? box.y + box.h * pad : box.y + box.h * (1 - pad) - h,
  };
}

/** Map units (SVG coords) to figure units. */
export function mapToFigure(view: Rect, box: Rect, x: number, y: number): [number, number] {
  return [box.x + ((x - view.x) / view.w) * box.w, box.y + ((y - view.y) / view.h) * box.h];
}

/** Figure units to map units. */
export function figureToMap(view: Rect, box: Rect, fx: number, fy: number): [number, number] {
  return [view.x + ((fx - box.x) / box.w) * view.w, view.y + ((fy - box.y) / box.h) * view.h];
}

/** Convert between the project's matplotlib limits (y up) and SVG views. */
export function viewFromLimits(xlim: [number, number], ylim: [number, number]): Rect {
  const [x0, x1] = [Math.min(...xlim), Math.max(...xlim)];
  const [y0, y1] = [Math.min(...ylim), Math.max(...ylim)];
  return { x: x0, y: -y1, w: x1 - x0, h: y1 - y0 };
}

export function limitsFromView(v: Rect): { xlim: [number, number]; ylim: [number, number] } {
  return { xlim: [v.x, v.x + v.w], ylim: [-(v.y + v.h), -v.y] };
}

/** Grow or shrink a view about its centre to the box's aspect (h / w). */
export function fitAspect(v: Rect, aspect: number): Rect {
  if (v.h / v.w < aspect) {
    const h = v.w * aspect;
    return { ...v, y: v.y + v.h / 2 - h / 2, h };
  }
  const w = v.h / aspect;
  return { ...v, x: v.x + v.w / 2 - w / 2, w };
}
