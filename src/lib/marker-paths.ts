// matplotlib's marker shapes as SVG paths, scaled so a circle has radius 1
// (draw them scaled by half the marker size: matplotlib's `s` is an area in
// pt², and the marker is √s points across). PyMappr names its markers
// "Circle", "Square", … with an " (open)" variant; both spellings work here.

function poly(points: [number, number][]): string {
  return points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(4)} ${y.toFixed(4)}`).join("") + "Z";
}

/** A regular polygon of radius r, first vertex at `startDeg` (0 = up). */
function regular(n: number, r: number, startDeg: number): string {
  return poly(
    Array.from({ length: n }, (_, i) => {
      const a = ((startDeg + (360 / n) * i - 90) * Math.PI) / 180;
      return [r * Math.cos(a), r * Math.sin(a)] as [number, number];
    }),
  );
}

function star(): string {
  return poly(
    Array.from({ length: 10 }, (_, i) => {
      const r = i % 2 ? 0.381966 : 1;
      const a = ((36 * i - 90) * Math.PI) / 180;
      return [r * Math.cos(a), r * Math.sin(a)] as [number, number];
    }),
  );
}

const S2 = Math.SQRT2;

/** Paths by matplotlib marker code; SVG y points down. */
const CODES: Record<string, string> = {
  o: "M1 0A1 1 0 1 1 -1 0A1 1 0 1 1 1 0Z",
  ".": "M0.5 0A0.5 0.5 0 1 1 -0.5 0A0.5 0.5 0 1 1 0.5 0Z",
  s: "M-1 -1H1V1H-1Z",
  "^": poly([[0, -1], [-1, 1], [1, 1]]),
  v: poly([[0, 1], [-1, -1], [1, -1]]),
  "<": poly([[-1, 0], [1, -1], [1, 1]]),
  ">": poly([[1, 0], [-1, -1], [-1, 1]]),
  D: poly([[0, -S2], [S2, 0], [0, S2], [-S2, 0]]),
  d: poly([[0, -S2], [0.6 * S2, 0], [0, S2], [-0.6 * S2, 0]]),
  "*": star(),
  P: poly(
    (
      [
        [-1, -3], [1, -3], [1, -1], [3, -1], [3, 1], [1, 1],
        [1, 3], [-1, 3], [-1, 1], [-3, 1], [-3, -1], [-1, -1],
      ] as [number, number][]
    ).map(([x, y]) => [x / 3, y / 3] as [number, number]),
  ),
  X: poly(
    (
      [
        [-1, -2], [0, -1], [1, -2], [2, -1], [1, 0], [2, 1],
        [1, 2], [0, 1], [-1, 2], [-2, 1], [-1, 0], [-2, -1],
      ] as [number, number][]
    ).map(([x, y]) => [x / 2, y / 2] as [number, number]),
  ),
  p: regular(5, 1, 0),
  h: regular(6, 1, 0),
  "8": regular(8, 1, 22.5),
};

/** PyMappr's marker names and their matplotlib codes. */
export const MARKER_CODES: Record<string, string> = {
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

/** Whether a PyMappr marker name is an open (outline-only) variant. */
export function isOpenMarker(name: string): boolean {
  return name.endsWith(" (open)");
}

/** The SVG path for a matplotlib code or a PyMappr marker name. */
export function markerPath(marker: string): string {
  const name = marker.replace(/ \(open\)$/, "");
  return CODES[name] ?? CODES[MARKER_CODES[name] ?? "o"] ?? CODES.o;
}
