// Project documents: reading and writing .pymappr files exactly as PyMappr
// does (pymappr/files/projects.py and the state half of
// pymappr/handlers/state.py), so a project moves freely between the apps.
// File access is the backend's (api-docs.ts); this module is the format.

import { PROJECT_FORMAT, PROJECT_FORMAT_VERSION, type DatasetEntry, type LegendOptions, type ProjectState, type RowOverride, defaultState, withDefaults } from "./model";

export const PROJECT_EXTENSION = ".pymappr";
export const UNTITLED = "Untitled";

/** A project file that cannot be read, with PyMappr's wording. */
export class ProjectFileError extends Error {}

// ------------------------------------------------------------ Python JSON

/** JSON.parse that also takes the NaN and Infinity Python's json writes;
 * they come back as NaN / ±Infinity. */
export function parsePythonJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch (first) {
    // Swap bare NaN/Infinity tokens (never those inside strings) for
    // placeholders, then put the numbers back.
    const tokens = { NaN: "__pymappr_nan__", Infinity: "__pymappr_inf__", "-Infinity": "__pymappr_ninf__" };
    let changed = false;
    const patched = text.replace(/"(?:[^"\\]|\\.)*"|-?Infinity|NaN/g, (match) => {
      if (match.startsWith('"')) return match;
      changed = true;
      return `"${tokens[match as keyof typeof tokens]}"`;
    });
    if (!changed) throw first;
    const values: Record<string, number> = {
      __pymappr_nan__: NaN,
      __pymappr_inf__: Infinity,
      __pymappr_ninf__: -Infinity,
    };
    return JSON.parse(patched, (_key, value) => (typeof value === "string" && value in values ? values[value] : value));
  }
}

function quote(text: string): string {
  return JSON.stringify(text).replace(/[\u007f-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
}

/** JSON as Python's `json.dumps` writes it: ", " and ": " separators,
 * non-ASCII escaped, NaN and Infinity as bare words. */
export function pythonJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "NaN";
    if (!Number.isFinite(value)) return value > 0 ? "Infinity" : "-Infinity";
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return quote(value);
  if (Array.isArray(value)) return "[" + value.map(pythonJson).join(", ") + "]";
  if (typeof value === "object") {
    const parts = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${quote(k)}: ${pythonJson(v)}`);
    return "{" + parts.join(", ") + "}";
  }
  return "null";
}

/** `time.strftime("%Y-%m-%dT%H:%M:%S")`: local time, no zone. */
export function localTimestamp(now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}` +
    `T${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`
  );
}

// Python's str() and bool() of what json gives back.
function pyStr(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "number" && Number.isInteger(value) && !Object.is(value, -0)) return String(value);
  return String(value);
}

function pyBool(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return Boolean(value);
}

