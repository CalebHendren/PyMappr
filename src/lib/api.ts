// The one door to the Rust backend. In the app every call goes through the
// Tauri `core` command; in a plain browser (npm run dev + npm run bridge) the
// same calls go to the dev HTTP bridge, so the UI can be driven from a
// browser. Commands live in src-tauri/src/cmd_*.rs.
import { invoke } from "@tauri-apps/api/core";

const BRIDGE = "http://127.0.0.1:1430/core";

export const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** Run a backend command. Errors come back as rejected promises with the
 * backend's message. */
export async function call<T>(cmd: string, args: Record<string, unknown> = {}): Promise<T> {
  if (inTauri) return invoke<T>("core", { cmd, args });
  const response = await fetch(BRIDGE, { method: "POST", body: JSON.stringify({ cmd, args }) });
  const reply = await response.json();
  if ("err" in reply) throw new Error(reply.err);
  return reply.ok as T;
}

// ---- dialogs: native in the app, a path prompt in a plain browser ---------

type Filter = { name: string; extensions: string[] };

export async function pickFile(title: string, filters: Filter[]): Promise<string | null> {
  if (!inTauri) return window.prompt(`${title} (path)`)?.trim() || null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const path = await open({ title, multiple: false, filters });
  return typeof path === "string" ? path : null;
}

export async function pickFolder(title: string): Promise<string | null> {
  if (!inTauri) return window.prompt(`${title} (folder path)`)?.trim() || null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const path = await open({ title, directory: true });
  return typeof path === "string" ? path : null;
}

export async function saveFile(title: string, defaultPath: string, filters: Filter[]): Promise<string | null> {
  if (!inTauri) return window.prompt(`${title} (path)`, defaultPath)?.trim() || null;
  const { save } = await import("@tauri-apps/plugin-dialog");
  return (await save({ title, defaultPath, filters })) ?? null;
}

export async function confirmDialog(message: string, title = "RustyMappr"): Promise<boolean> {
  if (!inTauri) return window.confirm(message);
  const { confirm } = await import("@tauri-apps/plugin-dialog");
  return confirm(message, { title });
}

