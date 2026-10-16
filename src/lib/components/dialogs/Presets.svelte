<script lang="ts">
  // The Presets section of the Data tab (PyMappr's handlers/presets.py):
  // pick a preset — the built-in Standard first, then the user's A–Z — and
  // Apply it, save the current settings as a new one, or delete one.
  import { onMount } from "svelte";
  import { confirmDialog } from "$lib/api";
  import { docs, type PresetListing } from "$lib/api-docs";
  import type { ProjectState } from "$lib/model";
  import {
    BUILT_IN_PRESET,
    type PresetResult,
    applyPreset,
    applyStandardPreset,
    presetChoices,
    presetNameProblem,
    presetOverwriteQuestion,
    presetSavedStatus,
    serializePreset,
    settingsFromState,
  } from "$lib/presets";

  let {
    project,
    appVersion,
    onapply,
    onstatus,
    backend = docs,
    confirm = confirmDialog,
  }: {
    /** The project as it is now. */
    project: ProjectState;
    /** Written into saved presets (app_version). */
    appVersion: string;
    /** A preset was applied: adopt `result.state`; keep the view when
     * `result.keepView`, else zoom to the data; show `result.status`. */
    onapply: (result: PresetResult) => void;
    /** A status-bar message (saved, deleted). */
    onstatus?: (text: string) => void;
    backend?: Pick<
      typeof docs,
      "listPresets" | "builtInPresetDeleted" | "readPreset" | "presetPath" | "writePreset" | "deletePreset" | "deleteBuiltInPreset"
    >;
    confirm?: (message: string, title?: string) => Promise<boolean>;
  } = $props();

  let presets = $state<PresetListing[]>([]);
  let builtInDeleted = $state(false);
  let selected = $state("");
  let saving = $state(false);
  let saveName = $state("");
  let error = $state("");

  const choices = $derived(presetChoices(presets, builtInDeleted));
  const isBuiltIn = (name: string) => name === BUILT_IN_PRESET && !builtInDeleted;

  async function refresh(choose: string | null = null) {
    try {
      [presets, builtInDeleted] = await Promise.all([backend.listPresets(), backend.builtInPresetDeleted()]);
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
    }
    const names = presetChoices(presets, builtInDeleted);
    selected = choose !== null && names.includes(choose) ? choose : names.includes(selected) ? selected : (names[0] ?? "");
  }

  onMount(() => {
    refresh();
  });

  async function apply() {
    const name = selected;
    if (!name) return;
    error = "";
    if (isBuiltIn(name)) {
      const { state: next, status } = applyStandardPreset(project);
      onapply({ state: next, keepView: true, status, skipped: [] });
      return;
    }
    const path = presets.find((p) => p.name === name)?.path;
    try {
      if (!path) throw new Error(`No preset named '${name}'.`);
      const { settings } = await backend.readPreset(path);
      onapply(applyPreset(project, name, settings));
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
      await refresh();
    }
  }

  function startSave() {
    saveName = isBuiltIn(selected) ? "" : selected;
    saving = true;
    error = "";
  }

  async function save() {
    const name = saveName.trim();
    const problem = presetNameProblem(name, builtInDeleted);
    if (problem) {
      error = problem;
      return;
    }
    try {
      const { path, exists } = await backend.presetPath(name);
      if (exists && !(await confirm(presetOverwriteQuestion(name), "Save preset"))) return;
      const active = project.active === null ? null : (project.datasets[project.active] ?? null);
      await backend.writePreset(path, serializePreset(name, settingsFromState(project, active), appVersion));
      saving = false;
      error = "";
      await refresh(name);
      onstatus?.(presetSavedStatus(name));
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
    }
  }

  async function remove() {
    const name = selected;
    const builtIn = isBuiltIn(name);
    const path = presets.find((p) => p.name === name)?.path;
    if (!builtIn && !path) return;
    if (!(await confirm(`Delete the preset “${name}”?`, "Delete preset"))) return;
    try {
      if (builtIn) await backend.deleteBuiltInPreset();
      else await backend.deletePreset(path!);
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
    }
    await refresh();
  }
</script>

<div class="space-y-2">
  <div class="flex items-center gap-1.5">
    <select class="field min-w-0 flex-1" bind:value={selected} aria-label="Preset" disabled={!choices.length}>
      {#each choices as name (name)}
        <option value={name}>{name}</option>
      {/each}
    </select>
    <button class="btn-primary" disabled={!selected} onclick={apply}>Apply</button>
  </div>
  {#if saving}
    <form
      class="flex items-center gap-1.5"
      onsubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <!-- svelte-ignore a11y_autofocus -->
      <input class="field min-w-0 flex-1" placeholder="Preset name" aria-label="Preset name" autofocus bind:value={saveName} />
      <button class="btn-primary" type="submit">Save</button>
      <button class="btn" type="button" onclick={() => ((saving = false), (error = ""))}>Cancel</button>
    </form>
  {:else}
    <div class="flex gap-1.5">
      <button class="btn border border-line" onclick={startSave}>Save current as…</button>
      <button class="btn border border-line" disabled={!selected} onclick={remove}>Delete</button>
    </div>
  {/if}
  {#if error}
    <p class="text-[12px] text-danger" role="alert">{error}</p>
  {/if}
</div>
