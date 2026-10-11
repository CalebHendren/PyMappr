// The app's state: the project document (PyMappr's shape, see model.ts) plus
// everything about the session that is not saved with a project: the view
// as drawn, what the backend last rendered, theme, the Advanced switch,
// status messages and the filter.
import {
  api,
  type AppInfo,
  type ColumnMapping,
  type LayerSettings,
  type LoadedDataset,
  type ProjectionSpec,
  type Rect,
  type RenderedInset,
  type RenderedMap,
  type ScaleBar,
} from "./api";
import { ADVANCED_LAYERS, defaultState, withDefaults, type DatasetEntry, type ProjectState } from "./model";
import { fitAspect, limitsFromView, viewFromLimits } from "./layout";
import { stateSnapshot } from "./project";

export type Theme = "light" | "dark";

/** The projection the project asks for, with its typed-in centre. */
export function projectionSpec(doc: ProjectState): ProjectionSpec {
  const num = (s: string) => (s.trim() === "" || !Number.isFinite(Number(s)) ? null : Number(s));
  return { name: doc.map.projection, lon0: num(doc.map.proj_lon0), lat0: num(doc.map.proj_lat0) };
}

export function layerSettings(doc: ProjectState): LayerSettings {
  const m = doc.map;
  return {
    lines: m.lines,
    fills: m.fills,
    points: m.points,
    labels: m.labels,
    ocean: m.ocean,
    lake_fill: m.lake_fill,
    bathymetry: m.bathymetry,
    capitals_only: m.capitals_only,
    basemap: m.basemap,
    graticule: m.graticule,
    hide_grid_labels: m.hide_grid_labels,
  };
}

/** Lon/lat of every point in a dataset entry (columns …, lon, lat). */
export function lonLats(entry: DatasetEntry): [number, number][] {
  const lon = entry.columns.indexOf("lon");
  const lat = entry.columns.indexOf("lat");
  return entry.rows.map((r) => [Number(r[lon]), Number(r[lat])]);
}

/** A loaded table as a project dataset entry, the way PyMappr adds one:
 * grouped by its first name column. */
export function entryFromLoaded(loaded: LoadedDataset, path: string): DatasetEntry {
  const n = loaded.nameLabels.length;
  return {
    name: loaded.fileName,
    visible: true,
    source_path: path,
    columns: [...Array.from({ length: n }, (_, i) => `name${i + 1}`), "lon", "lat"],
    name_labels: loaded.nameLabels,
    rows: loaded.points.map((p) => [...p.names, p.lon, p.lat]),
    group_by: loaded.nameLabels[0] ?? "",
    color_by: "",
    symbol_by: "",
    vary_symbols: false,
    open_by: "",
    open_values: [],
    legend_overrides: {},
    manual: null,
  };
}

/** The lon/lat box around points, crossing the antimeridian when that is
 * shorter, padded by max(15%, 2°) — PyMappr's zoom to data. */
export function dataExtent(points: [number, number][]): [number, number, number, number] | null {
  if (!points.length) return null;
  const lons = points.map((p) => p[0]).sort((a, b) => a - b);
  const lats = points.map((p) => p[1]);
  // Largest gap between sorted longitudes (wrapping): the box is its complement.
  let gap = lons[0] + 360 - lons[lons.length - 1];
  let start = lons[0];
  for (let i = 1; i < lons.length; i++) {
    const g = lons[i] - lons[i - 1];
    if (g > gap) {
      gap = g;
      start = lons[i];
    }
  }
  let w0 = start;
  let w1 = start + (360 - gap);
  let s = Math.min(...lats);
  let n = Math.max(...lats);
  const padX = Math.max((w1 - w0) * 0.15, 2);
  const padY = Math.max((n - s) * 0.15, 2);
  w0 -= padX;
  w1 += padX;
  s = Math.max(-90, s - padY);
  n = Math.min(90, n + padY);
  if (w1 - w0 >= 360) return [-180, 180, s, n];
  if (w0 < -180) {
    w0 += 360;
    w1 += 360;
  }
  return [w0, w1, s, n];
}

export const CONTINENT_EXTENTS: Record<string, [number, number, number, number]> = {
  World: [-180, 180, -90, 90],
  Africa: [-20, 55, -38, 40],
  Antarctica: [-180, 180, -90, -60],
  Asia: [25, 180, -12, 78],
  Europe: [-25, 45, 34, 72],
  "North America": [-170, -50, 5, 84],
  Oceania: [105, 180, -50, 10],
  "South America": [-85, -33, -58, 14],
};

