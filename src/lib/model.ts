// The project state, in the exact shape PyMappr saves (pymappr/handlers/
// state.py, pymappr/files/projects.py), so .pymappr files open in both apps.
// Defaults come from a fresh PyMappr: pymappr-defaults.json is its
// `_collect_state()` (scripts/pymappr_reference.py default-state).
import defaults from "./pymappr-defaults.json";

/** Per-legend-row customisation, keyed by PyMappr's `row_key`. */
export type RowOverride = {
  label?: string;
  hidden?: boolean;
  order?: number;
  color?: string;
  marker?: string;
  size?: number;
};

/** A dataset with its data embedded: `columns` are name1..nameN, lon, lat. */
export type DatasetEntry = {
  name: string;
  visible: boolean;
  source_path: string;
  columns: string[];
  name_labels: string[];
  rows: (string | number)[][];
  group_by: string;
  color_by: string;
  symbol_by: string;
  vary_symbols: boolean;
  open_by: string;
  open_values: string[];
  /** Written for older PyMappr builds only; never read back when
   * `legend_overrides` is present. */
  styles?: Record<string, { color: string; marker: string; size: number }>;
  legend_overrides: Record<string, RowOverride>;
  manual: { text: string; order: string } | null;
};

export type Corner = "lower left" | "lower right" | "upper left" | "upper right";

export type CompassOptions = {
  show: boolean;
  position: Corner;
  style: "arrow" | "triangle";
  size: number;
  color: string;
};

export type ScaleBarOptions = {
  show: boolean;
  units: "km" | "mi" | "both";
  position: Corner;
  style: "segmented" | "plain";
  length_mode: "auto" | "fixed";
  fixed_length: number | null;
  segments: number;
  width: number;
  fontsize: number;
  color: string;
  draggable: boolean;
  anchor_x: number | null;
  anchor_y: number | null;
};

export type InsetOptions = {
  show: boolean;
  position: Corner;
  size: number;
  region: string;
  zoom_out: number;
  lon_min: number | null;
  lon_max: number | null;
  lat_min: number | null;
  lat_max: number | null;
  projection: "same" | "Equirectangular" | "Robinson" | "Globe";
  countries: boolean;
  states: boolean;
  counties: boolean;
  land: boolean;
  ocean: "none" | "grey" | "blue";
  points: boolean;
  box: boolean;
  box_color: string;
  draggable: boolean;
  anchor_x: number | null;
  anchor_y: number | null;
};

export type MapSettings = {
  projection: string;
  proj_lon0: string;
  proj_lat0: string;
  basemap: "simple" | "relief" | "relief_alt" | "relief_grey" | "blue_marble";
  continent: string;
  orientation: "Landscape" | "Portrait";
  compass: boolean;
  compass_options: CompassOptions;
  scale_bar: ScaleBarOptions;
  inset: InsetOptions;
  palette: string;
  graticule: "Off" | "1°" | "5°" | "10°";
  hide_grid_labels: boolean;
  line_width: number;
  dpi: string;
  export_width: string;
  ocean: "none" | "grey" | "blue";
  lake_fill: "none" | "grey" | "blue";
  bathymetry: boolean;
  capitals_only: boolean;
  lines: Record<string, boolean>;
  fills: Record<string, boolean>;
  points: Record<string, boolean>;
  labels: Record<string, boolean>;
};

export type LegendOptions = {
  show: boolean;
  title: string | null;
  show_title: boolean;
  location: string;
  hierarchy: "auto" | "always" | "never";
  order: "data" | "az" | "za" | "count_desc" | "count_asc" | "manual";
  counts: boolean;
  count_format: string;
  blank_label: string;
  section_titles: boolean;
  title_separator: string;
  dataset_prefix: boolean;
  empty_groups: boolean;
  indent: number;
  bold_groups: boolean;
  group_spacer: boolean;
  group_swatch: "circle" | "first" | "none";
  symbol_swatch_color: string;
  columns: number;
  label_spacing: number;
  column_spacing: number;
  handle_text_pad: number | null;
  handle_length: number;
  border_pad: number;
  marker_scale: number;
  frame: boolean;
  frame_color: string;
  frame_alpha: number;
  frame_edge_color: string;
  frame_width: number;
  rounded: boolean;
  shadow: boolean;
  fontsize: number;
  title_fontsize: number;
  font_family: string;
  label_color: string;
  title_color: string;
  label_bold: boolean;
  label_italic: boolean;
  label_underline: boolean;
  title_bold: boolean;
  title_italic: boolean;
  title_underline: boolean;
  title_align: "left" | "center" | "right";
  /** Where the user dragged the legend, as axes fractions; null = placed by `location`. */
  draggable: boolean;
  anchor: [number, number] | null;
};

export type ProjectState = {
  datasets: DatasetEntry[];
  active: number | null;
  map: MapSettings;
  legend: LegendOptions;
  point_alpha: number;
  point_edge: { color: string; width: number };
  /** Axis limits in projected units with y up (matplotlib), not SVG's y down. */
  view: { xlim: [number, number]; ylim: [number, number] };
};

export const PROJECT_FORMAT = "pymappr-project";
export const PROJECT_FORMAT_VERSION = 1;
export const PRESET_FORMAT = "pymappr-preset";

/** A fresh PyMappr's state; a new object each call. */
export function defaultState(): ProjectState {
  return structuredClone(defaults) as unknown as ProjectState;
}

/** Fill in whatever an older project lacks, the way PyMappr's
 * `_apply_settings` merges with its defaults. */
export function withDefaults(state: Partial<ProjectState>): ProjectState {
  const d = defaultState();
  const map = { ...d.map, ...(state.map ?? {}) } as MapSettings;
  for (const section of ["lines", "fills", "points", "labels"] as const) {
    map[section] = { ...d.map[section], ...(state.map?.[section] ?? {}) };
  }
  map.compass_options = { ...d.map.compass_options, ...(state.map?.compass_options ?? {}) };
  if (state.map && "compass" in state.map) map.compass_options.show = Boolean(state.map.compass);
  map.scale_bar = { ...d.map.scale_bar, ...(state.map?.scale_bar ?? {}) };
  map.inset = { ...d.map.inset, ...(state.map?.inset ?? {}) };
  if ((map.basemap as string) === "satellite") map.basemap = "relief";
  return {
    ...d,
    ...state,
    datasets: state.datasets ?? [],
    map,
    legend: { ...d.legend, ...(state.legend ?? {}) },
    point_edge: { ...d.point_edge, ...(state.point_edge ?? {}) },
  } as ProjectState;
}

/** The political extras the Advanced checkbox hides. */
export const ADVANCED_LAYERS = {
  lines: ["sovereignty", "map_units", "subunits", "dependencies", "disputed_lines", "timezones", "maritime", "eez"],
  fills: ["disputed"],
  labels: ["timezones"],
} as const;
