// Typed wrappers over the Rust commands in src-tauri/src/lib.rs. Field names
// mirror the serde structs in crates/mappr-core.
import { invoke } from "@tauri-apps/api/core";

export type Rect = { x: number; y: number; w: number; h: number };

export type ProjectionSpec = { name: string; lon0: number | null; lat0: number | null };

export type AppInfo = { version: string; dataDir: string | null; projections: string[] };

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
};

export type RenderRequest = {
  projection: ProjectionSpec;
  view: Rect | null;
  pxWidth: number;
  layers: string[];
  graticule: number;
};

export type RenderedLayer = { id: string; geometry: "polygon" | "line"; d: string };

export type RenderedMap = {
  outline: string;
  extent: Rect;
  zoom: number;
  resolution: string;
  layers: RenderedLayer[];
  missing: string[];
};

// Rust's ProjectionSpec uses lon_0/lat_0, which serde renames to lon0/lat0.
const spec = (p: ProjectionSpec) => ({ name: p.name, lon0: p.lon0, lat0: p.lat0 });

export const api = {
  appInfo: () => invoke<AppInfo>("app_info"),
  setDataDir: (path: string) => invoke<string>("set_data_dir", { path }),
  inspectTable: (path: string, headerRow: boolean | null, sheet: string | null) =>
    invoke<TablePreview>("inspect_table", { path, headerRow, sheet }),
  loadDataset: (path: string, sheet: string | null, mapping: ColumnMapping) =>
    invoke<LoadedDataset>("load_dataset", { path, sheet, mapping }),
  renderMap: (request: RenderRequest) =>
    invoke<RenderedMap>("render_map", { request: { ...request, projection: spec(request.projection) } }),
  projectPoints: (projection: ProjectionSpec, points: [number, number][]) =>
    invoke<([number, number] | null)[]>("project_points", { projection: spec(projection), points }),
  unproject: (projection: ProjectionSpec, x: number, y: number) =>
    invoke<[number, number] | null>("unproject", { projection: spec(projection), x, y }),
  exportMap: (svg: string, format: "svg" | "png", widthPx: number, dpi: number, path: string) =>
    invoke<void>("export_map", { svg, format, widthPx, dpi, path }),
};
