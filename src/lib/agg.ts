// matplotlib's Agg renderer snaps straight-edged paths to the pixel grid
// (path_converters.h PathSnapper): a path whose segments are all horizontal
// or vertical, with at most 1024 vertices. These helpers apply that rule to
// SVG paths of move-to and line-to commands.
import { markerPathWith, markerShape } from "./markers";
import { snapPx } from "./mpltext.svelte";

type Pt = [number, number];

/** Subpaths of an SVG path made of M/L/H/V/Z commands (absolute). Z closes
 * back to the subpath's start. */
export function polylines(d: string): Pt[][] {
  const out: Pt[][] = [];
  let cur: Pt[] = [];
  for (const m of d.matchAll(/([MLHVZ])([^MLHVZ]*)/gi)) {
    const cmd = m[1].toUpperCase();
    const nums = m[2].trim().split(/[\s,]+/).filter(Boolean).map(Number);
    if (cmd === "M") {
      if (cur.length) out.push(cur);
      cur = [];
      for (let i = 0; i + 1 < nums.length; i += 2) cur.push([nums[i], nums[i + 1]]);
    } else if (cmd === "L") {
      for (let i = 0; i + 1 < nums.length; i += 2) cur.push([nums[i], nums[i + 1]]);
    } else if (cmd === "H") {
      for (const x of nums) cur.push([x, cur[cur.length - 1][1]]);
    } else if (cmd === "V") {
      for (const y of nums) cur.push([cur[cur.length - 1][0], y]);
    } else if (cur.length) {
      cur.push(cur[0]);
    }
  }
  if (cur.length) out.push(cur);
  return out;
}

/** Paths, given in some units and mapped to canvas pixels by `toPx`, back
 * as SVG path data in figure units (pixels / `perUnit`). Each subpath is
 * one matplotlib path (a grid line, a collection member) and is snapped as
 * Agg snaps it when it is straight-edged. */
export function snappedPath(d: string, toPx: (p: Pt) => Pt, strokePx: number, perUnit: number, snap = true): string {
  return polylines(d)
    .map((l) => {
      const px = l.map(toPx);
      const straight = snap && px.length <= 1024 && px.every((p, i) => i === 0 || Math.abs(p[0] - px[i - 1][0]) < 1e-4 || Math.abs(p[1] - px[i - 1][1]) < 1e-4);
      const f = (v: number) => String(Math.round(((straight ? snapPx(v, strokePx) : v) / perUnit) * 1e4) / 1e4);
      return px.map(([x, y], i) => `${i ? "L" : "M"}${f(x)} ${f(y)}`).join("");
    })
    .join("");
}

/** A marker as Agg's draw_markers stamps it: rendered once and placed at
 * the nearest pixel corner of its position; a straight-edged marker has its
 * own vertices snapped, any other is shifted half a pixel so that it is
 * centred on a pixel. Positions and sizes in canvas pixels; the path comes
 * back in figure units (pixels / `perUnit`). */
export function aggMarkerPath(name: string, sizePx: number, cx: number, cy: number, edgePx: number, perUnit: number): string {
  const d = markerShape(name).d;
  const straight =
    !/[CQ]/i.test(d) &&
    polylines(d).every((l) => l.every((p, i) => i === 0 || Math.abs(p[0] - l[i - 1][0]) * sizePx < 1e-4 || Math.abs(p[1] - l[i - 1][1]) * sizePx < 1e-4));
  const ox = Math.floor(cx + 0.5);
  const oy = Math.floor(cy + 0.5);
  const local = (v: number) => (straight ? snapPx(v * sizePx, edgePx) : v * sizePx + 0.5);
  return markerPathWith(name, (x, y) => [(ox + local(x)) / perUnit, (oy + local(y)) / perUnit]);
}