class Store {
  // ---- the project -------------------------------------------------------
  doc = $state<ProjectState>(defaultState());
  projectName = $state("Untitled");
  projectPath = $state<string | null>(null);
  /** Snapshot of the document as last saved or opened, for "unsaved changes". */
  saved = $state(stateSnapshot(defaultState()));

  // ---- the session -------------------------------------------------------
  info = $state<AppInfo | null>(null);
  theme = $state<Theme>("light");
  advanced = $state(false);
  status = $state("Ready. Add a data file or open a project to begin.");
  error = $state<string | null>(null);
  busy = $state(false);

  /** The visible map area in SVG coordinates (y down); null = not framed yet. */
  view = $state<Rect | null>(null);
  /** Aspect (h / w) of the map box on screen. */
  boxAspect = $state(0.7);
  /** The figure as laid out on screen (exports scale from it). */
  screenFig = $state<import("./layout").Figure | null>(null);
  map = $state<RenderedMap | null>(null);
  inset = $state<RenderedInset | null>(null);
  scaleBar = $state<ScaleBar | null>(null);
  /** Projected point positions per dataset, keyed by projection. */
  projected = $state<{ key: string; xy: ([number, number] | null)[] }[]>([]);
  cursor = $state<[number, number] | null>(null);
  /** Filter on the active dataset (not saved with projects). */
  filter = $state<import("./symbology").PointFilter | null>(null);
  /** Dragged map labels, keyed "layer|text", offsets in map units. */
  labelOffsets = $state<Record<string, [number, number]>>({});
  back = $state<Rect[]>([]);
  forward = $state<Rect[]>([]);
  svgEl = $state<SVGSVGElement | null>(null);
  /** Natural Earth district downloads (ISO3) drawn with the counties layer. */
  districts = $state<string[]>([]);
  /** "Allow dragging labels" (Labels tab); not saved with projects. */
  allowLabelDrag = $state(false);

  active = $derived(this.doc.active === null ? null : (this.doc.datasets[this.doc.active] ?? null));
  projection = $derived(projectionSpec(this.doc));
  dirty = $derived(stateSnapshot($state.snapshot(this.doc) as ProjectState) !== this.saved);
  /** Advanced layers switched on (by a project) while the switch is off. */
  hiddenAdvancedOn = $derived.by(() => {
    if (this.advanced) return 0;
    const m = this.doc.map;
    return (
      ADVANCED_LAYERS.lines.filter((k) => m.lines[k]).length +
      ADVANCED_LAYERS.fills.filter((k) => m.fills[k]).length +
      ADVANCED_LAYERS.labels.filter((k) => m.labels[k]).length
    );
  });

