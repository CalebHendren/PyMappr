<script module lang="ts">
  export type ProjectChanges = { renamed: Record<string, string>; deleted: string[] };
</script>

<script lang="ts">
  // "Projects": open, rename or delete the projects in the projects folder,
  // newest first (PyMappr's ui/projects_dialog.py). On closing it reports
  // what changed on disk, so the caller can keep the open project's path in
  // step: `renamed` maps an original path to its final one (chains
  // collapsed), `deleted` lists original paths.
  import { onMount } from "svelte";
  import { confirmDialog, pickFolder } from "$lib/api";
  import { docs, type ProjectListing } from "$lib/api-docs";
  import DialogFrame from "./DialogFrame.svelte";

  let {
    onopen,
    onClose,
    backend = docs,
    confirm = confirmDialog,
    chooseFolder = pickFolder,
  }: {
    /** A project chosen to open (after onClose's changes are reported). */
    onopen: (path: string, changes: ProjectChanges) => void;
    /** Closed without opening anything. */
    onClose: (changes: ProjectChanges) => void;
    backend?: Pick<typeof docs, "projectsDir" | "listProjects" | "renameProject" | "deleteProject" | "setProjectsDir">;
    confirm?: (message: string, title?: string) => Promise<boolean>;
    chooseFolder?: (title: string) => Promise<string | null>;
  } = $props();

  let folder = $state("");
  let projects = $state<ProjectListing[]>([]);
  let selected = $state<string | null>(null);
  let renaming = $state<string | null>(null);
  let newName = $state("");
  let error = $state("");
  const renamed: Record<string, string> = {};
  const deleted: string[] = [];
  const changes = (): ProjectChanges => ({ renamed: { ...renamed }, deleted: [...deleted] });

  /** "YYYY-MM-DD HH:MM", local time. */
  function stamp(ms: number): string {
    const d = new Date(ms);
    const p = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  async function refresh(keep: string | null = null) {
    try {
      folder = await backend.projectsDir();
      projects = await backend.listProjects(folder);
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
      projects = [];
    }
    selected = projects.find((p) => p.path === keep)?.path ?? projects[0]?.path ?? null;
  }

  onMount(() => {
    refresh();
  });

  const current = $derived(projects.find((p) => p.path === selected) ?? null);

  function open(path = selected) {
    if (path) onopen(path, changes());
  }

  function recordRename(old: string, now: string) {
    if (old === now) return;
    const origin = Object.keys(renamed).find((k) => renamed[k] === old);
    if (origin !== undefined) renamed[origin] = now;
    else renamed[old] = now;
  }

  function recordDelete(path: string) {
    const origin = Object.keys(renamed).find((k) => renamed[k] === path);
    if (origin !== undefined) {
      delete renamed[origin];
      path = origin;
    }
    deleted.push(path);
  }

  function startRename() {
    if (!current) return;
    renaming = current.path;
    newName = current.name;
    error = "";
  }

  async function finishRename() {
    const project = projects.find((p) => p.path === renaming);
    renaming = null;
    if (!project || !newName.trim() || newName.trim() === project.name) return;
    let target = project.path;
    try {
      target = await backend.renameProject(project.path, newName.trim());
      recordRename(project.path, target);
      error = "";
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
    }
    await refresh(target);
  }

  async function remove() {
    if (!current) return;
    const ok = await confirm(`Delete the project “${current.name}”?\n\nThis cannot be undone.`, "Delete project");
    if (!ok) return;
    try {
      await backend.deleteProject(current.path);
      recordDelete(current.path);
      error = "";
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
    }
    await refresh();
  }

  async function changeFolder() {
    const chosen = await chooseFolder("Choose the folder to save projects in");
    if (!chosen) return;
    try {
      await backend.setProjectsDir(chosen);
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
    }
    await refresh();
  }

  function keys(e: KeyboardEvent) {
    if (renaming) return;
    const at = projects.findIndex((p) => p.path === selected);
    if (e.key === "ArrowDown" && at < projects.length - 1) selected = projects[at + 1].path;
    else if (e.key === "ArrowUp" && at > 0) selected = projects[at - 1].path;
    else if (e.key === "Enter") open();
    else return;
    e.preventDefault();
  }
</script>

<DialogFrame title="Projects" onClose={() => onClose(changes())} width="w-[min(560px,92vw)]">
  <div class="mb-2 flex items-center gap-2">
    <p class="min-w-0 flex-1 truncate text-[12px] text-muted" title={folder}>Projects folder: {folder}</p>
    <button class="btn border border-line" onclick={changeFolder}>Change…</button>
  </div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="max-h-80 overflow-y-auto rounded-md border border-line bg-raised" tabindex="0" role="listbox" aria-label="Projects" onkeydown={keys}>
    <table class="w-full border-collapse text-[13px]">
      <thead class="sticky top-0 bg-raised">
        <tr class="text-left text-[12px] text-muted">
          <th class="px-2 py-1 font-semibold">Project</th>
          <th class="w-40 px-2 py-1 font-semibold">Last saved</th>
        </tr>
      </thead>
      <tbody>
        {#each projects as project (project.path)}
          <tr
            class="cursor-default border-t border-line/60"
            class:bg-accent-soft={project.path === selected}
            role="option"
            aria-selected={project.path === selected}
            onclick={() => (selected = project.path)}
            ondblclick={() => open(project.path)}
          >
            <td class="px-2 py-1">
              {#if renaming === project.path}
                <!-- svelte-ignore a11y_autofocus -->
                <input
                  class="field"
                  autofocus
                  bind:value={newName}
                  onkeydown={(e) => {
                    if (e.key === "Enter") finishRename();
                    if (e.key === "Escape") {
                      e.stopPropagation();
                      e.preventDefault();
                      renaming = null;
                    }
                  }}
                  onblur={finishRename}
                />
              {:else}
                {project.name}
              {/if}
            </td>
            <td class="px-2 py-1 tabular-nums text-muted">{stamp(project.modified)}</td>
          </tr>
        {:else}
          <tr><td colspan="2" class="px-2 py-3 text-muted">No projects saved yet.</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if error}
    <p class="mt-2 text-[13px] text-danger" role="alert">{error}</p>
  {/if}
  {#snippet actions()}
    <button class="btn-primary" disabled={!current} onclick={() => open()}>Open</button>
    <button class="btn border border-line" disabled={!current} onclick={startRename}>Rename…</button>
    <button class="btn border border-line" disabled={!current} onclick={remove}>Delete</button>
    <span class="flex-1"></span>
    <button class="btn border border-line" onclick={() => onClose(changes())}>Close</button>
  {/snippet}
</DialogFrame>
