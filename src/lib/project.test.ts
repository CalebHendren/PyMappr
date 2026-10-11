import { describe, expect, it } from "vitest";
import beetles from "./fixtures/beetles-standard.pymappr?raw";
import birds from "./fixtures/hornbills-orchids.pymappr?raw";
import {
  ProjectFileError,
  entryFromDict,
  entryToDict,
  legacyStyles,
  overridesFromDict,
  parsePythonJson,
  parseProject,
  parseSession,
  pythonJson,
  readProjectDocument,
  safeFilename,
  serializeProject,
  serializeSession,
} from "./project";
import { rowKey } from "./symbology";

const strip = (doc: Record<string, unknown>) => {
  const { saved_at: _s, app_version: _a, ...rest } = doc;
  return rest;
};

describe("PyMappr project files", () => {
  for (const [name, text] of [
    ["beetles-standard", beetles],
    ["hornbills-orchids", birds],
  ]) {
    it(`re-saves ${name} unchanged but for saved_at and app_version`, () => {
      const original = JSON.parse(text);
      const { name: projectName, state } = parseProject(text, `${name}.pymappr`);
      expect(projectName).toBe(original.name);
      const again = JSON.parse(serializeProject(projectName, state, "0.2.0"));
      expect(strip(again)).toEqual(strip(original));
      expect(Object.keys(again)).toEqual(Object.keys(original));
      expect(Object.keys(again.state)).toEqual(Object.keys(original.state));
      expect(again.app_version).toBe("0.2.0");
      expect(again.saved_at).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$/);
    });
  }

  it("writes JSON the way Python's json.dumps does", () => {
    expect(pythonJson({ a: [1, 2.5, "é"], b: null, c: true, d: NaN })).toBe('{"a": [1, 2.5, "\\u00e9"], "b": null, "c": true, "d": NaN}');
    const back = parsePythonJson('{"x": NaN, "y": -Infinity, "s": "NaN"}') as Record<string, unknown>;
    expect(back.x).toBeNaN();
    expect(back.y).toBe(-Infinity);
    expect(back.s).toBe("NaN");
  });

  it("refuses what is not a project, with PyMappr's messages", () => {
    expect(() => readProjectDocument("{nope")).toThrow(/^Not a PyMappr project file: /);
    expect(() => readProjectDocument('{"format": "x", "state": {}}')).toThrow("Not a PyMappr project file.");
    expect(() => readProjectDocument('{"format": "pymappr-project", "state": []}')).toThrow(ProjectFileError);
    expect(() => readProjectDocument('{"format": "pymappr-project", "format_version": 2, "app_version": "9.0", "state": {}}')).toThrow(
      "This project was saved by a newer PyMappr (9.0). Update PyMappr to open it.",
    );
  });

  it("names a project after its file when it has no name", () => {
    expect(readProjectDocument('{"format": "pymappr-project", "state": {}}', "C:\\x\\Survey.pymappr").name).toBe("Survey");
  });

  it("makes typed names safe for the file system", () => {
    expect(safeFilename('a<b>:c"d/e\\f|g?h*')).toBe("a_b__c_d_e_f_g_h_");
    expect(safeFilename("  ..My map.. ")).toBe("My map");
    expect(safeFilename("   ")).toBe("Untitled");
    expect(safeFilename("NUL.tar")).toBe("NUL_.tar");
    expect(safeFilename("com1")).toBe("com1_");
    expect(safeFilename("console")).toBe("console");
  });

  it("migrates a project from before legend_overrides", () => {
    const old = overridesFromDict({ styles: { Eleusis: { color: "#123456", marker: "Star", size: 45 } } });
    expect(old).toEqual({ [rowKey("group", "Eleusis")]: { color: "#123456", marker: "Star", size: 45 } });
  });

  it("does not pin the palette from a newer project's legacy copy", () => {
    const entry = entryFromDict({ styles: { A: { color: "#000000", marker: "Circle", size: 30 } }, legend_overrides: {} });
    expect(entry.legend_overrides).toEqual({});
  });

  it("keeps only the override fields that are set", () => {
    const o = overridesFromDict({ legend_overrides: { k: { label: "x", hidden: null, junk: 1 }, e: { color: null }, z: "bad" } });
    expect(o).toEqual({ k: { label: "x" } });
  });

  it("writes the pinned group styles for older builds", () => {
    const styles = legacyStyles({
      [rowKey("group", "Pardosa distincta")]: { marker: "Star" },
      [rowKey("group", "Other")]: { color: "#abcdef" },
      [rowKey("group", "Renamed")]: { label: "x" },
      [rowKey("color", "C")]: { color: "#000000" },
    });
    expect(styles).toEqual({
      "Pardosa distincta": { color: "#d62728", marker: "Star", size: 30 },
      Other: { color: "#abcdef", marker: "Circle", size: 30 },
    });
  });

  it("round-trips a combined column and a manual dataset", () => {
    const entry = entryFromDict({
      name: "taxa.csv",
      columns: ["name1", "name2", "name3", "lon", "lat"],
      name_labels: ["Genus", "Species", "Genus Species"],
      rows: [["Eleusis", "chapadensis", "Eleusis chapadensis", "-68.4", -12.3]],
      group_by: "Genus Species",
      manual: { text: "1,2", order: "lat,lon" },
    });
    expect(entry.rows[0][3]).toBe(-68.4);
    const back = entryFromDict(JSON.parse(pythonJson(entryToDict(entry))));
    expect(back).toEqual(entry);
  });

  it("defaults what an entry lacks", () => {
    const entry = entryFromDict({});
    expect(entry).toMatchObject({ name: "Dataset", visible: true, group_by: "", open_by: "", manual: null, rows: [] });
  });

  it("checks the active dataset and merges settings over the defaults", () => {
    const text = '{"format": "pymappr-project", "state": {"datasets": [], "active": 3, "legend": {"fontsize": "8", "show_title": "false", "nope": 1}}}';
    const { state } = parseProject(text);
    expect(state.active).toBeNull();
    expect(state.legend.fontsize).toBe(8);
    expect(state.legend.show_title).toBe(false);
    expect("nope" in state.legend).toBe(false);
    expect(state.map.lines.countries).toBe(true);
  });

  it("saves and restores the session", () => {
    const { state } = parseProject(beetles);
    const text = serializeSession(state, { projectPath: "C:\\p\\b.pymappr", projectName: "b", geometry: "1200x800+10+10", unsaved: true }, "0.2.0");
    const doc = JSON.parse(text);
    expect(doc.name).toBe("b");
    expect(doc.state.unsaved).toBe(true);
    const back = parseSession(text);
    expect(back).toMatchObject({ projectPath: "C:\\p\\b.pymappr", projectName: "b", geometry: "1200x800+10+10", unsaved: true });
    expect(back.state.datasets[0].rows).toEqual(state.datasets[0].rows);
  });
});

// With RUSTYMAPPR_ROUNDTRIP_DIR set, write the re-saved fixtures there so
// scripts/check_roundtrip.py can open them in PyMappr itself.
describe("files for PyMappr to open", () => {
  it("writes the re-saved fixtures when asked", async () => {
    // @ts-expect-error node globals are not typed in this project
    const dir: string | undefined = globalThis.process?.env?.RUSTYMAPPR_ROUNDTRIP_DIR;
    if (!dir) return;
    // @ts-expect-error node modules are not typed in this project
    const fs = await import("node:fs");
    fs.mkdirSync(dir, { recursive: true });
    for (const [name, text] of [
      ["beetles-standard", beetles],
      ["hornbills-orchids", birds],
    ]) {
      const { name: projectName, state } = parseProject(text);
      fs.writeFileSync(`${dir}/${name}.pymappr`, serializeProject(projectName, state, "0.2.0"), "utf-8");
    }
  });
});
