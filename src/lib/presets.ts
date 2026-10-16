// Presets: every setting but the data and the zoom, saved to reuse in other
// projects, plus the built-in "Standard" preset. A port of PyMappr's
// pymappr/files/presets.py and pymappr/handlers/presets.py; files go through
// the backend (api-docs.ts).

import { PUBLICATION_LEGEND } from "./legend";
import { PRESET_FORMAT, type DatasetEntry, type ProjectState, type RowOverride, defaultState, withDefaults } from "./model";
import { legendFromDict, localTimestamp, parsePythonJson, pythonJson, stateToDict } from "./project";
import {
  BLACK_AND_WHITE_NAME,
  PUBLICATION_POINT_EDGE,
  holotypeMarking,
  organisePublicationLegend,
} from "./symbology";

export const PRESET_EXTENSION = ".pymappr-preset";
export const PRESET_FORMAT_VERSION = 1;
/** The built-in preset, listed first; it adapts to the data it is applied
 * to rather than restoring saved values. */
export const BUILT_IN_PRESET = "Standard";
/** The Standard preset's export: a Zootaxa / Phytotaxa figure. */
export const PUBLICATION_DPI = "600";
export const PUBLICATION_WIDTH = "17 cm (Zootaxa / Phytotaxa page)";

/** What a preset holds: the state minus datasets/active/view, plus the
 * selected dataset's styling in `dataset`. */
export type PresetSettings = Record<string, unknown> & {
  dataset?: Partial<DatasetStyle>;
};

export type DatasetStyle = {
  group_by: string;
  color_by: string;
  symbol_by: string;
  vary_symbols: boolean;
  open_by: string;
  open_values: string[];
  legend_overrides: Record<string, RowOverride>;
};

const PROJECT_ONLY = ["datasets", "active", "view"];

/** A preset from a state: every setting but the data and the zoom, plus the
 * styling of the selected dataset (PyMappr's `settings_from_state`). */
export function settingsFromState(state: ProjectState | Record<string, unknown>, entry: DatasetEntry | null): PresetSettings {
  const dict = "map" in state && "datasets" in state ? stateToDict(state as ProjectState) : state;
  const settings: PresetSettings = {};
  for (const [key, value] of Object.entries(dict)) if (!PROJECT_ONLY.includes(key)) settings[key] = structuredClone(value);
  settings.dataset =
    entry === null
      ? {}
      : {
          group_by: entry.group_by,
          color_by: entry.color_by,
          symbol_by: entry.symbol_by,
          vary_symbols: entry.vary_symbols,
          open_by: entry.open_by,
          open_values: [...entry.open_values],
          legend_overrides: Object.fromEntries(Object.entries(entry.legend_overrides).map(([k, v]) => [k, { ...v }])),
        };
  return settings;
}

/** A preset file's text (PyMappr's `save_preset`). */
export function serializePreset(name: string, settings: PresetSettings, appVersion: string, now: Date = new Date()): string {
  return pythonJson({
    format: PRESET_FORMAT,
    format_version: PRESET_FORMAT_VERSION,
    app_version: appVersion,
    name,
    saved_at: localTimestamp(now),
    settings,
  });
}

export class PresetFileError extends Error {}

/** Read a preset file's text, checked as PyMappr's `load_preset` does. */
export function parsePreset(text: string, path = ""): { name: string; settings: PresetSettings } {
  let document: unknown;
  try {
    document = parsePythonJson(text);
  } catch (exc) {
    throw new PresetFileError(`Not a PyMappr preset file: ${(exc as Error).message}`);
  }
  const doc = document as Record<string, unknown>;
  if (typeof doc !== "object" || doc === null || Array.isArray(doc) || doc.format !== PRESET_FORMAT) {
    throw new PresetFileError("Not a PyMappr preset file.");
  }
  const settings = doc.settings;
  if (typeof settings !== "object" || settings === null || Array.isArray(settings)) {
    throw new PresetFileError("Not a PyMappr preset file.");
  }
  const version = Math.trunc(Number(doc.format_version ?? 1));
  if (Number.isNaN(version)) throw new PresetFileError("Not a PyMappr preset file.");
  if (version > PRESET_FORMAT_VERSION) {
    throw new PresetFileError(
      `This preset was saved by a newer PyMappr (${String(doc.app_version ?? "?")}). Update PyMappr to use it.`,
    );
  }
  const base = path.replace(/\\/g, "/").split("/").pop() ?? "";
  const name = doc.name ? String(doc.name) : base.endsWith(PRESET_EXTENSION) ? base.slice(0, -PRESET_EXTENSION.length) : base;
  return { name, settings: settings as PresetSettings };
}

const COLUMN_FIELDS: [keyof DatasetStyle, string][] = [
  ["group_by", "Group by"],
  ["color_by", "Color by"],
  ["symbol_by", "Symbol by"],
  ["open_by", "Open symbols for"],
];

/** A dataset with a preset's dataset style applied. A choice naming a
 * column the dataset lacks is left as it was and reported in `skipped`
 * (Group by “Genus Species”); legend-row edits merge in, the preset's
 * winning. PyMappr's `apply_dataset_style`. */
