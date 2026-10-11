// How the map looks: PyMappr's style tables (pymappr/renderer/tables.py) and
// the control panel's layer rows (pymappr/ui/control_panel/tables.py), so a
// map from either app matches. Sizes are in points; line widths are scaled
// by the project's `line_width`.

export type Dash = number[] | null;

/** Line layers: colour, width (pt), dash (on/off in multiples of width). */
export const LINE_STYLES: Record<string, { color: string; width: number; dash: Dash }> = {
  countries: { color: "#000000", width: 0.8, dash: null },
  continents: { color: "#000000", width: 0.8, dash: null },
  sovereignty: { color: "#5b2d8b", width: 0.9, dash: null },
  map_units: { color: "#2d6b8b", width: 0.6, dash: null },
  subunits: { color: "#8b6b2d", width: 0.5, dash: null },
  dependencies: { color: "#c2571a", width: 0.9, dash: null },
  disputed_lines: { color: "#c0392b", width: 0.9, dash: [4, 2] },
  maritime: { color: "#3b7bbf", width: 0.7, dash: [5, 3] },
  eez: { color: "#1c5c99", width: 0.8, dash: [1, 2] },
  timezones: { color: "#8a5fbf", width: 0.6, dash: [6, 3] },
  states: { color: "#5a5a5a", width: 0.5, dash: null },
  counties: { color: "#8a8a8a", width: 0.35, dash: null },
  districts: { color: "#8a8a8a", width: 0.35, dash: null },
  lakes_outline: { color: "#2d5f8a", width: 0.6, dash: null },
  rivers: { color: "#4a90c4", width: 0.5, dash: null },
  wadis: { color: "#b3985c", width: 0.6, dash: [3, 2] },
  reefs: { color: "#25a08c", width: 0.7, dash: null },
  regions: { color: "#a8763e", width: 0.5, dash: [3, 3] },
  roads: { color: "#b0693c", width: 0.35, dash: null },
};

/** Fill layers: face, edge, edge width (pt), opacity. Land is white rather
 * than PyMappr's cream: RustyMappr's base map is white throughout. */
export const FILL_STYLES: Record<string, { face: string; edge: string | null; width: number; alpha: number }> = {
  land: { face: "#ffffff", edge: null, width: 0, alpha: 1 },
  deserts: { face: "#f3e6c0", edge: null, width: 0, alpha: 0.65 },
  playas: { face: "#efe7c3", edge: "#d8c98a", width: 0.3, alpha: 1 },
  urban: { face: "#d95f4e", edge: null, width: 0, alpha: 0.55 },
  parks: { face: "#bfe3b4", edge: "#4e9a51", width: 0.4, alpha: 0.85 },
  ice_shelves: { face: "#d8ecf7", edge: "#a8cfe6", width: 0.3, alpha: 1 },
  glaciers: { face: "#e6f3fb", edge: "#b9d9ec", width: 0.3, alpha: 1 },
  disputed: { face: "#e8b4b8", edge: "#b03a48", width: 0.5, alpha: 0.75 },
  ecoregions: { face: "#8fbf6f", edge: "#4e7a3a", width: 0.25, alpha: 0.42 },
  marine_ecoregions: { face: "#5fa8c4", edge: "#2d6b8b", width: 0.25, alpha: 0.42 },
  biodiversity: { face: "#e0954a", edge: "#a85f16", width: 0.5, alpha: 0.5 },
};

export type WaterFill = "none" | "grey" | "blue";

/** Ocean and lake fills by mode; "none" leaves white paper. */
export const WATER: Record<"ocean" | "lakes", Record<WaterFill, string | null>> = {
  ocean: { none: null, grey: "#dcdcdc", blue: "#d4e6f4" },
  lakes: { none: null, grey: "#c9c9c9", blue: "#a6cae0" },
};

/** Bathymetry fills by depth (m), shallow to deep. */
export const BATHYMETRY: Record<number, string> = {
  0: "#e3f2fa",
  200: "#d2e9f5",
  1000: "#c0dff0",
  2000: "#a8d1e8",
  3000: "#8fc2e0",
  4000: "#74b2d8",
  5000: "#5a9fcd",
  6000: "#4489bd",
  7000: "#3273aa",
  8000: "#245e94",
  9000: "#194a7d",
  10000: "#103862",
};

/** Natural Earth point markers: matplotlib marker, area (pt²), face, edge. */
export const NE_MARKERS: Record<string, { marker: string; size: number; face: string; edge: string }> = {
  cities: { marker: "o", size: 11, face: "#333333", edge: "#ffffff" },
  capitals: { marker: "*", size: 60, face: "#b03a2e", edge: "#ffffff" },
  airports: { marker: "^", size: 18, face: "#4757a8", edge: "#ffffff" },
  ports: { marker: "v", size: 16, face: "#1f7a70", edge: "#ffffff" },
};

/** Map labels: size (pt), colour, weight, style. The halo is white, 2.2 pt
 * wide at 0.85 opacity. Districts use the counties style. */
