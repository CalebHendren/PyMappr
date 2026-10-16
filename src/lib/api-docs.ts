// Typed wrappers for the document commands in src-tauri/src/cmd_docs.rs:
// projects, presets, the session file and manual point entry.
import { call } from "./api";
import type { PresetSettings } from "./presets";

export type ProjectListing = {
  /** File name without ".pymappr", as the Projects dialog shows it. */
  name: string;
  path: string;
  /** Last modified, ms since 1970 ("Last saved"). */
  modified: number;
};

export type PresetListing = { name: string; path: string };

/** Typed-in points as the backend parsed them (PyMappr's
 * `build_manual_dataset`). */
export type ManualParse = {
  columns: string[];
  nameLabels: string[];
  rows: (string | number)[][];
  skipped: string[];
};

export const docs = {
  /** The projects folder (created if missing). */
  projectsDir: () => call<string>("projects_dir"),
  /** Choose the projects folder; returns the folder now in use. */
  setProjectsDir: (path: string) => call<string>("projects_dir_set", { path }),
  /** Projects in the folder (the projects folder by default), newest first. */
  listProjects: (folder?: string) => call<ProjectListing[]>("projects_list", { folder: folder ?? null }),
  /** Where a project of this name is saved, and whether one is already. */
  projectPath: (name: string) => call<{ path: string; exists: boolean }>("project_path", { name }),
  readProject: (path: string) => call<string>("project_read", { path }),
  writeProject: (path: string, text: string) => call<void>("project_write", { path, text }),
  /** Rename a project file; returns its new path. Fails when the name is taken. */
  renameProject: (path: string, newName: string) => call<string>("project_rename", { path, newName }),
  deleteProject: (path: string) => call<void>("project_delete", { path }),
  /** Copy a project into the projects folder ("name (2)" when taken); returns the copy. */
  importProject: (source: string) => call<string>("project_import", { source }),
  sessionPath: () => call<string>("session_path"),
  /** The autosaved session's text, or null when there is none. */
  readSession: () => call<string | null>("session_read"),
  writeSession: (text: string) => call<void>("session_write", { text }),
  presetsDir: () => call<string>("presets_dir"),
  /** Readable presets, A–Z by name. */
  listPresets: () => call<PresetListing[]>("presets_list"),
  presetPath: (name: string) => call<{ path: string; exists: boolean }>("preset_path", { name }),
  /** A preset file, checked; fails with PyMappr's message when it is not one. */
  readPreset: (path: string) => call<{ name: string; settings: PresetSettings }>("preset_read", { path }),
  writePreset: (path: string, text: string) => call<void>("preset_write", { path, text }),
  deletePreset: (path: string) => call<void>("preset_delete", { path }),
  builtInPresetDeleted: () => call<boolean>("presets_builtin_deleted"),
  /** Hide the built-in Standard preset for good. */
  deleteBuiltInPreset: () => call<void>("presets_delete_builtin"),
  pathExists: (path: string) => call<boolean>("path_exists", { path }),
  /** Parse typed coordinate lines ("lat,lon" or "lon,lat"). */
  parseManual: (legend: string, text: string, order: "lat,lon" | "lon,lat") =>
    call<ManualParse>("parse_manual", { legend, text, order }),
};
