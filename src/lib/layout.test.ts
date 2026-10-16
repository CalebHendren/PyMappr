import { describe, expect, it } from "vitest";
import { fitAspect, limitsFromView, printFigure, printPixels, screenFigure, viewFromLimits } from "./layout";
import { dataExtent } from "./store.svelte";

describe("figure layout", () => {
  it("places the map box with PyMappr's margins", () => {
    const plain = screenFigure(1000, 700, false, false);
    expect(plain.box.x).toBeCloseTo(10);
    expect(plain.box.w).toBeCloseTo(980);
    const ticks = screenFigure(1000, 700, true, false);
    expect(ticks.box.x).toBeCloseTo(55);
    expect(ticks.box.y + ticks.box.h).toBeCloseTo(700 * (1 - 0.045));
  });

  it("portrait shrinks the box to 6.5:9 and keeps it centred", () => {
    const f = screenFigure(1000, 700, false, true);
    expect(f.box.w / f.box.h).toBeCloseTo(6.5 / 9);
    expect(f.box.x + f.box.w / 2).toBeCloseTo(500);
    expect(f.mat).toBe(true);
  });

  it("prints at the chosen width with on-screen gutters", () => {
    const screen = screenFigure(900, 650, true, false);
    const fig = printFigure(screen, 17);
    expect((fig.w / 72) * 2.54).toBeCloseTo(17);
    // Gutters keep their inches: 900px * 0.055 at 100 dpi.
    expect(fig.box.x).toBeCloseTo(((900 * 0.055) / 100) * 72);
    expect(fig.box.h / fig.box.w).toBeCloseTo(screen.box.h / screen.box.w);
    expect(printPixels(fig, 600).w).toBe(Math.round((17 / 2.54) * 600));
  });

  it("caps a printed figure at 25 cm tall", () => {
    const tall = screenFigure(300, 1200, false, false);
    const fig = printFigure(tall, 17);
    expect((fig.h / 72) * 2.54).toBeCloseTo(25);
  });

  it("crops portrait mats off the print", () => {
    const fig = printFigure(screenFigure(1000, 700, false, true), 8);
    expect(fig.box.x).toBe(0);
    expect(fig.box.w).toBeCloseTo((8 / 2.54) * 72);
  });

  it("round-trips views and matplotlib limits", () => {
    const v = { x: -80, y: -15, w: 40, h: 30 };
    const { xlim, ylim } = limitsFromView(v);
    expect(xlim).toEqual([-80, -40]);
    expect(ylim).toEqual([-15, 15]);
    expect(viewFromLimits(xlim, ylim)).toEqual(v);
  });

  it("fits a view to the box shape about its centre", () => {
    const v = fitAspect({ x: 0, y: 0, w: 100, h: 10 }, 0.5);
    expect(v.h).toBe(50);
    expect(v.y).toBe(-20);
  });
});

describe("zoom to data", () => {
  it("pads by 15% or at least 2 degrees", () => {
    expect(dataExtent([[-60, -10], [-40, 10]])).toEqual([-63, -37, -13, 13]);
    expect(dataExtent([[-60, -10], [-50, 0]])).toEqual([-62, -48, -12, 2]);
    expect(dataExtent([[10, 10]])).toEqual([8, 12, 8, 12]);
  });

  it("crosses the antimeridian when that is shorter", () => {
    const box = dataExtent([[175, -40], [-178, -38]])!;
    expect(box[0]).toBeCloseTo(175 - 2);
    expect(box[1]).toBeCloseTo(182 + 2);
  });

  it("has nothing to frame without points", () => {
    expect(dataExtent([])).toBeNull();
  });
});