export const LABEL_STYLES: Record<string, { size: number; color: string; bold?: boolean; italic?: boolean }> = {
  countries: { size: 9, color: "#1a1a1a", bold: true },
  states: { size: 8, color: "#3a3a3a" },
  counties: { size: 6.5, color: "#4a4a4a" },
  districts: { size: 6.5, color: "#4a4a4a" },
  cities: { size: 7.5, color: "#222222" },
  airports: { size: 6.5, color: "#3a4c8c" },
  ports: { size: 6.5, color: "#14614f", italic: true },
  lakes: { size: 7.5, color: "#14477a", italic: true },
  rivers: { size: 7, color: "#14477a", italic: true },
  regions: { size: 8, color: "#7a5230", italic: true },
  timezones: { size: 8, color: "#6a4a9c" },
};
export const LABEL_HALO = { width: 2.2, color: "#ffffff", alpha: 0.85 };

export const GRATICULE = { color: "#787878", width: 0.4, alpha: 0.7, horizonWidth: 0.8, tickSize: 7 };

/** The map frame (matplotlib's axes spines). */
export const FRAME = { color: "#000000", width: 0.8 };

/** The inset map's look. */
export const INSET = { land: "#e3e3e3", lineScale: 0.6, pointScale: 0.3, frameWidth: 0.8, boxWidth: 1.2 };

/** Axes margins as figure fractions (left, bottom, right, top). */
export const MARGINS_WITH_TICKS = [0.055, 0.045, 0.99, 0.99] as const;
export const MARGINS_PLAIN = [0.01, 0.012, 0.99, 0.988] as const;
/** Portrait maps sit in a box this wide per unit of height, on a mat. */
export const PORTRAIT_ASPECT = 6.5 / 9;
export const PORTRAIT_MAT = "#e6e6e6";

/** PyMappr's screen figure is drawn at 100 dpi. */
export const SCREEN_DPI = 100;

/** Map fonts: Arial everywhere so the screen and rasterised exports agree. */
export const MAP_FONT = "Arial, Helvetica, sans-serif";

// ---- the Layers and Labels tabs ---------------------------------------------

export type LayerKind = "line" | "fill" | "point";
export type LayerRow = { key: string; text: string; kind: LayerKind; advanced?: boolean };

export const LAYER_SECTIONS: { title: string; rows: LayerRow[] }[] = [
  {
    title: "Borders & areas",
    rows: [
      { key: "countries", text: "Countries", kind: "line" },
      { key: "states", text: "States/Provinces", kind: "line" },
      { key: "counties", text: "US Counties", kind: "line" },
      { key: "sovereignty", text: "Sovereign states", kind: "line", advanced: true },
      { key: "map_units", text: "Map units", kind: "line", advanced: true },
      { key: "subunits", text: "Map subunits", kind: "line", advanced: true },
      { key: "dependencies", text: "Dependencies", kind: "line", advanced: true },
      { key: "disputed", text: "Disputed areas", kind: "fill", advanced: true },
      { key: "disputed_lines", text: "Disputed boundaries", kind: "line", advanced: true },
      { key: "timezones", text: "Time zones", kind: "line", advanced: true },
    ],
  },
  {
    title: "Water & marine",
    rows: [
      { key: "rivers", text: "Rivers", kind: "line" },
      { key: "wadis", text: "Wadis / intermittent rivers", kind: "line" },
      { key: "maritime", text: "Maritime boundaries", kind: "line", advanced: true },
      { key: "eez", text: "EEZ / 200 nm limits", kind: "line", advanced: true },
      { key: "reefs", text: "Reefs", kind: "line" },
    ],
  },
  {
    title: "Physical features",
    rows: [
      { key: "land", text: "Land polygons (fill)", kind: "fill" },
      { key: "glaciers", text: "Glaciers", kind: "fill" },
      { key: "ice_shelves", text: "Antarctic ice shelves", kind: "fill" },
      { key: "playas", text: "Playas", kind: "fill" },
      { key: "deserts", text: "Deserts", kind: "fill" },
      { key: "regions", text: "Geographic regions", kind: "line" },
    ],
  },
  {
    title: "Culture & infrastructure",
    rows: [
      { key: "urban", text: "Urban areas", kind: "fill" },
      { key: "airports", text: "Airports", kind: "point" },
      { key: "ports", text: "Ports", kind: "point" },
      { key: "parks", text: "Parks & protected areas", kind: "fill" },
      { key: "roads", text: "Roads", kind: "line" },
    ],
  },
  {
    title: "Biodiversity & ecoregions",
    rows: [
      { key: "biodiversity", text: "Biodiversity hotspots", kind: "fill" },
      { key: "ecoregions", text: "Terrestrial ecoregions", kind: "fill" },
      { key: "marine_ecoregions", text: "Marine ecoregions", kind: "fill" },
    ],
  },
];

export const LABEL_ROWS: { key: string; text: string; advanced?: boolean }[] = [
  { key: "countries", text: "Countries" },
  { key: "states", text: "States/Provinces" },
  { key: "counties", text: "US Counties" },
  { key: "cities", text: "Major cities" },
  { key: "airports", text: "Airports" },
  { key: "ports", text: "Ports" },
  { key: "lakes", text: "Lakes" },
  { key: "rivers", text: "Rivers" },
  { key: "regions", text: "Geographic regions" },
  { key: "timezones", text: "Time zones", advanced: true },
];

