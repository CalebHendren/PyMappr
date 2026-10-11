// Map styling tables, taken from PyMappr (pymappr/styling/styles.py and
// pymappr/renderer/tables.py) so maps from both apps look alike.

export const PALETTES: Record<string, { label: string; colors: string[] }> = {
  default: {
    label: "Default",
    colors: ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f"],
  },
  okabe: {
    label: "Okabe-Ito (colour-blind safe)",
    colors: ["#e69f00", "#56b4e9", "#009e73", "#f0e442", "#0072b2", "#d55e00", "#cc79a7", "#000000"],
  },
  bw: { label: "Black & white", colors: ["#000000", "#ffffff", "#808080"] },
};

const polygon = (n: number, rotate = -90, r = 1) =>
  Array.from({ length: n }, (_, i) => {
    const a = ((rotate + (360 / n) * i) * Math.PI) / 180;
    return `${i ? "L" : "M"}${(r * Math.cos(a)).toFixed(4)} ${(r * Math.sin(a)).toFixed(4)}`;
  }).join("") + "Z";

const star = () =>
  Array.from({ length: 10 }, (_, i) => {
    const r = i % 2 ? 0.45 : 1.1;
    const a = ((-90 + 36 * i) * Math.PI) / 180;
    return `${i ? "L" : "M"}${(r * Math.cos(a)).toFixed(4)} ${(r * Math.sin(a)).toFixed(4)}`;
  }).join("") + "Z";

/** Marker outlines in a unit box centred on the point. `line` shapes are
 * drawn with a stroke only. */
export const SHAPES: Record<string, { label: string; d: string; line?: boolean }> = {
  circle: { label: "Circle", d: "M1 0A1 1 0 1 1 -1 0A1 1 0 1 1 1 0Z" },
  square: { label: "Square", d: "M-0.85 -0.85H0.85V0.85H-0.85Z" },
  triangle: { label: "Triangle", d: polygon(3, -90, 1.15) },
  diamond: { label: "Diamond", d: polygon(4, -90, 1.15) },
  star: { label: "Star", d: star() },
  plus: { label: "Plus", d: "M-1 0H1M0 -1V1", line: true },
  x: { label: "X", d: "M-0.8 -0.8L0.8 0.8M-0.8 0.8L0.8 -0.8", line: true },
  pentagon: { label: "Pentagon", d: polygon(5, -90, 1.05) },
  hexagon: { label: "Hexagon", d: polygon(6, -90, 1.05) },
  triangleDown: { label: "Triangle down", d: polygon(3, 90, 1.15) },
};

/** The order shapes are handed out in when symbols vary. */
export const SHAPE_ORDER = ["circle", "square", "triangle", "diamond", "star", "plus", "x", "pentagon", "hexagon", "triangleDown"];

/** Base layers, bottom to top, with PyMappr's colours and widths (pt). */
export const LAYERS = [
  { id: "land", label: "Land", fill: "#f0ece1", stroke: null, width: 0 },
  { id: "lakes", label: "Lakes", fill: "lakes", stroke: "#2d5f8a", width: 0.6 },
  { id: "rivers", label: "Rivers", fill: null, stroke: "#4a90c4", width: 0.5 },
  { id: "states", label: "States & provinces", fill: null, stroke: "#5a5a5a", width: 0.5 },
  { id: "countries", label: "Countries", fill: null, stroke: "#000000", width: 0.8 },
  { id: "graticule", label: "Graticule", fill: null, stroke: "#787878", width: 0.4 },
] as const;

export type WaterFill = "none" | "grey" | "blue";

export const WATER: Record<"ocean" | "lakes", Record<WaterFill, string>> = {
  ocean: { none: "#ffffff", grey: "#dcdcdc", blue: "#d4e6f4" },
  lakes: { none: "#ffffff", grey: "#c9c9c9", blue: "#a6cae0" },
};

/** Columns that hold type status; holotypes in them get open symbols. */
export const TYPE_STATUS = /^(type ?status|typestatus|type|status|type material)$/i;