export async function openUrl(url: string): Promise<void> {
  if (!inTauri) {
    window.open(url, "_blank", "noopener");
    return;
  }
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

// ---- shared types ----------------------------------------------------------

export type Rect = { x: number; y: number; w: number; h: number };

export type ProjectionSpec = { name: string; lon0: number | null; lat0: number | null };

export type AppInfo = {
  version: string;
  dataDir: string | null;
  defaultDataDir: string;
  configDir: string;
  projections: string[];
};

export type ColumnMapping = {
  longitude: string;
  latitude: string;
  names: string[];
  useHeaders: boolean;
  headerRow: boolean;
};

export type TablePreview = {
  fileName: string;
  sheets: string[];
  headerRow: boolean;
  headers: string[];
  preview: string[][];
  rowCount: number;
  mapping: ColumnMapping | null;
  mappingError: string | null;
};

export type Point = { lon: number; lat: number; names: string[]; row: number };

export type LoadedDataset = {
  fileName: string;
  nameLabels: string[];
  points: Point[];
  skipped: string[];
  /** Notes on points far from the rest, usually a missing minus sign. */
  farPoints: string[];
};

export type DataStatus = {
  dir: string;
  vectorsReady: number;
  vectorsTotal: number;
  rastersReady: number;
  rastersTotal: number;
  extrasReady: string[];
};

export type UpdateCheck = { checked: boolean; latest?: string; newer?: boolean; url?: string };

export type JobStatus = {
  id: number;
  label: string;
  step: string;
  progress: number | null;
  done: boolean;
  error: string | null;
  cancelled: boolean;
};

// ---- map rendering contract (src-tauri/src/cmd_map.rs, crates/mappr-core) --
// SVG coordinates throughout: projected x, and projected y negated (y down).

/** The layer switches, exactly as in the project's `map` section. */
export type LayerSettings = {
  lines: Record<string, boolean>;
  fills: Record<string, boolean>;
  points: Record<string, boolean>;
  labels: Record<string, boolean>;
  ocean: "none" | "grey" | "blue";
  lake_fill: "none" | "grey" | "blue";
  bathymetry: boolean;
  capitals_only: boolean;
  basemap: string;
  graticule: string;
  hide_grid_labels: boolean;
};

export type RenderRequest = {
  projection: ProjectionSpec;
  /** The visible area; null for the whole map (the result's extent). */
  view: Rect | null;
  /** Map width on screen (or in the export) in pixels; sets the detail. */
  pxWidth: number;
  /** Map height in pixels when the view is stretched to a box of another
   * shape (PyMappr's world maps fill the canvas); omit for square units. */
  pxHeight?: number | null;
  /** Pixels per typographic point, for label sizes and collisions. */
  pxPerPt: number;
  /** Added to the zoom when picking data detail (PyMappr's export boost). */
  detailBoost: number;
  layers: LayerSettings;
  /** ISO3 codes of downloaded geoBoundaries districts to draw. */
  districts: string[];
};

/** One drawable base layer, already in draw order. `id` keys the style
 * tables in styles.ts (bathymetry layers are "bathymetry:<depth>"; lake
 * fill is "lakes", lake outlines "lakes_outline"; downloaded districts are
 * one "districts" line layer). Fill paths keep each polygon's ring
 * orientation, so draw them with fill-rule "nonzero". Paths are thinned
 * to 0.01 pt and cut to the view plus a 5% margin. */
export type RenderedLayer = { id: string; kind: "fill" | "line"; d: string };

export type NeMarker = { layer: "cities" | "capitals" | "airports" | "ports"; x: number; y: number };

export type MapLabel = {
  /** A LABEL_STYLES key; "districts" labels take the counties style. */
  layer: string;
  text: string;
  x: number;
  y: number;
  /** "bottom" puts the text above the point (city dots); else centred. */
  va: "bottom" | "center";
  /** PyMappr's zoom font scale, 0.78–1.15. */
  fontScale: number;
};

export type Tick = { pos: number; text: string };

export type RenderedMap = {
  /** The edge of the drawn world (sphere outline); also the ocean fill. */
  outline: string;
  extent: Rect;
  /** PyMappr's zoom: log2(world width / view width). */
  zoom: number;
  /** Natural Earth scale used for the multi-resolution layers. */
  resolution: string;
  layers: RenderedLayer[];
  markers: NeMarker[];
  labels: MapLabel[];
  /** Raster basemap warped to the view, as an embedded PNG; transparent
   * off the world. Draw it stretched (preserveAspectRatio="none"). */
  raster: { href: string; x: number; y: number; w: number; h: number } | null;
  graticule: {
    d: string;
    /** Globe horizon ring, when on the globe. */
    horizon: string | null;
    /** Meridian labels along the bottom edge (pos = SVG x). */
    xTicks: Tick[];
    /** Parallel labels along the left edge (pos = SVG y). */
    yTicks: Tick[];
  } | null;
  /** Layers that could not be drawn, with the reason. */
  missing: string[];
};

export type ScaleBarRequest = {
  projection: ProjectionSpec;
  view: Rect;
  /** Map box in points. */
  boxPt: { w: number; h: number };
  options: import("./model").ScaleBarOptions;
};

/** Bars in axes fractions; `x`, `y` are the lower-left corner of the bar,
 * which is `width` wide and 0.011 tall. The first bar's label sits 0.012
 * above it (va bottom), a second bar's 0.012 below it (va top). Axes
 * fractions run 0..1 from the left/bottom, as PyMappr lays them out. */
export type ScaleBar = {
  bars: { x: number; y: number; width: number; label: string; units: "km" | "mi"; segments: number }[];
  /** Why no bar could be drawn, for the status line. */
  error: string | null;
};

export type InsetRequest = {
  projection: ProjectionSpec;
  view: Rect;
  pxWidth: number;
  /** As in RenderRequest: the map box's height when not the view's shape. */
  pxHeight?: number | null;
  pxPerPt: number;
  options: import("./model").InsetOptions;
  /** The scale bar's options, so an inset in its corner steps around it. */
  scaleBar?: import("./model").ScaleBarOptions | null;
  /** All visible user points as lon/lat, for "Your points". */
  points: [number, number][];
};

export type RenderedInset = {
  map: RenderedMap;
  /** Where the inset sits, in the map's axes fractions: x, y of its
   * lower-left corner from the left and bottom, and its w, h. */
  rect: Rect;
  /** The inset's own view in its SVG coordinates. */
  view: Rect;
  /** The inset's projection (after "same" fallbacks). */
  projection: ProjectionSpec;
  /** Height / width of the inset box. */
  aspect: number;
  /** Linking box: drawn on the inset, the main map, or not at all. */
  box: { on: "inset" | "map" | null; d: string };
  /** Projected positions of the points, in the inset's coordinates. */
  points: ([number, number] | null)[];
};

// ---- commands --------------------------------------------------------------

export const api = {
  appInfo: () => call<AppInfo>("app_info"),
  settings: () => call<Record<string, unknown>>("settings_get"),
  setSettings: (patch: Record<string, unknown>) => call<Record<string, unknown>>("settings_set", { patch }),
  setDataDir: (path: string) => call<string>("set_data_dir", { path }),
  inspectTable: (path: string, headerRow: boolean | null, sheet: string | null) =>
    call<TablePreview>("inspect_table", { path, headerRow, sheet }),
  loadDataset: (path: string, sheet: string | null, mapping: ColumnMapping) =>
    call<LoadedDataset>("load_dataset", { path, sheet, mapping }),
  renderMap: (request: RenderRequest) => call<RenderedMap>("render_map", { request }),
  projectPoints: (projection: ProjectionSpec, points: [number, number][]) =>
    call<([number, number] | null)[]>("project_points", { projection, points }),
  unproject: (projection: ProjectionSpec, x: number, y: number) =>
    call<[number, number] | null>("unproject", { projection, x, y }),
  exportMap: (svg: string, format: string, widthPx: number, dpi: number, path: string) =>
    call<void>("export_map", { svg, format, widthPx, dpi, path }),
  scaleBar: (request: ScaleBarRequest) => call<ScaleBar>("scale_bar", { request }),
  renderInset: (request: InsetRequest) => call<RenderedInset>("render_inset", { request }),
  /** The view framing a lon/lat box [lon_min, lon_max, lat_min, lat_max]
   * (continent, data extent) in a box of the given aspect (h / w), as
   * PyMappr's set_extent does (the globe frames its whole disk). */
  extentView: (projection: ProjectionSpec, lonlat: [number, number, number, number], aspect: number) =>
    call<Rect>("extent_view", { projection, lonlat, aspect }),
  districtsList: () => call<{ iso3: string; name: string; license: string; source: string }[]>("districts_list"),
  /** Download districts for these countries; returns a job id to poll. */
  districtsFetch: (iso3: string[]) => call<number>("districts_fetch", { iso3 }),
  districtsRemove: (iso3: string) => call<void>("districts_remove", { iso3 }),
  /** ISO3 codes of the countries inside the view. */
  countriesInView: (projection: ProjectionSpec, view: Rect) =>
    call<string[]>("countries_in_view", { projection, view }),
  dataStatus: (dir: string | null) => call<DataStatus>("data_status", { dir }),
  /** Download map data into `dir` (RustyMappr's own folder when null); returns a job id. */
  dataDownload: (dir: string | null, rasters: boolean, extras: boolean) =>
    call<number>("data_download", { dir, rasters, extras }),
  checkUpdates: (force: boolean) => call<UpdateCheck>("check_updates", { force }),
  jobStatus: (id: number) => call<JobStatus | null>("job_status", { id }),
  jobCancel: (id: number) => call<void>("job_cancel", { id }),
};