/** Section of the project's `map` that holds a layer's switch. */
export const SECTION_FOR_KIND: Record<LayerKind, "lines" | "fills" | "points"> = {
  line: "lines",
  fill: "fills",
  point: "points",
};

export const CONTINENTS = ["World", "Africa", "Antarctica", "Asia", "Europe", "North America", "Oceania", "South America"];

export const BASEMAPS: [string, string][] = [
  ["simple", "Simple (white with borders)"],
  ["relief", "Relief"],
  ["relief_alt", "Relief (alternate)"],
  ["relief_grey", "Relief (greyscale)"],
  ["blue_marble", "Blue Marble"],
];

export const CORNERS = ["lower left", "lower right", "upper left", "upper right"] as const;

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

/** PyMappr's Legend tab, as data: (section, open?, rows). A row is
 * [field, kind, label, extra]. */
export type LegendRow =
  | [string, "check", string]
  | [string, "combo", string, string[]]
  | [string, "choice", string, Record<string, string>]
  | [string, "text", string]
  | [string, "number", string, [number, number, number]]
  | [string, "color", string]
  | [string, "style", string]
  | [null, "note", string];

export const LEGEND_SECTIONS: [string, boolean | null, LegendRow[]][] = [
  [
    "Legend",
    null,
    [
      ["show", "check", "Show legend"],
      ["location", "combo", "Position", LEGEND_LOCATIONS],
      ["show_title", "check", "Show a title"],
      ["title", "text", "Title"],
      [null, "note", "Blank uses the Group by column name."],
    ],
  ],
  [
    "Rows and order",
    true,
    [
      ["hierarchy", "choice", "Hierarchy", { "Auto (detect)": "auto", "Always nest": "always", "Never nest": "never" }],
      [null, "note", "Nesting also lets shapes repeat across colour groups, so a hierarchy needs fewer of them."],
      [
        "order",
        "choice",
        "Order",
        {
          "As in data": "data",
          "A – Z": "az",
          "Z – A": "za",
          "Count, high to low": "count_desc",
          "Count, low to high": "count_asc",
          Manual: "manual",
        },
      ],
      ["counts", "check", "Show point counts"],
      ["count_format", "choice", "Counts look like", { "(12)": "(n)", "12": "n", "(12, 34%)": "(n, %)", "34%": "%" }],
      ["blank_label", "text", "Blank values"],
      ["section_titles", "check", "Show section titles"],
      ["title_separator", "text", "Title separator"],
      ["dataset_prefix", "check", "Prefix sections with the dataset name"],
      ["empty_groups", "check", "Keep groups with no visible rows"],
    ],
  ],
  [
    "Nested keys",
    false,
    [
      ["indent", "number", "Indent (spaces)", [0, 12, 1]],
      ["bold_groups", "check", "Bold the group rows"],
      ["group_spacer", "check", "Blank row between groups"],
      ["group_swatch", "choice", "Group swatch", { Circle: "circle", "Match first child": "child", "No swatch": "none" }],
      ["symbol_swatch_color", "color", "Crossed symbol colour"],
      [null, "note", "Used only when the columns cross, where a shape appears in every colour."],
    ],
  ],
  [
    "Layout",
    false,
    [
      ["columns", "number", "Columns", [1, 6, 1]],
      ["label_spacing", "number", "Row spacing", [0, 4, 0.1]],
      ["column_spacing", "number", "Column spacing", [0, 8, 0.5]],
      ["marker_scale", "number", "Marker size", [0.1, 6, 0.25]],
      ["handle_text_pad", "number", "Swatch gap", [0, 4, 0.1]],
      [null, "note", "Blank gap = automatic."],
      ["handle_length", "number", "Swatch width", [0, 8, 0.5]],
      ["border_pad", "number", "Inner padding", [0, 4, 0.1]],
    ],
  ],
  [
    "Frame",
    false,
    [
      ["frame", "check", "Draw legend frame"],
      ["frame_color", "color", "Fill"],
      ["frame_alpha", "number", "Fill opacity", [0, 1, 0.05]],
      ["frame_edge_color", "color", "Border"],
      ["frame_width", "number", "Border width", [0, 6, 0.2]],
      ["rounded", "check", "Rounded corners"],
      ["shadow", "check", "Drop shadow"],
    ],
  ],
  [
    "Text",
    false,
    [
      ["fontsize", "number", "Font size", [4, 32, 1]],
      ["title_fontsize", "number", "Title font size", [4, 40, 1]],
      ["font_family", "choice", "Font", { Default: "", "Sans-serif": "sans-serif", Serif: "serif", Monospace: "monospace" }],
      ["title_align", "choice", "Title align", { Left: "left", Centre: "center", Right: "right" }],
      ["label_color", "color", "Label colour"],
      ["title_color", "color", "Title colour"],
      ["label", "style", "Label text"],
      ["title", "style", "Title text"],
    ],
  ],
];
