// Dataset edits from the Data tab: combining name columns and manually
// entered points. Ports of PyMappr's data_loader.combine_name_columns, the
// combine dialog's default ticks, and the manual-entry handlers
// (handlers/datasets.py on_manual_entry / on_edit_dataset).

import type { ManualParse } from "./api-docs";
import type { DatasetEntry, RowOverride } from "./model";
import { type PointStyle, applyOverride, pointStyle, rowKey } from "./symbology";

const GENUS_NAMES = ["genus"];
const SPECIES_NAMES = ["species", "specific epithet", "specificepithet", "epithet", "species epithet", "sp.", "sp"];

/** The columns that start ticked: Genus and Species wherever they sit, else
 * the last two. */
export function defaultCombineColumns(labels: string[]): string[] {
  const lower = (l: string) => l.trim().toLowerCase();
  const genus = labels.find((l) => GENUS_NAMES.includes(lower(l)));
  const species = labels.find((l) => SPECIES_NAMES.includes(lower(l)));
  if (genus && species) return [genus, species];
  return labels.slice(-2);
}

/** Python's repr of a string, for messages that quote a value. */
export function pyRepr(text: string): string {
  const q = text.includes("'") && !text.includes('"') ? '"' : "'";
  let out = q;
  for (const c of text) {
    if (c === "\\") out += "\\\\";
    else if (c === "\n") out += "\\n";
    else if (c === "\r") out += "\\r";
    else if (c === "\t") out += "\\t";
    else if (c === q) out += "\\" + c;
    else if (c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127) out += "\\x" + c.charCodeAt(0).toString(16).padStart(2, "0");
    else out += c;
  }
  return out + q;
}

/** A copy of the dataset with one more name column joining `labels`
 * ("Genus Species"); blank parts are skipped. Returns the entry and the new
 * column's label (made unique with " (2)", …). */
export function combineNameColumns(
  entry: DatasetEntry,
  labels: string[],
  separator = " ",
): { entry: DatasetEntry; label: string } {
  const keys = new Map<string, string>();
  entry.name_labels.forEach((l, i) => keys.set(l, `name${i + 1}`));
  const missing = labels.find((l) => !keys.has(l));
  if (missing !== undefined) throw new Error(`No name column called ${pyRepr(missing)}`);
  const indices = labels.map((l) => entry.columns.indexOf(keys.get(l)!));
  const values = entry.rows.map((row) =>
    indices
      .map((i) => (i < 0 || row[i] === null || row[i] === undefined ? "" : String(row[i]).trim()))
      .filter((p) => p)
      .join(separator),
  );
  const existing = entry.name_labels;
  const base = labels.join(separator).trim() || "Combined";
  let label = base;
  for (let n = 2; existing.includes(label); n++) label = `${base} (${n})`;
  // Name columns are name1..nameN in order, ahead of lon/lat.
  const at = existing.length;
  const columns = [...entry.columns];
  columns.splice(at, 0, `name${existing.length + 1}`);
  const rows = entry.rows.map((row, r) => {
    const copy = [...row];
    copy.splice(at, 0, values[r]);
    return copy;
  });
  return { entry: { ...entry, columns, rows, name_labels: [...existing, label] }, label };
}

/** The combined value of the first row, for the dialog's live preview. */
export function combinePreview(entry: DatasetEntry, labels: string[], separator: string): string {
  if (labels.length < 2 || !entry.rows.length) return "";
  const first = { ...entry, rows: entry.rows.slice(0, 1) };
  const { entry: sample } = combineNameColumns(first, labels, separator);
  return String(sample.rows[0][sample.name_labels.length - 1] ?? "");
}

/** Combine the columns and group by the result, clearing Symbol by (which
 * would hide the full names again). PyMappr's on_combine_columns. */
export function applyCombine(
  entry: DatasetEntry,
  labels: string[],
  separator: string,
): { entry: DatasetEntry; label: string; status: string } {
  const { entry: combined, label } = combineNameColumns(entry, labels, separator);
  return {
    entry: { ...combined, group_by: label, symbol_by: "" },
    label,
    status: `Added the column “${label}” and grouped by it.`,
  };
}

// ---------------------------------------------------------------- manual entry

export type ManualOrder = "lat,lon" | "lon,lat";

/** What the Manual entry dialog returns. */
export type ManualResult = { legend: string; text: string; order: ManualOrder; style: PointStyle };

/** A legend-row override pinning every part of a style. */
export function pinnedStyle(style: PointStyle): RowOverride {
  return { color: style.color, marker: style.marker, size: style.size };
}

/** A new dataset from typed-in points (PyMappr's on_manual_entry). */
export function manualEntry(result: ManualResult, parsed: ManualParse): DatasetEntry {
  return {
    name: result.legend,
    visible: true,
    source_path: "",
    columns: parsed.columns,
    name_labels: parsed.nameLabels,
    rows: parsed.rows,
    group_by: "Legend",
    color_by: "",
    symbol_by: "",
    vary_symbols: false,
    open_by: "",
    open_values: [],
    legend_overrides: { [rowKey("group", result.legend)]: pinnedStyle(result.style) },
    manual: { text: result.text, order: result.order },
  };
}

/** A manual dataset's current style, for re-opening it in the dialog. */
export function manualStyle(entry: DatasetEntry): PointStyle {
  const key = rowKey("group", entry.name);
  return applyOverride(pointStyle(), Object.hasOwn(entry.legend_overrides, key) ? entry.legend_overrides[key] : undefined) as PointStyle;
}

/** A manual dataset re-entered (PyMappr's on_edit_dataset): the legend
 * name is the group's value, so a rename moves the row's customisation. */
export function editManualEntry(entry: DatasetEntry, result: ManualResult, parsed: ManualParse): DatasetEntry {
  const overrides = { ...entry.legend_overrides };
  const oldKey = rowKey("group", entry.name);
  const old = Object.hasOwn(overrides, oldKey) ? overrides[oldKey] : {};
  delete overrides[oldKey];
  overrides[rowKey("group", result.legend)] = { ...old, ...pinnedStyle(result.style) };
  return {
    ...entry,
    name: result.legend,
    columns: parsed.columns,
    name_labels: parsed.nameLabels,
    rows: parsed.rows,
    legend_overrides: overrides,
    manual: { text: result.text, order: result.order },
  };
}

const MAX_SKIPPED_SHOWN = 12;

/** What to tell the user about skipped lines (PyMappr's _report_skipped):
 * an error when nothing was read, a warning when some lines were skipped,
 * or null. */
export function skippedReport(imported: number, skipped: string[]): { kind: "error" | "warning"; title: string; message: string } | null {
  if (imported === 0) {
    const problems = skipped.slice(0, MAX_SKIPPED_SHOWN).join("\n");
    return {
      kind: "error",
      title: "No usable rows",
      message: "No rows had valid coordinates." + (problems ? `\n\nFirst problems:\n${problems}` : ""),
    };
  }
  if (!skipped.length) return null;
  let shown = skipped.slice(0, MAX_SKIPPED_SHOWN).join("\n");
  const more = skipped.length - MAX_SKIPPED_SHOWN;
  if (more > 0) shown += `\n… and ${more} more`;
  return { kind: "warning", title: "Some rows skipped", message: `Imported ${imported} rows; skipped ${skipped.length}:\n\n${shown}` };
}
