// App state: datasets and their groups, map settings, legend and export.
import { api, type AppInfo, type ColumnMapping, type LoadedDataset, type ProjectionSpec, type Rect, type RenderedMap } from "./api";
import { PALETTES, SHAPE_ORDER, TYPE_STATUS, type WaterFill } from "./styles";

/** How a dataset's points are split into legend entries. */
export type GroupBy = "all-names" | "dataset" | number;

export type Dataset = LoadedDataset & {
  id: number;
  path: string;
  visible: boolean;
  groupBy: GroupBy;
  /** Name column holding type status, or -1. */
  typeColumn: number;
  /** SVG position of each point under the current projection. */
  xy: ([number, number] | null)[];
  /** The projection `xy` was computed for. */
  xyKey: string;
};

export type Group = {
  id: string;
  datasetId: number;
  label: string;
  color: string;
  shape: string;
  visible: boolean;
  count: number;
};

/** A view of `extent` that fills a `size` box, with a small margin. */
export function fitView(extent: Rect, size: { w: number; h: number }): Rect {
  const aspect = size.w / size.h;
  let w = extent.w * 1.04;
  let h = w / aspect;
  if (h < extent.h * 1.04) {
    h = extent.h * 1.04;
    w = h * aspect;
  }
  return { x: extent.x + extent.w / 2 - w / 2, y: extent.y + extent.h / 2 - h / 2, w, h };
}

export type Corner = "upper-left" | "upper-right" | "lower-left" | "lower-right";

let nextId = 1;

function defaultGroupBy(labels: string[], typeColumn: number): GroupBy {
  const names = labels.filter((_, i) => i !== typeColumn).length;
  if (names === 0) return "dataset";
  return names <= 3 ? "all-names" : 0;
}

export function groupKey(ds: Dataset, names: string[]): string {
  if (ds.groupBy === "dataset") return ds.fileName;
  if (ds.groupBy === "all-names") {
    const key = names.filter((_, i) => i !== ds.typeColumn && names[i]).join(" ");
    return key || "(unnamed)";
  }
  return names[ds.groupBy] || "(blank)";
}

export function isHolotype(ds: Dataset, names: string[]): boolean {
  return ds.typeColumn >= 0 && /holotype/i.test(names[ds.typeColumn] ?? "");
}

class AppState {
  info = $state<AppInfo | null>(null);
  error = $state<string | null>(null);
  notice = $state<string | null>(null);
  theme = $state<"light" | "dark">("light");

  datasets = $state<Dataset[]>([]);
  /** Group styles, keyed by `${datasetId}:${label}`; kept across regrouping. */
  groupStyles = $state<Record<string, { color: string; shape: string; visible: boolean }>>({});

  palette = $state("default");
  varySymbols = $state(false);
  pointSize = $state(8);
  outlineColor = $state("#ffffff");
  outlineWidth = $state(0.5);
  opacity = $state(1);

  projection = $state<ProjectionSpec>({ name: "Equirectangular", lon0: null, lat0: null });
  layers = $state<Record<string, boolean>>({
    land: true,
    lakes: false,
    rivers: false,
    states: false,
    countries: true,
    graticule: false,
  });
  graticuleStep = $state(10);
  oceanFill = $state<WaterFill>("blue");
  lakeFill = $state<WaterFill>("blue");

  legend = $state({
    show: true,
    corner: "lower-left" as Corner,
    title: "",
    italic: false,
    counts: false,
    sort: "data" as "data" | "az",
    framed: true,
  });

  exportDpi = $state(300);
  exportWidthCm = $state<number | null>(null);

  // Map view, shared by the map, toolbar and export.
  map = $state<RenderedMap | null>(null);
  view = $state<Rect | null>(null);
  size = $state({ w: 800, h: 600 });
  svgEl = $state<SVGSVGElement | null>(null);
  cursor = $state<[number, number] | null>(null);
  busy = $state(false);

