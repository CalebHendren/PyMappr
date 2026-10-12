// PyMappr's north arrow (renderer/overlays.py `_apply_compass`) with the
// geometry matplotlib gives it: the "arrow" style is an annotation whose
// FancyArrowPatch ("-|>") runs from the "N" to the tip, clipped by the
// text's padded box, shrunk by shrinkA and given a filled head
// (patches.py ConnectionStyle._Base, ArrowStyle._Curve; bezier.py).
// Everything here is in canvas pixels with y UP, as matplotlib works, so
// the bisection lands on the same points.
import type { CompassOptions } from "./model";

type Pt = [number, number];

/** Where the compass's parts go, in axes fractions plus points (y up). */
export function compassLayout(o: CompassOptions) {
  const pad = 0.025;
  let x = o.position.includes("right") ? 1 - pad : pad;
  const y = o.position.includes("upper") ? 1 - pad : pad;
  const size = Math.max(Number(o.size), 0.1);
  const triangle = o.style === "triangle";
  const fontsize = (triangle ? 10 : 11) * size;
  const reach = 0.07 * size;
  const top = y > 0.5 ? y : y + reach;
  const lift = y > 0.5 ? 0 : 0.5 * fontsize;
  const inwards = x > 0.5 ? -1 : 1;
  const growth = Math.max(size - 1, 0);
  let shift = 0;
  if (triangle) x += inwards * 0.016 * growth;
  else shift = inwards * 0.425 * 11 * growth;
  return { x, top, labelY: top - reach, reach, size, fontsize, shiftPt: shift, liftPt: lift, triangle, half: 0.016 * size };
}

const lerp = (a: Pt, b: Pt, t: number): Pt => [a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t];

/** Split a Bézier (control points) at t: de Casteljau, as bezier.py does. */
function splitAt(beta: Pt[], t: number): [Pt[], Pt[]] {
  const rows: Pt[][] = [beta];
  let cur = beta;
  while (cur.length > 1) {
    const next: Pt[] = [];
    for (let i = 0; i < cur.length - 1; i++) next.push(lerp(cur[i], cur[i + 1], t));
    rows.push(next);
    cur = next;
  }
  return [rows.map((r) => r[0]), rows.reverse().map((r) => r[r.length - 1])];
}

/** The quadratic Bézier at t, BezierSegment's power form. */
function quadAt(p: Pt[], t: number): Pt {
  const u = 1 - t;
  const c = [u * u, 2 * u * t, t * t];
  return [c[0] * p[0][0] + c[1] * p[1][0] + c[2] * p[2][0], c[0] * p[0][1] + c[1] * p[1][1] + c[2] * p[2][1]];
}

/** split_path_inout on a single quadratic: the part after `inside` turns
 * false (unchanged when it never does). */
function clipStart(path: Pt[], inside: (p: Pt) => boolean, tolerance = 0.01): Pt[] {
  const startInside = inside(path[0]);
  if (inside(path[2]) === startInside) return path;
  let t0 = 0;
  let t1 = 1;
  let start = quadAt(path, t0);
  let end = quadAt(path, t1);
  let sIn = inside(start);
  for (;;) {
    if (Math.hypot(start[0] - end[0], start[1] - end[1]) < tolerance) break;
    const mt = 0.5 * (t0 + t1);
    const mid = quadAt(path, mt);
    const mIn = inside(mid);
    if (sIn !== mIn) {
      t1 = mt;
      if (end[0] === mid[0] && end[1] === mid[1]) break;
      end = mid;
    } else {
      t0 = mt;
      if (start[0] === mid[0] && start[1] === mid[1]) break;
      start = mid;
      sIn = mIn;
    }
  }
  return splitAt(path, (t0 + t1) / 2)[1];
}

/** The arrow from the "N" (its box centre `from`, box `textBox` as
 * [x0, y0, x1, y1]) to `tip`, all in pixels with y up. Returns the shaft
 * (a quadratic: start, control, end) and the closed head. */
export function compassArrow(from: Pt, tip: Pt, textBox: [number, number, number, number], pxPerPt: number, size: number, fontsize: number) {
  const padPx = 4 * pxPerPt;
  const [bx0, by0, bx1, by1] = [textBox[0] - padPx / 2, textBox[1] - padPx / 2, textBox[2] + padPx / 2, textBox[3] + padPx / 2];
  const inBox = (p: Pt) => p[0] > bx0 && p[0] < bx1 && p[1] > by0 && p[1] < by1;
  let path: Pt[] = [from, [(from[0] + tip[0]) / 2, (from[1] + tip[1]) / 2], tip];
  path = clipStart(path, inBox);
  const shrinkA = 6 * size * pxPerPt;
  const c = path[0];
  path = clipStart(path, (p) => (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 < shrinkA * shrinkA);

  const ms = fontsize * pxPerPt;
  const lw = 1.4 * size * pxPerPt;
  const headLength = 0.55 * ms;
  const headWidth = 0.28 * ms;
  const headDist = Math.hypot(headLength, headWidth);
  const cos = headLength / headDist;
  const sin = headWidth / headDist;
  const [x2, y2] = path[1];
  const [x3, y3] = path[2];
  let dx = x2 - x3;
  let dy = y2 - y3;
  const cp = Math.hypot(dx, dy) || 1;
  const padProjected = (0.5 * lw) / sin;
  const ddx = (padProjected * dx) / cp;
  const ddy = (padProjected * dy) / cp;
  dx = (dx / cp) * headDist;
  dy = (dy / cp) * headDist;
  const [dx1, dy1] = [cos * dx + sin * dy, -sin * dx + cos * dy];
  const [dx2, dy2] = [cos * dx - sin * dy, sin * dx + cos * dy];
  const shaft: Pt[] = [path[0], path[1], [x3 + ddx, y3 + ddy]];
  const head: Pt[] = [
    [x3 + ddx + dx1, y3 + ddy + dy1],
    [x3 + ddx, y3 + ddy],
    [x3 + ddx + dx2, y3 + ddy + dy2],
  ];
  return { shaft, head, lineWidth: lw };
}
