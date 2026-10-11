import { describe, expect, it } from "vitest";
import birds from "./fixtures/hornbills-orchids.pymappr?raw";
import { referenceCases } from "./legend-fixtures";
import type { DatasetEntry } from "./model";
import { parseProject, stateToDict } from "./project";
import {
  applyDatasetStyle,
  applyPreset,
  applyStandardPreset,
  parsePreset,
  presetChoices,
  presetNameProblem,
  serializePreset,
  settingsFromState,
} from "./presets";

const project = () => parseProject(birds).state;

function harvestmen(patch: Partial<DatasetEntry> = {}): DatasetEntry {
  return {
    name: "harvestmen.csv",
    visible: true,
    source_path: "",
    columns: ["name1", "name2", "lon", "lat"],
    name_labels: ["Species", "Type status"],
    rows: [
      ["Nebulobunus alpha", "Holotype", -70, -40],
      ["Nebulobunus alpha", "", -71, -41],
    ],
    group_by: "Species",
    color_by: "",
    symbol_by: "",
    vary_symbols: false,
    open_by: "",
    open_values: [],
    legend_overrides: {},
    manual: null,
    ...patch,
  };
}

describe("presets", () => {
  it("reads back as saved", () => {
    const settings = { map: { projection: "Robinson" }, point_alpha: 0.5 };
    const text = serializePreset("Mine", settings, "0.2.0");
    expect(parsePreset(text)).toEqual({ name: "Mine", settings });
    expect(JSON.parse(text).format).toBe("pymappr-preset");
  });

  it("is not a project file, nor one from a newer PyMappr", () => {
    expect(() => parsePreset('{"format": "pymappr-project", "state": {}}')).toThrow("Not a PyMappr preset file.");
    expect(() => parsePreset("{")).toThrow(/^Not a PyMappr preset file: /);
    expect(() => parsePreset('{"format": "pymappr-preset", "format_version": 99, "app_version": "9", "settings": {}}')).toThrow(
      "This preset was saved by a newer PyMappr (9). Update PyMappr to use it.",
    );
  });

  it("leaves out the data and the zoom", () => {
    const entry = harvestmen({ color_by: "Type status", vary_symbols: true, legend_overrides: { "group\x00a": { color: "#ff0000" } } });
    const settings = settingsFromState(project(), entry);
    expect(Object.keys(settings)).toEqual(["map", "legend", "point_alpha", "point_edge", "dataset"]);
    expect(settings.dataset).toMatchObject({ group_by: "Species", color_by: "Type status", vary_symbols: true });
    expect(settings.dataset!.legend_overrides).toEqual(entry.legend_overrides);
    expect(settingsFromState(project(), null).dataset).toEqual({});
  });

  it("applies a dataset style where the columns exist", () => {
    const style = settingsFromState({}, harvestmen({ color_by: "Type status", vary_symbols: true, open_by: "Type status", open_values: ["Holotype"] })).dataset;
    const { entry, skipped } = applyDatasetStyle(harvestmen({ group_by: "" }), style);
    expect(skipped).toEqual([]);
    expect([entry.group_by, entry.color_by, entry.open_by, entry.open_values, entry.vary_symbols]).toEqual([
      "Species",
      "Type status",
      "Type status",
      ["Holotype"],
      true,
    ]);
  });

  it("leaves a missing column alone and reports it", () => {
    const { entry, skipped } = applyDatasetStyle(harvestmen(), { group_by: "Genus Species", color_by: "" });
    expect(skipped).toEqual(["Group by “Genus Species”"]);
    expect(entry.group_by).toBe("Species");
    expect(entry.color_by).toBe("");
  });

  it("merges legend row edits, the preset's winning", () => {
    const target = harvestmen({ legend_overrides: { a: { label: "A", color: "#111111" }, b: { hidden: true } } });
    const { entry } = applyDatasetStyle(target, { legend_overrides: { a: { color: "#222222" }, c: { size: 40 } } });
    expect(entry.legend_overrides).toEqual({ a: { label: "A", color: "#222222" }, b: { hidden: true }, c: { size: 40 } });
    expect(target.legend_overrides.a.color).toBe("#111111");
  });

  it("keeps the zoom unless the preset reprojects the map", () => {
    const state = project();
    const same = applyPreset(state, "Mine", settingsFromState(state, null));
    expect(same.keepView).toBe(true);
    expect(same.status).toBe("Applied the preset “Mine”.");
    const settings = settingsFromState(state, null);
    (settings.map as Record<string, unknown>).projection = "Robinson";
    expect(applyPreset(state, "Mine", settings).keepView).toBe(false);
  });

  it("applies settings over the defaults and says what did not carry over", () => {
    const state = project();
    const result = applyPreset(state, "Fig", { legend: { fontsize: 12 }, dataset: { group_by: "Family" } });
    expect(result.state.legend.fontsize).toBe(12);
    expect(result.state.map.projection).toBe("Equirectangular");
    expect(result.state.view).toEqual(state.view);
    expect(result.status).toBe(
      "Applied the preset “Fig”. Not applied: Group by “Family” is not a column in asia_hornbills.csv; " +
        "Group by “Family” is not a column in europe_orchids.csv.",
    );
  });

  it("lists Standard first unless it was deleted", () => {
    expect(presetChoices([{ name: "Alpha" }, { name: "beta" }], false)).toEqual(["Standard", "Alpha", "beta"]);
    expect(presetChoices([{ name: "Alpha" }], true)).toEqual(["Alpha"]);
    expect(presetNameProblem("Standard", false)).toMatch(/built-in/);
    expect(presetNameProblem("Standard", true)).toBeNull();
  });

  it("applies Standard exactly as PyMappr does", () => {
    const ref = referenceCases().find((c) => c.name === "birds-standard")!;
    const { state, status } = applyStandardPreset(project());
    expect(status).toBe(ref.status);
    expect(stateToDict(state)).toEqual(ref.state);
  });
});
