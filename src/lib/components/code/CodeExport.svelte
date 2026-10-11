<script lang="ts">
  // Export the map as a Python or R script that recreates it (PyMappr's
  // "Export map as code" dialog), with an optional AI check of the script.
  import { Copy, FileCode, FolderDown, Sparkles } from "@lucide/svelte";
  import { api, confirmDialog, pickFolder, saveFile } from "$lib/api";
  import { codeApi, type CodeLanguage, type ExportInput } from "$lib/api-code";
  import Modal from "../Modal.svelte";
  import CodeAssist from "./CodeAssist.svelte";

  let {
    input,
    getMapImage,
    onClose,
  }: {
    /** The map to export: project state, figure size, renderer info, name. */
    input: ExportInput;
    /** A PNG data URL of the map as drawn, offered to the AI check. */
    getMapImage?: () => Promise<string | null>;
    onClose: () => void;
  } = $props();

  const NOTE =
    "The script downloads its base layers from Natural Earth, so you can open it in an IDE and click Run. " +
    "If a package it needs is missing, it prints the command to install it (or run it with --install-deps to " +
    "install them for you). Save a single self-contained file, or a whole runnable project folder.";
  const LABELS: Record<CodeLanguage, string> = { Python: "Python", R: "R (best effort)" };

  let language = $state<CodeLanguage | null>(null);
  let code = $state("");
  let notes = $state<string[]>([]);
  let revised = $state(false);
  let status = $state("");
  let error = $state(false);
  let assisting = $state(false);

  const lines = $derived(code ? code.split("\n").length - (code.endsWith("\n") ? 1 : 0) : 0);
  const extension = $derived(language === "R" ? ".R" : ".py");

  $effect(() => {
    (async () => {
      let stored: unknown = null;
      try {
        stored = (await api.settings()).codeExportLanguage;
      } catch {
        // Settings are a convenience.
      }
      language = stored === "R" ? "R" : "Python";
    })();
  });

  async function refresh(lang: CodeLanguage) {
    status = "Generating…";
    error = false;
    try {
      const generated = await codeApi.generate(input, lang);
      code = generated.code;
      notes = generated.notes;
      revised = false;
      status = `${lang} · ${generated.lines} lines`;
    } catch (e) {
      status = `Could not generate code: ${e}`;
      error = true;
    }
  }

  $effect(() => {
    if (language) void refresh(language);
  });

  async function pick(lang: CodeLanguage) {
    if (lang === language) return;
    if (revised && !(await confirmDialog("Switching language drops the AI-revised script. Switch anyway?"))) return;
    language = lang;
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      status = "Code copied to the clipboard.";
      error = false;
    } catch (e) {
      status = `Could not copy: ${e}`;
      error = true;
    }
  }

  async function saveCode() {
    if (!language) return;
    const path = await saveFile("Save map code", `recreate_map${extension}`, [
      { name: `${language} script`, extensions: [extension.slice(1)] },
    ]);
    if (!path) return;
    try {
      await codeApi.save(path, code);
      status = `Saved to ${path}`;
      error = false;
    } catch (e) {
      status = `Could not save: ${e}`;
      error = true;
    }
  }

  async function saveFolder() {
    if (!language) return;
    const folder = await pickFolder("Choose a folder for the runnable project");
    if (!folder) return;
    try {
      let result = await codeApi.workdir(folder, input, language, false);
      if (result.existing.length) {
        const n = result.existing.length;
        const ok = await confirmDialog(
          `${n} file${n === 1 ? "" : "s"} already exist${n === 1 ? "s" : ""} in\n${folder}\n(e.g. ${result.existing[0]}).\n\nOverwrite them?`,
          "Overwrite files?",
        );
        if (!ok) return;
        result = await codeApi.workdir(folder, input, language, true);
      }
      status = `Saved a runnable ${language} project to ${folder}` + (revised ? " (from the map; the AI revision is not in it)" : "");
      error = false;
    } catch (e) {
      status = `Could not save the project: ${e}`;
      error = true;
    }
  }
</script>

<Modal title="Export map as code" {onClose}>
  <div class="flex min-h-[60vh] flex-col gap-3 text-[13px]">
    <p class="text-muted">{NOTE}</p>

    <div class="flex items-center gap-1" role="radiogroup" aria-label="Language">
      <span class="label mr-2">Language</span>
      {#each ["Python", "R"] as const as lang (lang)}
        <button
          class="btn border border-line"
          class:!bg-accent-soft={language === lang}
          role="radio"
          aria-checked={language === lang}
          onclick={() => pick(lang)}>{LABELS[lang]}</button
        >
      {/each}
      <span class="flex-1"></span>
      <span class="text-muted tabular-nums" class:!text-danger={error} aria-live="polite">{status}</span>
    </div>

    {#if notes.length}
      <p class="text-muted">Shown on the map but not reproduced by the script: {notes.join("; ")}.</p>
    {/if}
    {#if revised}
      <p class="text-muted">This script was revised with AI assistance. Review it before relying on it.</p>
    {/if}

    <textarea
      class="field min-h-[40vh] flex-1 resize-none font-mono text-[12px] leading-snug whitespace-pre select-text"
      readonly
      wrap="off"
      spellcheck="false"
      aria-label="Generated code, {lines} lines">{code}</textarea
    >
  </div>

  {#snippet actions()}
    <button class="btn" onclick={copy} disabled={!code}><Copy size={14} /> Copy code</button>
    <button class="btn" onclick={saveCode} disabled={!code}><FileCode size={14} /> Save code as…</button>
    <button class="btn" onclick={saveFolder} disabled={!code}><FolderDown size={14} /> Save as working directory…</button>
    <button class="btn" onclick={() => (assisting = true)} disabled={!code}><Sparkles size={14} /> Check with AI…</button>
    <span class="flex-1"></span>
    <button class="btn-primary" onclick={onClose}>Close</button>
  {/snippet}
</Modal>

{#if assisting && language}
  <CodeAssist
    {code}
    {language}
    {input}
    {getMapImage}
    onAccept={(next) => {
      code = next;
      revised = true;
      status = `${language} · ${next.split("\n").length - (next.endsWith("\n") ? 1 : 0)} lines (AI-revised)`;
    }}
    onClose={() => (assisting = false)}
  />
{/if}