  async init() {
    try {
      this.info = await api.appInfo();
      const s = await api.settings();
      const theme = s.theme === "dark" || s.theme === "light" ? (s.theme as Theme) : null;
      this.setTheme(theme ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"), false);
      this.advanced = s.advanced === true;
      this.districts = Array.isArray(s.districtsShown) ? (s.districtsShown as string[]) : [];
    } catch (e) {
      this.error = String(e);
    }
  }

  setStatus(message: string) {
    this.status = message;
    this.error = null;
  }

  fail(e: unknown) {
    this.error = e instanceof Error ? e.message : String(e);
  }

  setTheme(theme: Theme, save = true) {
    this.theme = theme;
    document.documentElement.dataset.theme = theme;
    if (save) api.setSettings({ theme }).catch(() => {});
  }

  setAdvanced(on: boolean) {
    this.advanced = on;
    api.setSettings({ advanced: on }).catch(() => {});
  }

  // ---- project lifecycle (file handling lives in documents.svelte.ts) ----

  /** Replace the whole document, as opening a project does. */
  load(state: Partial<ProjectState>, name: string, path: string | null) {
    this.doc = withDefaults(state);
    this.projectName = name;
    this.projectPath = path;
    this.saved = stateSnapshot($state.snapshot(this.doc) as ProjectState);
    this.projected = this.doc.datasets.map(() => ({ key: "", xy: [] }));
    this.filter = null;
    this.labelOffsets = {};
    this.back = [];
    this.forward = [];
    const { xlim, ylim } = this.doc.view;
    const v = viewFromLimits(xlim, ylim);
    this.view = v.w > 0 && v.h > 0 ? fitAspect(v, this.boxAspect) : null;
  }

  markSaved(name: string, path: string | null) {
    this.syncViewToDoc();
    this.projectName = name;
    this.projectPath = path;
    this.saved = stateSnapshot($state.snapshot(this.doc) as ProjectState);
  }

  /** Write the current view into the document (it is saved as limits). */
  syncViewToDoc() {
    if (this.view) this.doc.view = limitsFromView(this.view);
  }

  // ---- datasets ----------------------------------------------------------

  async importTable(path: string, sheet: string | null, mapping: ColumnMapping): Promise<LoadedDataset> {
    const loaded = await api.loadDataset(path, sheet, mapping);
    if (!loaded.points.length) throw new Error("No row has usable coordinates, so nothing was added.");
    this.addEntry(entryFromLoaded(loaded, path));
    const skipped = loaded.skipped.length;
    this.setStatus(
      `Loaded ${loaded.points.length} points from ${loaded.fileName}.` +
        (skipped ? ` Skipped ${skipped} rows without usable coordinates.` : ""),
    );
    return loaded;
  }

  addEntry(entry: DatasetEntry) {
    this.doc.datasets.push(entry);
    this.projected.push({ key: "", xy: [] });
    this.doc.active = this.doc.datasets.length - 1;
    this.filter = null;
    this.zoomToData();
  }

  removeDataset(index: number) {
    this.doc.datasets.splice(index, 1);
    this.projected.splice(index, 1);
    const n = this.doc.datasets.length;
    this.doc.active = n ? Math.min(this.doc.active ?? 0, n - 1) : null;
    this.filter = null;
  }

  setActive(index: number) {
    if (this.doc.active !== index) this.filter = null;
    this.doc.active = index;
  }

  // ---- the view ----------------------------------------------------------

  /** Frame a lon/lat box in the current projection. */
  async frame(lonlat: [number, number, number, number]) {
    try {
      const v = await api.extentView(this.projection, lonlat, this.boxAspect);
      this.setView(v);
    } catch (e) {
      this.fail(e);
    }
  }

  /** Frame all visible points, or the "Limit to" extent when there are none. */
  zoomToData() {
    const pts = this.doc.datasets.filter((d) => d.visible).flatMap(lonLats);
    const box = dataExtent(pts) ?? CONTINENT_EXTENTS[this.doc.map.continent] ?? CONTINENT_EXTENTS.World;
    this.frame(box);
  }

  /** Frame the "Limit to" continent (PyMappr's Home). */
  home() {
    this.frame(CONTINENT_EXTENTS[this.doc.map.continent] ?? CONTINENT_EXTENTS.World);
  }

  setView(v: Rect, remember = true) {
    if (remember && this.view) {
      this.back = [...this.back.slice(-49), this.view];
      this.forward = [];
    }
    this.view = fitAspect(v, this.boxAspect);
  }

  goBack() {
    const prev = this.back.at(-1);
    if (!prev || !this.view) return;
    this.forward = [this.view, ...this.forward];
    this.back = this.back.slice(0, -1);
    this.view = fitAspect(prev, this.boxAspect);
  }

  goForward() {
    const next = this.forward[0];
    if (!next || !this.view) return;
    this.back = [...this.back, this.view];
    this.forward = this.forward.slice(1);
    this.view = fitAspect(next, this.boxAspect);
  }

  /** Zoom by `factor` (> 1 = in) about a map point, or the centre. The view
   * stays between 1.5× and 1e-6× the world width, as in PyMappr. */
  zoomBy(factor: number, at?: [number, number]) {
    const v = this.view;
    const world = this.map?.extent;
    if (!v || !world) return;
    const w = Math.min(Math.max(v.w / factor, world.w * 1e-6), world.w * 1.5);
    const f = w / v.w;
    const [cx, cy] = at ?? [v.x + v.w / 2, v.y + v.h / 2];
    this.view = { x: cx - (cx - v.x) * f, y: cy - (cy - v.y) * f, w, h: v.h * f };
  }

  /** Lon/lat under a map point (SVG coordinates), or null off the map. */
  cursorAt(x: number, y: number): Promise<[number, number] | null> {
    return api.unproject($state.snapshot(this.projection), x, y).catch(() => null);
  }

  // ---- settings that redraw ---------------------------------------------

  setProjection(name: string, lon0 = "", lat0 = "") {
    this.doc.map.projection = name;
    this.doc.map.proj_lon0 = lon0;
    this.doc.map.proj_lat0 = lat0;
    this.labelOffsets = {};
    this.view = null; // reframed once the new projection is drawn
  }
}

export const store = new Store();