function isDict(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// ---------------------------------------------------------------- filenames

const RESERVED_FILENAMES = new Set([
  "con",
  "prn",
  "aux",
  "nul",
  ...Array.from({ length: 9 }, (_, i) => `com${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `lpt${i + 1}`),
]);

/** A filesystem-safe version of a typed project name (PyMappr's
 * `safe_filename`): reserved characters become "_", a Windows device name
 * gets "_" after it, and a blank name is "Untitled". */
export function safeFilename(name: string): string {
  let cleaned = [...name.trim()].map((ch) => ('<>:"/\\|?*'.includes(ch) || ch.charCodeAt(0) < 32 ? "_" : ch)).join("");
  cleaned = cleaned.replace(/^[. ]+|[. ]+$/g, "") || "Untitled";
  const dot = cleaned.indexOf(".");
  const first = dot < 0 ? cleaned : cleaned.slice(0, dot);
  if (RESERVED_FILENAMES.has(first.trim().toLowerCase())) {
    cleaned = dot < 0 ? `${first.trimEnd()}_` : `${first.trimEnd()}_${cleaned.slice(dot)}`;
  }
  return cleaned;
}

// ---------------------------------------------------------------- datasets

const OVERRIDE_FIELDS = ["label", "hidden", "order", "color", "marker", "size"] as const;
const GROUP_PREFIX = "group\x00";

/** The pinned group styles in the form older PyMappr builds read. */
export function legacyStyles(overrides: Record<string, RowOverride>): Record<string, { color: string; marker: string; size: number }> {
  const out: Record<string, { color: string; marker: string; size: number }> = {};
  for (const [key, o] of Object.entries(overrides)) {
    if (!key.startsWith(GROUP_PREFIX) || !(o.color || o.marker || o.size)) continue;
    out[key.slice(GROUP_PREFIX.length)] = {
      color: o.color || "#d62728",
      marker: o.marker || "Circle",
      size: Number(o.size || 30.0),
    };
  }
  return out;
}

/** Read the per-row legend customisations, migrating a project saved
 * before they existed (only "styles", keyed by group label). */
export function overridesFromDict(data: Record<string, unknown>): Record<string, RowOverride> {
  const overrides: Record<string, RowOverride> = {};
  if (!("legend_overrides" in data)) {
    const styles = isDict(data.styles) ? data.styles : {};
    for (const [label, raw] of Object.entries(styles)) {
      if (!isDict(raw)) continue;
      const size = Number(raw.size ?? 30.0);
      if (Number.isNaN(size) && typeof raw.size !== "number") continue;
      overrides[GROUP_PREFIX + label] = {
        color: pyStr(raw.color ?? "#d62728"),
        marker: pyStr(raw.marker ?? "Circle"),
        size,
      };
    }
  }
  const stored = isDict(data.legend_overrides) ? data.legend_overrides : {};
  for (const [key, raw] of Object.entries(stored)) {
    if (!isDict(raw)) continue;
    const kept: Record<string, unknown> = {};
    for (const field of OVERRIDE_FIELDS) if (raw[field] !== null && raw[field] !== undefined) kept[field] = raw[field];
    if (Object.keys(kept).length) overrides[key] = { ...(overrides[key] ?? {}), ...(kept as RowOverride) };
  }
  return overrides;
}

/** A dataset as a project stores it (PyMappr's `entry_to_dict`), with the
 * legacy "styles" copy for older builds. */
export function entryToDict(entry: DatasetEntry): DatasetEntry {
  return {
    name: entry.name,
    visible: entry.visible,
    source_path: entry.source_path,
    columns: entry.columns.map(String),
    name_labels: [...entry.name_labels],
    rows: entry.rows.map((row) => row.map((v) => (typeof v === "number" ? v : v === null || v === undefined ? (v as never) : String(v)))),
    group_by: entry.group_by,
    color_by: entry.color_by,
    symbol_by: entry.symbol_by,
    vary_symbols: entry.vary_symbols,
    open_by: entry.open_by,
    open_values: [...entry.open_values],
    styles: legacyStyles(entry.legend_overrides),
    legend_overrides: Object.fromEntries(Object.entries(entry.legend_overrides).map(([k, v]) => [k, { ...v }])),
    manual: entry.manual,
  };
}

function toNumber(value: unknown): number {
  if (typeof value === "number") return value;
  if (typeof value === "boolean") return Number(value);
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value.trim());
    return Number.isNaN(n) ? NaN : n;
  }
  return NaN;
}

/** A stored dataset, read back as PyMappr's `entry_from_dict` reads it. */
export function entryFromDict(data: Record<string, unknown>): DatasetEntry {
  const columns = (Array.isArray(data.columns) ? data.columns : []).map(pyStr);
  const coords = ["lon", "lat"].map((c) => columns.indexOf(c)).filter((i) => i >= 0);
  const rows = (Array.isArray(data.rows) ? data.rows : []).map((raw) => {
    const row = (Array.isArray(raw) ? [...raw] : []) as (string | number)[];
    for (const i of coords) row[i] = toNumber(row[i]);
    return row;
  });
  const manual = isDict(data.manual) ? ({ ...data.manual } as DatasetEntry["manual"]) : null;
  return {
    name: pyStr(data.name ?? "Dataset"),
    visible: pyBool(data.visible ?? true),
    source_path: pyStr(data.source_path ?? ""),
    columns,
    name_labels: (Array.isArray(data.name_labels) ? data.name_labels : []).map(pyStr),
    rows,
    group_by: pyStr(data.group_by ?? ""),
    color_by: pyStr(data.color_by ?? ""),
    symbol_by: pyStr(data.symbol_by ?? ""),
    vary_symbols: pyBool(data.vary_symbols ?? false),
    open_by: pyStr(data.open_by || ""),
    open_values: (Array.isArray(data.open_values) ? data.open_values : []).map(pyStr),
    legend_overrides: overridesFromDict(data),
    manual,
  };
}

// ---------------------------------------------------------------- the state

/** LegendOptions read the way `LegendOptions.from_dict` reads them:
 * defaults for what is missing or unreadable, values coerced to the
 * field's type, unknown keys dropped (draggable and anchor are kept, as
 * the state stores them beside the options). */
export function legendFromDict(raw: Record<string, unknown>): LegendOptions {
  const defaults = defaultState().legend as unknown as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  const nullable = new Set(["title", "handle_text_pad"]);
  const ints = new Set(["indent", "columns"]);
  for (const [field, fallback] of Object.entries(defaults)) {
    if (field === "draggable" || field === "anchor") continue;
    if (!(field in raw)) {
      out[field] = fallback;
      continue;
    }
    const value = raw[field];
    if (value === null || value === undefined) {
      out[field] = nullable.has(field) ? null : fallback;
      continue;
    }
    if (typeof fallback === "boolean") {
      out[field] = typeof value === "string" ? ["1", "true", "yes", "on"].includes(value.trim().toLowerCase()) : pyBool(value);
    } else if (ints.has(field)) {
      const n = toNumber(value);
      out[field] = Number.isFinite(n) ? Math.trunc(n) : fallback;
    } else if (typeof fallback === "number" || field === "handle_text_pad") {
      const n = toNumber(value);
      out[field] = Number.isNaN(n) ? fallback : n;
    } else {
      out[field] = pyStr(value);
    }
  }
  out.draggable = pyBool(raw.draggable ?? false);
  const anchor = raw.anchor;
  out.anchor = Array.isArray(anchor) && anchor.length === 2 ? anchor.map(Number) : null;
  return out as LegendOptions;
}

/** A state as a project stores it, in the order PyMappr's `_collect_state`
 * writes it. */
export function stateToDict(state: ProjectState): Record<string, unknown> {
  return {
    datasets: state.datasets.map(entryToDict),
    active: state.active,
    map: state.map,
    legend: state.legend,
    point_alpha: state.point_alpha,
    point_edge: state.point_edge,
    view: state.view,
  };
}

/** A stored state put back as PyMappr's `_apply_state` does: datasets read,
 * the active one checked, settings merged over the defaults. */
export function stateFromDict(raw: Record<string, unknown>): ProjectState {
  const datasets = (Array.isArray(raw.datasets) ? raw.datasets : []).map((d) => entryFromDict(isDict(d) ? d : {}));
  let active = raw.active;
  if (!(typeof active === "number" && Number.isInteger(active) && active >= 0 && active < datasets.length)) {
    active = datasets.length ? 0 : null;
  }
  const merged = withDefaults({ ...(raw as Partial<ProjectState>), datasets });
  const edge = isDict(raw.point_edge) ? raw.point_edge : {};
  const width = toNumber(edge.width ?? 0.5);
  return {
    ...merged,
    datasets,
    active: active as number | null,
    legend: legendFromDict(isDict(raw.legend) ? { ...defaultState().legend, ...raw.legend } : {}),
    point_edge: { color: pyStr(edge.color || "#ffffff"), width: Number.isNaN(width) ? 0.5 : width },
  };
}

/** A comparable snapshot of a state, for telling whether it has unsaved
 * changes (PyMappr compares sorted-key JSON the same way). */
export function stateSnapshot(state: ProjectState): string {
  const sort = (value: unknown): unknown =>
    Array.isArray(value)
      ? value.map(sort)
      : isDict(value)
        ? Object.fromEntries(Object.keys(value).sort().map((k) => [k, sort(value[k])]))
        : value;
  return JSON.stringify(sort(stateToDict(state)));
}

// ---------------------------------------------------------------- documents

/** A project file's text (PyMappr's `save_project`). */
export function serializeProject(
  name: string,
  state: ProjectState | Record<string, unknown>,
  appVersion: string,
  now: Date = new Date(),
): string {
  const body = "datasets" in state && Array.isArray(state.datasets) && "map" in state ? stateToDict(state as ProjectState) : state;
  return pythonJson({
    format: PROJECT_FORMAT,
    format_version: PROJECT_FORMAT_VERSION,
    app_version: appVersion,
    name,
    saved_at: localTimestamp(now),
    state: body,
  });
}

function stem(path: string): string {
  const base = path.replace(/\\/g, "/").split("/").pop() ?? "";
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

/** The envelope of a project file, checked as PyMappr's `load_project`
 * checks it; returns the name and the raw stored state. */
export function readProjectDocument(text: string, path = ""): { name: string; state: Record<string, unknown>; document: Record<string, unknown> } {
  let document: unknown;
  try {
    document = parsePythonJson(text);
  } catch (exc) {
    throw new ProjectFileError(`Not a PyMappr project file: ${(exc as Error).message}`);
  }
  if (!isDict(document) || document.format !== PROJECT_FORMAT || !isDict(document.state)) {
    throw new ProjectFileError("Not a PyMappr project file.");
  }
  const version = Math.trunc(toNumber(document.format_version ?? 1));
  if (Number.isNaN(version)) throw new ProjectFileError("Not a PyMappr project file.");
  if (version > PROJECT_FORMAT_VERSION) {
    throw new ProjectFileError(
      `This project was saved by a newer PyMappr (${pyStr(document.app_version ?? "?")}). Update PyMappr to open it.`,
    );
  }
  const name = document.name ? pyStr(document.name) : stem(path);
  return { name, state: document.state, document };
}

/** Read a project file's text into a state ready to use. */
export function parseProject(text: string, path = ""): { name: string; state: ProjectState } {
  const { name, state } = readProjectDocument(text, path);
  return { name, state: stateFromDict(state) };
}

/** The project name a path gives (its file name without the extension). */
export function projectNameFromPath(path: string): string {
  return stem(path);
}

// ---------------------------------------------------------------- session

export type SessionInfo = {
  /** The open project's file, "" when it has none. */
  projectPath: string;
  projectName: string;
  /** Window geometry, as the shell stores it. */
  geometry: string;
  /** Unsaved changes stay unsaved across a restart. */
  unsaved: boolean;
};

/** The autosaved session (`session.pymappr`): the state plus where it came
 * from (PyMappr's `_save_session`). */
export function serializeSession(state: ProjectState, info: SessionInfo, appVersion: string, now: Date = new Date()): string {
  return serializeProject(
    info.projectName,
    {
      ...stateToDict(state),
      project_path: info.projectPath,
      project_name: info.projectName,
      geometry: info.geometry,
      unsaved: info.unsaved,
    },
    appVersion,
    now,
  );
}

/** Read the session back. `projectPath` is as stored; check it still
 * exists before treating the session as that project (PyMappr does). */
export function parseSession(text: string): { state: ProjectState } & SessionInfo {
  const { state } = readProjectDocument(text, "session.pymappr");
  return {
    state: stateFromDict(state),
    projectPath: state.project_path ? pyStr(state.project_path) : "",
    projectName: (state.project_name ? pyStr(state.project_name) : "") || UNTITLED,
    geometry: state.geometry ? pyStr(state.geometry) : "",
    unsaved: pyBool(state.unsaved),
  };
}