  /** Legend entries in display order. */
  groups = $derived.by(() => {
    const out: Group[] = [];
    for (const ds of this.datasets) {
      if (!ds.visible) continue;
      const counts = new Map<string, number>();
      for (const p of ds.points) {
        const key = groupKey(ds, p.names);
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      for (const [label, count] of counts) {
        const id = `${ds.id}:${label}`;
        const style = this.groupStyles[id] ?? { color: "#d62728", shape: "circle", visible: true };
        out.push({ id, datasetId: ds.id, label, count, ...style });
      }
    }
    if (this.legend.sort === "az") out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
  });

  pointCount = $derived(this.datasets.reduce((n, d) => n + (d.visible ? d.points.length : 0), 0));

  async init() {
    try {
      this.info = await api.appInfo();
    } catch (e) {
      this.error = String(e);
    }
  }

  async addDataset(path: string, sheet: string | null, mapping: ColumnMapping) {
    const loaded = await api.loadDataset(path, sheet, mapping);
    const typeColumn = loaded.nameLabels.findIndex((l) => TYPE_STATUS.test(l.trim()));
    const ds: Dataset = {
      ...loaded,
      id: nextId++,
      path,
      visible: true,
      groupBy: defaultGroupBy(loaded.nameLabels, typeColumn),
      typeColumn,
      xy: [],
      xyKey: "",
    };
    this.datasets.push(ds);
    this.assignStyles(false);
    const skipped = loaded.skipped.length;
    this.notice = `Added ${loaded.points.length} points from ${loaded.fileName}` + (skipped ? `; skipped ${skipped} rows without usable coordinates.` : ".");
  }

  removeDataset(id: number) {
    this.datasets = this.datasets.filter((d) => d.id !== id);
  }

  /** Hand out colours (and shapes when symbols vary) in legend order. With
   * `all` false, only groups that have no style yet get one. */
  assignStyles(all = true) {
    const colors = PALETTES[this.palette].colors;
    const styles = { ...this.groupStyles };
    this.groups.forEach((g, i) => {
      if (!all && this.groupStyles[g.id]) return;
      const old = styles[g.id];
      // Black & white cannot tell groups apart by colour alone: vary shapes too.
      const bw = this.palette === "bw";
      styles[g.id] = {
        color: colors[i % colors.length],
        shape: this.varySymbols || bw ? SHAPE_ORDER[i % SHAPE_ORDER.length] : "circle",
        visible: old?.visible ?? true,
      };
    });
    this.groupStyles = styles;
  }

  setGroupStyle(id: string, patch: Partial<{ color: string; shape: string; visible: boolean }>) {
    const current = this.groupStyles[id] ?? { color: "#d62728", shape: "circle", visible: true };
    this.groupStyles[id] = { ...current, ...patch };
  }

  /** PyMappr's built-in "Standard" preset: a Zootaxa/Phytotaxa-ready figure. */
  applyStandard() {
    this.palette = "bw";
    this.varySymbols = true;
    this.outlineColor = "#000000";
    this.outlineWidth = 0.6;
    this.opacity = 1;
    this.legend.italic = true;
    this.legend.framed = true;
    this.exportDpi = 600;
    this.exportWidthCm = 17;
    this.assignStyles(true);
    this.notice = "Applied the Standard preset: black-and-white symbols, italic legend, 600 DPI at 17 cm.";
  }

  setProjection(name: string) {
    this.projection = { name, lon0: null, lat0: null };
    this.view = null;
  }

  /** Zoom by `factor` (> 1 zooms in) around a point, or the view centre. */
  zoomBy(factor: number, at?: [number, number]) {
    const v = this.view;
    const extent = this.map?.extent;
    if (!v || !extent) return;
    const w = Math.min(Math.max(v.w / factor, extent.w / 5000), extent.w * 2);
    const f = w / v.w;
    const [cx, cy] = at ?? [v.x + v.w / 2, v.y + v.h / 2];
    this.view = { x: cx - (cx - v.x) * f, y: cy - (cy - v.y) * f, w, h: v.h * f };
  }

  fit() {
    if (this.map) this.view = fitView(this.map.extent, this.size);
  }

  toggleTheme() {
    this.theme = this.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = this.theme;
  }
}

export const app = new AppState();
