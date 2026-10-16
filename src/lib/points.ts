// Styled, projected user points for the map: the symbology module's point
// styles (PyMappr's styles.py/layout.py port, filter already applied) joined
// with projected positions.
import type { Mark } from "./components/map/MapSvg.svelte";
import type { ProjectState } from "./model";
import { isOpen, markerPaint, type PointStyle } from "./symbology";

export type { PointStyle };

function mark(x: number, y: number, s: PointStyle, edge: { color: string; width: number }): Mark {
  const paint = markerPaint(s, edge);
  return { x, y, marker: s.marker, size: s.size, face: paint.face, edge: paint.edge, edgeWidth: paint.edgeWidth };
}

/** Marks to draw for every visible, unfiltered point the projection shows.
 * Open symbols draw over everything else, as in PyMappr. */
export function marks(
  doc: ProjectState,
  styles: (PointStyle | null)[][],
  projected: { xy: ([number, number] | null)[] }[],
): Mark[] {
  const filled: Mark[] = [];
  const open: Mark[] = [];
  doc.datasets.forEach((ds, d) => {
    if (!ds.visible) return;
    const xy = projected[d]?.xy ?? [];
    ds.rows.forEach((_, r) => {
      const p = xy[r];
      const s = styles[d]?.[r];
      if (!p || !s) return;
      (isOpen(s) ? open : filled).push(mark(p[0], p[1], s, doc.point_edge));
    });
  });
  return [...filled, ...open];
}

/** Marks for the inset, which projects every visible point in order. */
export function insetMarks(doc: ProjectState, styles: (PointStyle | null)[][], points: ([number, number] | null)[]): Mark[] {
  const flat = doc.datasets.flatMap((ds, d) => (ds.visible ? ds.rows.map((_, r) => styles[d]?.[r] ?? null) : []));
  return points.flatMap((p, i) => {
    const s = flat[i];
    return p && s ? [mark(p[0], p[1], s, doc.point_edge)] : [];
  });
}
