import { describe, expect, it } from "vitest";
import { referenceCases } from "../../legend-fixtures";
import { symbology } from "../../symbology";
import { type Measure, type Rect, anchorForBox, dejaVuExtent, framePath, legendLayout } from "./layout";

type Metric = { text: string; size: number; weight: string; style: string; w: number; h: number; d: number; lpH: number; lpD: number };

/** A Measure answering with the metrics matplotlib measured the case with. */
function matplotlibMeasure(metrics: Metric[]): Measure {
  const key = (size: number, bold: boolean, italic: boolean) => `${size}|${bold}|${italic}`;
  const texts = new Map<string, Metric>();
  const lp = new Map<string, Metric>();
  for (const m of metrics) {
    const k = key(m.size, m.weight === "bold", m.style === "italic");
    texts.set(`${k}|${m.text}`, m);
    lp.set(k, m);
  }
  return (text, font) => {
    const k = key(font.size, font.bold, font.italic);
    if (text === "lp") {
      const m = lp.get(k);
      if (!m) throw new Error(`no metrics for ${k}`);
      return { width: 0, height: m.lpH, descent: m.lpD };
    }
    const m = texts.get(`${k}|${text}`);
    if (!m) throw new Error(`no metrics for ${k}|${text}`);
    return { width: m.w, height: m.h, descent: m.d };
  };
}

/** SVG rect -> matplotlib's [x0, y0, w, h] with y up. */
const up = (r: Rect, H: number) => [r.x, H - r.y - r.h, r.w, r.h];

describe("legend layout matches matplotlib", () => {
  for (const ref of referenceCases()) {
    if (!ref.geometry) continue;
    it(ref.name, () => {
      const g = ref.geometry;
      const [W, H] = g.axes;
      const result = symbology(ref.state, ref.filter);
      const layout = legendLayout({
        legend: result.legend,
        options: result.options,
        boxPt: { w: W, h: H },
        fontExtent: dejaVuExtent,
        measure: matplotlibMeasure(g.metrics),
        pointEdge: ref.state.point_edge,
      })!;
      // Within 0.05 pt of where matplotlib put each part; with nothing on
      // the map to avoid, "best" lands where PyMappr's did too.
      const close = (actual: number[], expected: number[]) =>
        actual.forEach((v, i) => expect(Math.abs(v - expected[i])).toBeLessThan(0.05));
      close(up(layout.box, H), g.box);
      expect(layout.rows.length).toBe(g.texts.length);
      layout.rows.forEach((row, i) => {
        close(up(row.text.box, H), g.texts[i]);
        if (row.marker) close([row.marker.cx, H - row.marker.cy], g.markers[i]);
      });
      if (g.title) close(up(layout.title!.box, H), g.title);
      else expect(layout.title).toBeNull();
    });
  }
});

describe("legend placement", () => {
  const ref = referenceCases().find((c) => c.name === "beetles-group-manual")!;
  const result = symbology(ref.state, null);
  const measure: Measure = (text, font) => ({ width: text.length * font.size * 0.5, height: font.size, descent: font.size * 0.2 });
  const box = { w: 600, h: 400 };
  const place = (patch: object, extra: object = {}) =>
    legendLayout({ legend: result.legend, options: { ...result.options, ...patch }, boxPt: box, measure, ...extra })!;

  it("pins a dragged legend's lower-left corner on its anchor", () => {
    const layout = place({ anchor: [0.25, 0.5] });
    expect(layout.box.x).toBeCloseTo(150);
    expect(layout.box.y + layout.box.h).toBeCloseTo(200);
    anchorForBox(layout.box, box).forEach((v, i) => expect(v).toBeCloseTo([0.25, 0.5][i], 9));
    expect(layout.anchor).toEqual([0.25, 0.5]);
  });

  it("keeps half a font size from the axes edge in a corner", () => {
    const f = result.options.fontsize;
    const layout = place({ location: "upper right" });
    expect(layout.box.x + layout.box.w).toBeCloseTo(600 - f / 2);
    expect(layout.box.y).toBeCloseTo(f / 2);
    const lower = place({ location: "lower left" });
    expect(lower.box.x).toBeCloseTo(f / 2);
    expect(lower.box.y + lower.box.h).toBeCloseTo(400 - f / 2);
  });

  it("puts 'best' in the first corner clear of points", () => {
    expect(place({ location: "best" }).location).toBe(1);
    const upperRight = place({ location: "upper right" }).box;
    const inside: [number, number] = [upperRight.x + 5, upperRight.y + 5];
    const layout = place({ location: "best" }, { pointsPt: [inside] });
    expect(layout.location).toBe(2);
    const everywhere = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((code) => {
      const name = Object.entries({ "upper right": 1, "upper left": 2, "lower left": 3, "lower right": 4, right: 5, "center left": 6, "center right": 7, "lower center": 8, "upper center": 9, center: 10 }).find(([, c]) => c === code)![0];
      const b = place({ location: name }).box;
      return [b.x + 1, b.y + 1] as [number, number];
    });
    // Every spot covers a point: the least bad wins, ties to the lowest code.
    expect(place({ location: "best" }, { pointsPt: everywhere }).location).toBe(1);
  });

  it("steps beyond a scale bar in its corner", () => {
    const f = result.options.fontsize;
    const layout = place({ location: "lower left" }, { clear: { corner: "lower left", frac: 0.1, liftPt: 4 } });
    expect(layout.box.y + layout.box.h).toBeCloseTo(400 - (40 + 4 + f / 2));
  });

  it("rounds the frame's corners as matplotlib does", () => {
    expect(framePath({ x: 0, y: 0, w: 10, h: 5 }, 0)).toBe("M0 0H10V5H0Z");
    expect(framePath({ x: 0, y: 0, w: 10, h: 5 }, 1)).toContain("Q10 0 10 1");
  });
});
