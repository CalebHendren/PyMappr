// Marker shapes, exactly as matplotlib draws them. The outlines are
// matplotlib's own marker paths (MarkerStyle(code).get_path() transformed by
// get_transform()), dumped at marker size 1 with y flipped for SVG, so a
// symbol here matches the one PyMappr puts on its map and in its legend.
//
// Sizes: matplotlib's scatter `s` (PyMappr's PointStyle.size) is an AREA in
// pt²; the marker is drawn at `√s` points. Legend handles use
// `max(√area, 2) × marker_scale` points.

/** One matplotlib marker: its outline at size 1 (a unit-wide shape centred on
 * the point, y down) and the line join matplotlib strokes it with. `line`
 * shapes are strokes only; none of PyMappr's markers are, since its "Plus"
 * and "X" are matplotlib's filled "P" and "X". */
export type MarkerShape = { d: string; join: "miter" | "round" | "bevel"; line: boolean };

const SHAPES: Record<string, MarkerShape> = {
  o: {
    d:
      "M0 0.5C0.132602 0.5 0.25979 0.447317 0.353553 0.353553C0.447317 0.25979 0.5 0.132602 0.5 0" +
      "C0.5 -0.132602 0.447317 -0.25979 0.353553 -0.353553C0.25979 -0.447317 0.132602 -0.5 0 -0.5" +
      "C-0.132602 -0.5 -0.25979 -0.447317 -0.353553 -0.353553C-0.447317 -0.25979 -0.5 -0.132602 -0.5 0" +
      "C-0.5 0.132602 -0.447317 0.25979 -0.353553 0.353553C-0.25979 0.447317 -0.132602 0.5 0 0.5Z",
    join: "round",
    line: false,
  },
  s: { d: "M-0.5 0.5L0.5 0.5L0.5 -0.5L-0.5 -0.5Z", join: "miter", line: false },
  "^": { d: "M0 -0.5L-0.5 0.5L0.5 0.5Z", join: "miter", line: false },
  v: { d: "M0 0.5L0.5 -0.5L-0.5 -0.5Z", join: "miter", line: false },
  "<": { d: "M-0.5 0L0.5 0.5L0.5 -0.5Z", join: "miter", line: false },
  ">": { d: "M0.5 0L-0.5 -0.5L-0.5 0.5Z", join: "miter", line: false },
  D: { d: "M0 0.707107L0.707107 0L0 -0.707107L-0.707107 0Z", join: "miter", line: false },
  d: { d: "M0 0.707107L0.424264 0L0 -0.707107L-0.424264 0Z", join: "miter", line: false },
  "*": {
    d:
      "M0 -0.5L-0.112257 -0.154508L-0.475528 -0.154508L-0.181636 0.059017L-0.293893 0.404508L0 0.190983" +
      "L0.293893 0.404508L0.181636 0.059017L0.475528 -0.154508L0.112257 -0.154508Z",
    join: "bevel",
    line: false,
  },
  P: {
    d:
      "M-0.166667 0.5L0.166667 0.5L0.166667 0.166667L0.5 0.166667L0.5 -0.166667L0.166667 -0.166667" +
      "L0.166667 -0.5L-0.166667 -0.5L-0.166667 -0.166667L-0.5 -0.166667L-0.5 0.166667L-0.166667 0.166667Z",
    join: "miter",
    line: false,
  },
  X: {
    d: "M-0.25 0.5L0 0.25L0.25 0.5L0.5 0.25L0.25 0L0.5 -0.25L0.25 -0.5L0 -0.25L-0.25 -0.5L-0.5 -0.25L-0.25 0L-0.5 0.25Z",
    join: "miter",
    line: false,
  },
  p: { d: "M0 -0.5L-0.475528 -0.154508L-0.293893 0.404508L0.293893 0.404508L0.475528 -0.154508Z", join: "miter", line: false },
  h: { d: "M0 -0.5L-0.433013 -0.25L-0.433013 0.25L0 0.5L0.433013 0.25L0.433013 -0.25Z", join: "miter", line: false },
  "8": {
    d:
      "M-0.191342 -0.46194L-0.46194 -0.191342L-0.46194 0.191342L-0.191342 0.46194L0.191342 0.46194" +
      "L0.46194 0.191342L0.46194 -0.191342L0.191342 -0.46194Z",
    join: "miter",
    line: false,
  },
  ".": {
    d:
      "M0 0.25C0.066301 0.25 0.129895 0.223658 0.176777 0.176777C0.223658 0.129895 0.25 0.066301 0.25 0" +
      "C0.25 -0.066301 0.223658 -0.129895 0.176777 -0.176777C0.129895 -0.223658 0.066301 -0.25 0 -0.25" +
      "C-0.066301 -0.25 -0.129895 -0.223658 -0.176777 -0.176777C-0.223658 -0.129895 -0.25 -0.066301 -0.25 0" +
      "C-0.25 0.066301 -0.223658 0.129895 -0.176777 0.176777C-0.129895 0.223658 -0.066301 0.25 0 0.25Z",
    join: "round",
    line: false,
  },
};

