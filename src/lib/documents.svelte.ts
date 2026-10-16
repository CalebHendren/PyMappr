// Project files: new, open, save, save as, import, export, the projects
// folder, and the session saved on exit and restored at launch, as PyMappr's
// File menu does (pymappr/handlers/project_files.py).
import { confirmDialog, pickFile, pickFolder, saveFile } from "./api";
import { docs } from "./api-docs";
import { defaultState } from "./model";
import { parseProject, parseSession, projectNameFromPath, serializeProject, serializeSession, UNTITLED } from "./project";
import { store } from "./store.svelte";

const FILTERS = [{ name: "PyMappr project", extensions: ["pymappr"] }];

class Documents {
  /** Asks the page for a project name (Save as); resolves null on cancel. */
  askName: ((title: string, initial: string) => Promise<string | null>) | null = null;

  private version() {
    return store.info?.version ?? "0.0.0";
  }

  /** Offer to save unsaved changes. Resolves false when the user cancels. */
  async settleUnsaved(): Promise<boolean> {
    if (!store.dirty) return true;
    if (await confirmDialog(`Save the changes to "${store.projectName}" first?`, "Unsaved changes")) {
      return this.save();
    }
    return confirmDialog("Discard the unsaved changes?", "Unsaved changes");
  }

  async newProject() {
    if (!(await this.settleUnsaved())) return;
    store.load(defaultState(), UNTITLED, null);
    store.setStatus("New project.");
  }

  async open(path: string) {
    if (!(await this.settleUnsaved())) return;
    try {
      const { name, state } = parseProject(await docs.readProject(path), path);
      store.load(state, name, path);
      store.setStatus(`Opened ${name}.`);
    } catch (e) {
      // A broken file leaves the current project as it was.
      store.fail(e);
    }
  }

  async save(): Promise<boolean> {
    if (!store.projectPath) return this.saveAs();
    return this.writeTo(store.projectPath, store.projectName);
  }

  async saveAs(): Promise<boolean> {
    const name = await this.askName?.("Save project as", store.projectName === UNTITLED ? "" : store.projectName);
    if (!name) return false;
    const { path, exists } = await docs.projectPath(name);
    if (exists && path !== store.projectPath && !(await confirmDialog(`A project named "${name}" already exists. Replace it?`))) return false;
    return this.writeTo(path, name);
  }

  private async writeTo(path: string, name: string): Promise<boolean> {
    try {
      store.syncViewToDoc();
      await docs.writeProject(path, serializeProject(name, $state.snapshot(store.doc), this.version()));
      store.markSaved(name, path);
      store.setStatus(`Saved ${name}.`);
      return true;
    } catch (e) {
      store.fail(e);
      return false;
    }
  }

  async importProject() {
    const source = await pickFile("Import project", FILTERS);
    if (!source) return;
    try {
      const copy = await docs.importProject(source);
      await this.open(copy);
    } catch (e) {
      store.fail(e);
    }
  }

  async exportProject() {
    const path = await saveFile("Export project", `${store.projectName}.pymappr`, FILTERS);
    if (!path) return;
    try {
      store.syncViewToDoc();
      await docs.writeProject(path, serializeProject(store.projectName, $state.snapshot(store.doc), this.version()));
      store.setStatus(`Exported a copy to ${path}.`);
    } catch (e) {
      store.fail(e);
    }
  }

  async setProjectsFolder() {
    const folder = await pickFolder("Projects folder");
    if (!folder) return;
    try {
      store.setStatus(`Projects are saved in ${await docs.setProjectsDir(folder)}.`);
    } catch (e) {
      store.fail(e);
    }
  }

  /** After the projects manager renamed or deleted the open project. */
  followChanges(changes: { renamed: Record<string, string>; deleted: string[] }) {
    const path = store.projectPath;
    if (!path) return;
    if (changes.renamed[path]) {
      const next = changes.renamed[path];
      store.projectPath = next;
      store.projectName = projectNameFromPath(next);
    } else if (changes.deleted.includes(path)) {
      // The file is gone: the project now only exists unsaved.
      store.projectPath = null;
      store.saved = "";
    }
  }

  // ---- the session ---------------------------------------------------------

  async saveSession() {
    try {
      store.syncViewToDoc();
      const text = serializeSession(
        $state.snapshot(store.doc),
        {
          projectPath: store.projectPath ?? "",
          projectName: store.projectName,
          geometry: `${window.outerWidth}x${window.outerHeight}`,
          unsaved: store.dirty,
        },
        this.version(),
      );
      await docs.writeSession(text);
    } catch {
      // Losing the session is not worth an error on the way out.
    }
  }

  async restoreSession() {
    try {
      const text = await docs.readSession();
      if (!text) return;
      const s = parseSession(text);
      const path = s.projectPath && (await docs.pathExists(s.projectPath)) ? s.projectPath : null;
      store.load(s.state, s.projectName, path);
      // Unsaved changes stay unsaved across a restart.
      if (s.unsaved) store.saved = "";
      store.setStatus("Restored your previous session.");
    } catch {
      // A damaged session file just means a fresh start.
    }
  }
}

export const documents = new Documents();
