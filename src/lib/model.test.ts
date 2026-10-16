import { describe, expect, it } from "vitest";
import beetles from "./fixtures/beetles-standard.pymappr?raw";
import { defaultState, withDefaults } from "./model";

describe("project state", () => {
  it("leaves a complete PyMappr project unchanged", () => {
    const state = JSON.parse(beetles).state;
    expect(withDefaults(state)).toEqual({ ...state });
  });

  it("fills in what an older project lacks", () => {
    const merged = withDefaults({ map: { projection: "Robinson", basemap: "satellite" } } as never);
    expect(merged.map.projection).toBe("Robinson");
    expect(merged.map.basemap).toBe("relief");
    expect(merged.map.lines.countries).toBe(true);
    expect(merged.legend).toEqual(defaultState().legend);
  });
});
