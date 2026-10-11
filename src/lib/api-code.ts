// Commands for the Python/R code export and the AI check
// (src-tauri/src/cmd_code.rs, crates/mappr-codegen, src-tauri/src/llm.rs).
import { call } from "./api";
import type { ProjectState } from "./model";

export type CodeLanguage = "Python" | "R";

/** How a single-file script carries the point data: every row, a
 * `__RUSTYMAPPR_DATA_<i>__` placeholder per dataset, or the first N rows. */
export type DataMode = "embedded" | "placeholder" | `head:${number}`;

/** What only the renderer knows. `insetExport` is the dict PyMappr's
 * `MapRenderer.inset_export()` returns (its fields are documented on
 * `ExportOptions` in crates/mappr-codegen/src/config.rs), or null when
 * there is no inset. */
export type RendererInfo = { insetExport: Record<string, unknown> | null };

/** Everything an export needs besides the language. */
export type ExportInput = {
  /** The project state exactly as saved (no `inset_export` needed in it). */
  state: ProjectState | Record<string, unknown>;
  /** The exported map size in inches, [width, height]; null for PyMappr's
   * default 9 × 6.5 in canvas. Only the width really matters: the height
   * follows from the view. */
  figureSize: [number, number] | null;
  renderer?: RendererInfo | null;
  /** Used in the script's title, README and .Rproj name. */
  projectName?: string;
};

export type GeneratedCode = { code: string; lines: number; notes: string[] };

export type WorkdirResult = {
  /** Files written (relative paths). Empty when files existed and
   * `overwrite` was false: then nothing was written. */
  written: string[];
  existing: string[];
};

export type SendOptions = {
  columns: boolean;
  firstRows: boolean;
  /** How many rows "First N rows" sends (default 5). */
  rows: number | null;
  mapImage: boolean;
  fullData: boolean;
};

export type ModelInfo = { id: string; author: string; name: string | null; inputModalities: string[] };

export type LlmPrefs = {
  model: string;
  send: SendOptions;
  presets: string[];
  defaultModel: string;
  /** The cached full catalog, or null until "Load all models". */
  models: ModelInfo[] | null;
  keyUrl: string;
};

export type KeyStatus = { set: boolean; hint: string | null };

export type CheckRequest = ExportInput & {
  /** The script as shown in the export dialog (data embedded). */
  code: string;
  language: CodeLanguage;
  model: string;
  send: SendOptions;
  /** PNG data URL of the map; sent only with `send.mapImage`. */
  mapImage?: string | null;
};

export type CheckPreview = {
  url: string;
  /** The exact JSON body that would be POSTed. */
  payload: { model: string; messages: unknown[] };
  chars: number;
  approxTokens: number;
  dataMode: DataMode;
  /** Datasets whose data could not be held back (the check refuses). */
  unmatched: number[];
};

export type CheckResult = {
  model: string;
  /** The suggested script with the real data put back, or null. */
  code: string | null;
  changes: string[];
  noChanges: boolean;
  /** Reply text outside the code block. */
  notes: string;
  finishReason: string | null;
  restored: number[];
  /** Datasets whose placeholder the reply lost: their data is missing. */
  missing: number[];
};

export const DEFAULT_SEND: SendOptions = { columns: false, firstRows: false, rows: 5, mapImage: false, fullData: false };

export const codeApi = {
  generate: (input: ExportInput, language: CodeLanguage, dataMode: DataMode = "embedded") =>
    call<GeneratedCode>("code_generate", { ...input, language, dataMode }),
  save: (path: string, code: string) => call<void>("code_save", { path, code }),
  workdir: (folder: string, input: ExportInput, language: CodeLanguage, overwrite: boolean) =>
    call<WorkdirResult>("code_workdir", { ...input, folder, language, overwrite }),
  restore: (code: string, state: ExportInput["state"], language: CodeLanguage, dataMode: DataMode) =>
    call<{ code: string; restored: number[]; missing: number[] }>("code_restore", { code, state, language, dataMode }),

  keyStatus: () => call<KeyStatus>("llm_key_status"),
  /** Stores the key in the OS credential store; it never comes back. */
  keySet: (key: string) => call<KeyStatus>("llm_key_set", { key }),
  keyClear: () => call<void>("llm_key_clear"),
  prefs: () => call<LlmPrefs>("llm_prefs"),
  setPrefs: (patch: { model?: string; send?: SendOptions }) => call<LlmPrefs>("llm_prefs_set", patch),
  /** Fetches OpenRouter's catalog and caches it. */
  refreshModels: () => call<ModelInfo[]>("llm_models_refresh"),
  preview: (request: CheckRequest) => call<CheckPreview>("llm_preview", request),
  /** Starts the check; returns a job id to poll with `api.jobStatus`, whose
   * `result` is a CheckResult once done. */
  check: (request: CheckRequest) => call<number>("llm_check", request),
};

/** `# Revised with AI assistance (<model>, <date>). Review before relying on it.`
 * above the script, after a Python shebang so it still runs directly. */
export function withRevisionHeader(code: string, model: string, date = new Date()): string {
  const day = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const header = `# Revised with AI assistance (${model.replace(/[\r\n]+/g, " ")}, ${day}). Review before relying on it.\n`;
  if (code.startsWith("#!")) {
    const eol = code.indexOf("\n");
    if (eol >= 0) return code.slice(0, eol + 1) + header + code.slice(eol + 1);
  }
  return header + code;
}
