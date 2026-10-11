import { describe, expect, it } from "vitest";
import { referenceCases } from "./legend-fixtures";
import { markerCode } from "./markers";
import {
  type DatasetLayout,
  type MapLayout,
  type PointStyle,
  editorRows,
  markerPaint,
  paletteFor,
  symbology,
} from "./symbology";

const style = (s: PointStyle | null) => s && { color: s.color, marker: s.marker, size: s.size, fill: s.fill };

function layoutJson(layout: MapLayout) {
  const groups = (gs: DatasetLayout["groups"]) => gs.map((g) => ({ label: g.label, style: style(g.style), rows: g.rows }));
  const sections = (ss: MapLayout["sections"]) =>
    ss && ss.map((s) => ({ title: s.title, rows: s.rows.map((r) => ({ label: r.label, style: style(r.style), depth: r.depth })) }));
  return {
    datasets: layout.datasets.map((d) => ({
      name: d.entry.name,
      groups: groups(d.groups),
      openGroups: groups(d.openGroups),
      labelMap: d.labelMap,
      rows: d.rows.map((r) => ({ label: r.label, style: style(r.style) })),
      sections: sections(d.sections),
      attribute: d.attribute,
      paletteOffset: d.paletteOffset,
    })),
    sections: sections(layout.sections),
    rowOrder: layout.rowOrder,
    openNote: layout.openNote && { label: layout.openNote.label, style: style(layout.openNote.style) },
  };
}

describe("symbology matches PyMappr", () => {
  for (const ref of referenceCases()) {
    describe(ref.name, () => {
      const result = symbology(ref.state, ref.filter);

      it("styles and groups the points", () => {
        expect(layoutJson(result.layout)).toEqual(ref.layout);
      });

      it("defaults the title", () => {
        expect(result.options.title).toEqual(ref.title);
      });

      it("warns as PyMappr does", () => {
        expect(result.warning ?? "").toEqual(ref.warning);
      });

      it("lists the editor rows", () => {
        const active = ref.state.active;
        if (active === null) return;
        const entry = ref.state.datasets[active];
        const drawn = result.layout.datasets.find((d) => d.index === active);
        const rows = editorRows(entry, result.options, paletteFor(ref.state.map.palette), drawn?.paletteOffset ?? 0);
        expect(rows.map((r) => ({ ...r, style: style(r.style) }))).toEqual(ref.editor);
      });

      it("draws the legend rows matplotlib drew", () => {
        const legend = result.legend;
        expect(legend.visible).toBe(ref.legend !== null);
        if (!ref.legend) return;
        const o = result.options;
        expect(legend.title).toEqual(ref.legend.title?.text ?? null);
        if (ref.legend.title) {
          expect(ref.legend.title.weight).toBe(o.title_bold ? "bold" : "normal");
          expect(legend.titleUnderline).toBe(ref.legend.title.underline);
        }
        const drawn = legend.rows.map((row) => {
          const bold = row.header ? o.title_bold : o.label_bold;
          const italic = row.header ? o.title_italic : o.label_italic;
          const paint = row.style && markerPaint(row.style, ref.state.point_edge);
          return {
            text: row.label,
            weight: bold ? "bold" : "normal",
            style: italic ? "italic" : "normal",
            color: row.header ? o.title_color : o.label_color,
            underline: row.underline,
            handle: row.style && {
              marker: markerCode(row.style.marker),
              markersize: Math.max(Math.sqrt(row.area), 2) * o.marker_scale,
              face: paint!.face,
              edge: paint!.edge,
              edgeWidth: paint!.edgeWidth,
            },
          };
        });
        const expected = ref.legend.entries.map((e: Record<string, unknown>) => {
          const { size: _s, family: _f, handle, ...rest } = e as { handle: Record<string, number> | null } & Record<string, unknown>;
          return { ...rest, handle: handle && { ...handle, markersize: expect.closeTo(handle.markersize, 9) } };
        });
        expect(drawn).toEqual(expected);
      });
    });
  }
});