export function applyDatasetStyle(entry: DatasetEntry, style: Partial<DatasetStyle> | null | undefined): { entry: DatasetEntry; skipped: string[] } {
  const out: DatasetEntry = { ...entry, legend_overrides: { ...entry.legend_overrides }, open_values: [...entry.open_values] };
  if (!style || Object.keys(style).length === 0) return { entry: out, skipped: [] };
  const labels = new Set(entry.name_labels);
  const skipped: string[] = [];
  for (const [field, title] of COLUMN_FIELDS) {
    if (!(field in style)) continue;
    const value = style[field] ? String(style[field]) : "";
    if (value && !labels.has(value)) {
      skipped.push(`${title} “${value}”`);
      continue;
    }
    (out as Record<string, unknown>)[field] = value;
    if (field === "open_by") out.open_values = value ? (style.open_values ?? []).map(String) : [];
  }
  if ("vary_symbols" in style) out.vary_symbols = Boolean(style.vary_symbols);
  for (const [key, override] of Object.entries(style.legend_overrides ?? {})) {
    if (override && typeof override === "object" && !Array.isArray(override)) {
      out.legend_overrides[key] = { ...(out.legend_overrides[key] ?? {}), ...override };
    }
  }
  return { entry: out, skipped };
}

/** The settings half of a state put back as PyMappr's `_apply_settings`
 * does: map, legend and point settings from `settings` over the DEFAULTS
 * (not over the current state). */
export function applySettings(state: ProjectState, settings: Record<string, unknown>): ProjectState {
  const d = defaultState();
  const merged = withDefaults({ map: settings.map as ProjectState["map"] });
  const legendRaw = typeof settings.legend === "object" && settings.legend ? (settings.legend as Record<string, unknown>) : {};
  const edge = (typeof settings.point_edge === "object" && settings.point_edge ? settings.point_edge : {}) as Record<string, unknown>;
  const width = Number(edge.width ?? d.point_edge.width);
  return {
    ...state,
    map: merged.map,
    legend: legendFromDict({ ...d.legend, ...legendRaw }),
    point_alpha: settings.point_alpha === undefined ? d.point_alpha : Number(settings.point_alpha),
    point_edge: { color: String(edge.color || "#ffffff"), width: Number.isNaN(width) ? 0.5 : width },
  };
}

const framing = (s: ProjectState) => [s.map.projection, s.map.proj_lon0, s.map.proj_lat0, s.map.orientation].join("\x00");

export type PresetResult = {
  state: ProjectState;
  /** False when the preset reprojected or reoriented the map: zoom to the
   * data rather than keeping the view. */
  keepView: boolean;
  status: string;
  /** What did not carry over, one note per dataset and column. */
  skipped: string[];
};

/** Apply a saved preset to a project (PyMappr's `on_apply_preset`). */
export function applyPreset(state: ProjectState, name: string, settings: PresetSettings): PresetResult {
  const skipped: string[] = [];
  const datasets = state.datasets.map((entry) => {
    const result = applyDatasetStyle(entry, settings.dataset ?? {});
    skipped.push(...result.skipped.map((what) => `${what} is not a column in ${entry.name}`));
    return result.entry;
  });
  const applied = applySettings({ ...state, datasets }, settings);
  const keepView = framing(applied) === framing(state);
  let status = `Applied the preset “${name}”.`;
  if (skipped.length) status += " Not applied: " + skipped.join("; ") + ".";
  return { state: applied, keepView, status, skipped };
}

/** The built-in Standard preset for a journal figure (PyMappr's
 * `on_publication_style`): black-and-white varied symbols with black
 * outlines, a plain boxed italic legend sorted A–Z and shaded by genus,
 * holotypes as open symbols, 600 DPI at 17 cm. Rows styled by hand, a
 * manual order and a chosen Color by are kept. */
export function applyStandardPreset(state: ProjectState): { state: ProjectState; status: string } {
  let legend = { ...state.legend, ...PUBLICATION_LEGEND } as ProjectState["legend"];
  if (!(legend.title ?? "").trim()) legend = { ...legend, show_title: false };
  const organised = organisePublicationLegend(state.datasets, legend);
  const datasets = organised.entries.map((entry) => {
    const out = { ...entry, vary_symbols: true };
    const marking = entry.open_by ? null : holotypeMarking(entry);
    if (marking) {
      out.open_by = marking[0];
      out.open_values = [marking[1]];
    }
    return out;
  });
  return {
    state: {
      ...state,
      datasets,
      legend: organised.options,
      map: { ...state.map, palette: BLACK_AND_WHITE_NAME, dpi: PUBLICATION_DPI, export_width: PUBLICATION_WIDTH },
      point_edge: { ...PUBLICATION_POINT_EDGE },
      point_alpha: 1.0,
    },
    status:
      `Applied the ${BUILT_IN_PRESET} preset. Export with File → Save map as ` +
      `(${PUBLICATION_DPI} DPI, 17 cm wide).`,
  };
}

/** The preset dropdown: Standard first (unless deleted), then the user's
 * presets as listed (A–Z). */
export function presetChoices(userPresets: { name: string }[], builtInDeleted: boolean): string[] {
  return [...(builtInDeleted ? [] : [BUILT_IN_PRESET]), ...userPresets.map((p) => p.name)];
}

/** Why a name cannot be saved as a preset, or null. */
export function presetNameProblem(name: string, builtInDeleted: boolean): string | null {
  if (!name.trim()) return "Give the preset a name.";
  if (name.trim() === BUILT_IN_PRESET && !builtInDeleted) {
    return `That name belongs to the built-in ${BUILT_IN_PRESET} preset. Choose another.`;
  }
  return null;
}

/** The overwrite question for an existing preset. */
export function presetOverwriteQuestion(name: string): string {
  return `A preset named “${name}” already exists. Overwrite it?`;
}

/** The status after saving a preset. */
export function presetSavedStatus(name: string): string {
  return `Saved the preset “${name}”. Apply it in any project from the Data tab.`;
}
