import { describe, expect, it } from "vitest";
import type { ManualParse } from "./api-docs";
import {
  applyCombine,
  combineNameColumns,
  combinePreview,
  defaultCombineColumns,
  editManualEntry,
  manualEntry,
  manualStyle,
  skippedReport,
} from "./datasets";
import type { DatasetEntry } from "./model";
import { entryFromDict, entryToDict } from "./project";
import { pointStyle, rowKey } from "./symbology";

// PyMappr's tests/test_data_loader.py `_taxa`.
const taxa = (): DatasetEntry =>
  entryFromDict({
    name: "taxa.csv",
    columns: ["name1", "name2", "name3", "lon", "lat"],
    name_labels: ["Family", "Genus", "Species"],
    rows: [
      ["Staphylinidae", "Eleusis", "chapadensis", -68.4, -12.3],
      ["Staphylinidae", "Xanthopygus", "", -41.2, -18.1],
    ],
    group_by: "Family",
    symbol_by: "Species",
  });

describe("combine columns", () => {
  it("adds a joined name column", () => {
    const dataset = taxa();
    const { entry, label } = combineNameColumns(dataset, ["Genus", "Species"]);
    expect(label).toBe("Genus Species");
    expect(entry.name_labels).toEqual(["Family", "Genus", "Species", "Genus Species"]);
    expect(entry.columns).toEqual(["name1", "name2", "name3", "name4", "lon", "lat"]);
    expect(entry.rows.map((r) => r[3])).toEqual(["Eleusis chapadensis", "Xanthopygus"]);
    expect(entry.rows[0][4]).toBe(-68.4);
    expect(dataset.name_labels).toEqual(["Family", "Genus", "Species"]);
    expect(dataset.columns).not.toContain("name4");
  });

  it("takes a separator and keeps labels unique", () => {
    const dataset = taxa();
    const dashed = combineNameColumns(dataset, ["Family", "Genus"], " - ");
    expect(dashed.label).toBe("Family - Genus");
    expect(dashed.entry.rows[0][3]).toBe("Staphylinidae - Eleusis");
    const once = combineNameColumns(dataset, ["Genus", "Species"]).entry;
    expect(combineNameColumns(once, ["Genus", "Species"]).label).toBe("Genus Species (2)");
    expect(() => combineNameColumns(dataset, ["Genus", "Subspecies"])).toThrow("No name column called 'Subspecies'");
  });

  it("ticks Genus and Species wherever they sit, else the last two", () => {
    expect(defaultCombineColumns(["Genus", "Species", "Type status", "Country"])).toEqual(["Genus", "Species"]);
    expect(defaultCombineColumns(["family", "GENUS", "specific epithet", "Locality"])).toEqual(["GENUS", "specific epithet"]);
    expect(defaultCombineColumns(["Family", "Tribe", "Name"])).toEqual(["Tribe", "Name"]);
    expect(defaultCombineColumns(["Genus", "Locality"])).toEqual(["Genus", "Locality"]);
  });

  it("previews the first row and groups by the new column", () => {
    expect(combinePreview(taxa(), ["Genus", "Species"], "_")).toBe("Eleusis_chapadensis");
    expect(combinePreview(taxa(), ["Genus"], " ")).toBe("");
    const { entry, status } = applyCombine(taxa(), ["Genus", "Species"], " ");
    expect([entry.group_by, entry.symbol_by]).toEqual(["Genus Species", ""]);
    expect(status).toBe("Added the column “Genus Species” and grouped by it.");
  });

  it("survives saving", () => {
    const { entry } = combineNameColumns(taxa(), ["Genus", "Species"]);
    const back = entryFromDict(JSON.parse(JSON.stringify(entryToDict(entry))));
    expect(back.name_labels).toEqual(["Family", "Genus", "Species", "Genus Species"]);
    expect(back.rows[0][3]).toBe("Eleusis chapadensis");
  });
});

describe("manual entry", () => {
  const parsed: ManualParse = { columns: ["name1", "lon", "lat"], nameLabels: ["Legend"], rows: [["spiders", -100, 38]], skipped: [] };
  const style = pointStyle({ color: "#123456", marker: "Star", size: 45 });

  it("pins the chosen style on the dataset's one row", () => {
    const entry = manualEntry({ legend: "spiders", text: "38,-100", order: "lat,lon", style }, parsed);
    expect(entry.group_by).toBe("Legend");
    expect(entry.legend_overrides).toEqual({ [rowKey("group", "spiders")]: { color: "#123456", marker: "Star", size: 45 } });
    expect(entry.manual).toEqual({ text: "38,-100", order: "lat,lon" });
    expect(manualStyle(entry)).toEqual({ ...style, fill: null });
  });

  it("moves the row's customisation when the legend name changes", () => {
    const entry = manualEntry({ legend: "spiders", text: "38,-100", order: "lat,lon", style }, parsed);
    entry.legend_overrides[rowKey("group", "spiders")].label = "Spiders!";
    const edited = editManualEntry(entry, { legend: "mites", text: "1,2", order: "lon,lat", style: pointStyle() }, { ...parsed, rows: [["mites", 1, 2]] });
    expect(edited.name).toBe("mites");
    expect(edited.legend_overrides).toEqual({ [rowKey("group", "mites")]: { label: "Spiders!", color: "#d62728", marker: "Circle", size: 30 } });
    expect(edited.manual).toEqual({ text: "1,2", order: "lon,lat" });
  });

  it("reports skipped lines as PyMappr does", () => {
    expect(skippedReport(0, ["line 1: x"])).toEqual({ kind: "error", title: "No usable rows", message: "No rows had valid coordinates.\n\nFirst problems:\nline 1: x" });
    expect(skippedReport(3, [])).toBeNull();
    const many = Array.from({ length: 14 }, (_, i) => `line ${i + 1}: bad`);
    expect(skippedReport(2, many)!.message).toMatch(/^Imported 2 rows; skipped 14:\n\nline 1: bad\n[\s\S]*line 12: bad\n… and 2 more$/);
  });
});