/** PyMappr's marker names (pymappr/styling/styles.py `_BASE_MARKERS`), in
 * its order, to matplotlib's marker codes. */
export const BASE_MARKERS: Record<string, string> = {
  Circle: "o",
  Square: "s",
  Triangle: "^",
  "Triangle down": "v",
  "Triangle left": "<",
  "Triangle right": ">",
  Diamond: "D",
  "Thin diamond": "d",
  Star: "*",
  Plus: "P",
  X: "X",
  Pentagon: "p",
  Hexagon: "h",
  Octagon: "8",
  Dot: ".",
};

/** Openness is a fill style, not a different marker. */
export const OPEN_SUFFIX = " (open)";

/** All 30 marker names, solid then open, as PyMappr's MARKERS dict lists them. */
export const MARKERS: Record<string, string> = {
  ...BASE_MARKERS,
  ...Object.fromEntries(Object.entries(BASE_MARKERS).map(([name, code]) => [name + OPEN_SUFFIX, code])),
};

export const MARKER_NAMES: string[] = Object.keys(MARKERS);

/** The same table under the name src/lib/marker-paths.ts uses. */
export const MARKER_CODES = BASE_MARKERS;

/** Whether a PyMappr marker name is an open (outline-only) variant. */
export function isOpenMarker(name: string): boolean {
  return name.endsWith(OPEN_SUFFIX);
}

/** The matplotlib code for a PyMappr marker name, or a code itself ("o" for
 * anything unknown, as PointStyle.mpl_marker does). */
export function markerCode(name: string): string {
  if (Object.hasOwn(MARKERS, name)) return MARKERS[name];
  return Object.hasOwn(SHAPES, name) ? name : "o";
}

/** The shape for a PyMappr marker name. */
export function markerShape(name: string): MarkerShape {
  return SHAPES[markerCode(name)];
}

/** Marker size in points for matplotlib's scatter area `s` (pt²). */
export function areaToSize(area: number): number {
  return Math.sqrt(Math.max(area, 0));
}

/** Matplotlib's scatter area (pt²) for a marker size in points. */
export function sizeToArea(size: number): number {
  return size * size;
}

const TOKEN = /([MLCQZ])|(-?\d*\.?\d+(?:e[-+]?\d+)?)/gi;
const PARSED = new Map<string, (string | number)[]>();

function tokens(d: string): (string | number)[] {
  let parsed = PARSED.get(d);
  if (!parsed) {
    parsed = [...d.matchAll(TOKEN)].map((m) => (m[1] ? m[1] : Number(m[2])));
    PARSED.set(d, parsed);
  }
  return parsed;
}

const num = (v: number) => {
  const r = Math.round(v * 1e4) / 1e4;
  return Object.is(r, -0) ? "0" : String(r);
};

/** The SVG path of a marker `sizePt` points across, centred on (cx, cy).
 * The numbers are scaled in the path itself, so the outline can be stroked
 * at a plain width in the same units. */
export function markerPathAt(name: string, sizePt: number, cx = 0, cy = 0): string {
  let out = "";
  let axis = 0;
  for (const token of tokens(markerShape(name).d)) {
    if (typeof token === "string") {
      out += token;
      axis = 0;
    } else {
      out += (axis ? " " : "") + num(axis % 2 === 0 ? cx + token * sizePt : cy + token * sizePt);
      axis++;
    }
  }
  return out;
}

/** The outline for a matplotlib code or a PyMappr name at radius 1 (a
 * circle 2 across, i.e. scale by half the marker size), the convention of
 * src/lib/marker-paths.ts's `markerPath`. */
export function markerPath(marker: string): string {
  return markerPathAt(marker.replace(/ \(open\)$/, ""), 2);
}

/** A marker's outline with each unit-shape vertex (size 1, centred on 0,
 * y down) mapped through `f`. */
export function markerPathWith(name: string, f: (x: number, y: number) => [number, number]): string {
  let out = "";
  let pending: number | null = null;
  for (const token of tokens(markerShape(name).d)) {
    if (typeof token === "string") {
      out += token;
      pending = null;
    } else if (pending === null) {
      pending = token;
    } else {
      const [x, y] = f(pending, token);
      out += (out.endsWith("M") || out.endsWith("L") || out.endsWith("C") || out.endsWith("Q") ? "" : " ") + `${num(x)} ${num(y)}`;
      pending = null;
    }
  }
  return out;
}
