// Styled, projected user points for the map. The styling rules (groups,
// colours, symbols, open symbols, overrides) come from the symbology module;
// this joins them with projected positions and the active filter.
import type { Mark } from "./components/map/MapSvg.svelte";
import type { DatasetEntry, ProjectState } from "./model";

export type PointStyle = { color: string; marker: string; size: number; open: boolean; hidden?: boolean };

/** Per-dataset, per-row point styles. Replaced by the full PyMappr port of
 * styles.py/layout.py once it lands (symbology.ts). */
export type StyleFn = (doc: ProjectState) => (PointStyle | null)[][];

const DEFAULT_PALETTE = ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f"];

/** A plain stand-in: one colour per Group by value. */
export const basicStyles: StyleFn = (doc) =>
  doc.datasets.map((ds: DatasetEntry) => {
    const col = ds.group_by ? ds.name_labels.indexOf(ds.group_by) : -1;
    const keys = new Map<string, number>();
    return ds.rows.map((row) => {
      const key = col >= 0 ? String(row[col] ?? "") : "";
      if (!keys.has(key)) keys.set(key, keys.size);
      return { color: DEFAULT_PALETTE[keys.get(key)! % DEFAULT_PALETTE.length], marker: "o", size: 30, open: false };
    });
  });

/** Marks to draw: visible datasets, filtered rows of the active one, and
 * points the projection shows. */
export function marks(
  doc: ProjectState,
  styles: (PointStyle | null)[][],
  projected: { xy: ([number, number] | null)[] }[],
  filter: { column: string; hidden: string[] } | null,
): Mark[] {
  const out: Mark[] = [];
  doc.datasets.forEach((ds, d) => {
    if (!ds.visible) return;
    const xy = projected[d]?.xy ?? [];
    const filterCol = filter && d === doc.active ? ds.name_labels.indexOf(filter.column) : -1;
    const hidden = new Set(filter?.hidden ?? []);
    ds.rows.forEach((row, r) => {
      const p = xy[r];
      const s = styles[d]?.[r];
      if (!p || !s || s.hidden) return;
      if (filterCol >= 0 && hidden.has(String(row[filterCol] ?? ""))) return;
      out.push({ x: p[0], y: p[1], color: s.color, marker: s.marker, size: s.size, open: s.open });
    });
  });
  // Open symbols draw over everything else, as in PyMappr.
  return [...out.filter((m) => !m.open), ...out.filter((m) => m.open)];
}
