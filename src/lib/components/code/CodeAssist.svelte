<script lang="ts">
  // Check the exported script with a model on OpenRouter (the user's own
  // key), then review the suggested changes as a diff before taking them.
  import { onDestroy } from "svelte";
  import { KeyRound, RefreshCw, Eye, Send, TriangleAlert } from "@lucide/svelte";
  import { api, confirmDialog, openUrl } from "$lib/api";
  import {
    codeApi,
    DEFAULT_SEND,
    withRevisionHeader,
    type CheckPreview,
    type CheckRequest,
    type CheckResult,
    type CodeLanguage,
    type ExportInput,
    type KeyStatus,
    type ModelInfo,
    type SendOptions,
  } from "$lib/api-code";
  import { diffLines, diffStats, hunks } from "$lib/diff";
  import Modal from "../Modal.svelte";

  let {
    code,
    language,
    input,
    getMapImage,
    onAccept,
    onClose,
  }: {
    /** The script as it stands in the export dialog (data embedded). */
    code: string;
    language: CodeLanguage;
    /** The map the script recreates: state, figure size, renderer info. */
    input: ExportInput;
    /** A PNG data URL of the map as drawn, for models that take images. */
    getMapImage?: () => Promise<string | null>;
    /** Called with the revised script (header comment added) on Accept. */
    onAccept: (code: string) => void;
    onClose: () => void;
  } = $props();

  let key = $state<KeyStatus>({ set: false, hint: null });
  let keyDraft = $state("");
  let editingKey = $state(false);
  let keyUrl = $state("https://openrouter.ai/settings/keys");

  let presets = $state<string[]>([]);
  let catalog = $state<ModelInfo[] | null>(null);
  let model = $state("");
  let customModel = $state("");
  let send = $state<SendOptions>({ ...DEFAULT_SEND });

  let busy = $state<string | null>(null);
  let error = $state<string | null>(null);
  let preview = $state<CheckPreview | null>(null);
  let jobId = $state<number | null>(null);
  let result = $state<CheckResult | null>(null);

  const CUSTOM = "__custom__";
  const chosenModel = $derived(model === CUSTOM ? customModel.trim() : model);
  const modelInfo = $derived(catalog?.find((m) => m.id === chosenModel) ?? null);
  // Unknown (a preset before the catalog is loaded, or a custom ID): let
  // the user try; the provider rejects images it cannot take.
  const imageOk = $derived(modelInfo ? modelInfo.inputModalities.includes("image") : catalog === null);
  const groups = $derived.by(() => {
    const ids = catalog ? catalog.map((m) => m.id) : presets;
    const byAuthor = new Map<string, string[]>();
    for (const id of ids) {
      const author = id.includes("/") ? id.slice(0, id.indexOf("/")) : "other";
      byAuthor.set(author, [...(byAuthor.get(author) ?? []), id]);
    }
    return [...byAuthor.entries()];
  });

  const diff = $derived(result?.code ? diffLines(code, result.code) : []);
  const stats = $derived(diffStats(diff));
  const diffHunks = $derived(hunks(diff, 3));

  $effect(() => {
    (async () => {
      try {
        const [status, prefs] = await Promise.all([codeApi.keyStatus(), codeApi.prefs()]);
        key = status;
        editingKey = !status.set;
        presets = prefs.presets;
        catalog = prefs.models;
        keyUrl = prefs.keyUrl;
        send = { ...DEFAULT_SEND, ...prefs.send };
        const known = (prefs.models?.map((m) => m.id) ?? prefs.presets).includes(prefs.model);
        model = known ? prefs.model : CUSTOM;
        if (!known) customModel = prefs.model;
      } catch (e) {
        error = String(e);
      }
    })();
  });

  // Stop the request if the dialog closes mid-way.
  onDestroy(() => {
    if (jobId !== null) void api.jobCancel(jobId);
  });

  async function saveKey() {
    error = null;
    try {
      key = await codeApi.keySet(keyDraft);
      keyDraft = "";
      editingKey = false;
    } catch (e) {
      error = String(e);
    }
  }

  async function clearKey() {
    if (!(await confirmDialog("Remove the OpenRouter key from Windows Credential Manager?"))) return;
    try {
      await codeApi.keyClear();
      key = { set: false, hint: null };
      editingKey = true;
    } catch (e) {
      error = String(e);
    }
  }

  async function loadModels() {
    busy = "Loading the model list…";
    error = null;
    try {
      catalog = await codeApi.refreshModels();
    } catch (e) {
      error = String(e);
    } finally {
      busy = null;
    }
  }

  function remember() {
    preview = null;
    if (chosenModel) void codeApi.setPrefs({ model: chosenModel, send: $state.snapshot(send) });
  }

  async function toggleFullData(on: boolean) {
    if (
      on &&
      !(await confirmDialog(
        "Send every row of your data to OpenRouter and the model's provider? They may keep it under their own terms.",
        "Send full data",
      ))
    ) {
      send.fullData = false;
      return;
    }
    send.fullData = on;
    remember();
  }

  async function request(): Promise<CheckRequest | null> {
    if (!chosenModel) {
      error = "Pick a model first.";
      return null;
    }
    let mapImage: string | null = null;
    if (send.mapImage && imageOk && getMapImage) {
      mapImage = await getMapImage();
      if (!mapImage) {
        error = "The map image is not available.";
        return null;
      }
    }
    return {
      ...input,
      code,
      language,
      model: chosenModel,
      send: { ...$state.snapshot(send), mapImage: send.mapImage && imageOk },
      mapImage,
    };
  }

  async function showPreview() {
    error = null;
    const req = await request();
    if (!req) return;
    try {
      preview = await codeApi.preview(req);
    } catch (e) {
      error = String(e);
    }
  }

  async function run() {
    error = null;
    result = null;
    const req = await request();
    if (!req) return;
    try {
      jobId = await codeApi.check(req);
      busy = `Waiting for ${req.model}… (this can take a few minutes)`;
      while (jobId !== null) {
        await new Promise((r) => setTimeout(r, 1000));
        const status = await api.jobStatus(jobId);
        if (!status || !status.done) continue;
        jobId = null;
        if (status.error) error = status.error;
        else result = (status as unknown as { result: CheckResult }).result;
      }
    } catch (e) {
      error = String(e);
      jobId = null;
    } finally {
      busy = null;
    }
  }

  async function cancel() {
    if (jobId !== null) await api.jobCancel(jobId);
    jobId = null;
    busy = null;
    error = "Cancelled. The reply, if one comes, is ignored.";
  }

  function accept() {
    if (!result?.code) return;
    onAccept(withRevisionHeader(result.code, result.model));
    onClose();
  }

  const payloadText = $derived(preview ? JSON.stringify(preview.payload, null, 2) : "");
</script>

<Modal title="Check the script with AI" {onClose}>
  <div class="space-y-4 text-[13px]">
    <div class="flex gap-2 rounded-md border border-line bg-raised p-3 text-muted" role="note">
      <TriangleAlert size={16} class="mt-0.5 shrink-0 text-danger" />
      <p>
        AI-suggested code can be wrong, or subtly change the map. Review the diff before using it. What you choose to
        send goes to OpenRouter and to the selected model's provider, and may be logged under their terms. Your API key
        is stored in Windows Credential Manager.
      </p>
    </div>

    {#if !result}
      <section class="space-y-1">
        <span class="label">OpenRouter API key</span>
        {#if key.set && !editingKey}
          <div class="flex items-center gap-2">
            <KeyRound size={14} class="text-muted" />
            <span class="font-mono">{key.hint}</span>
            <button class="btn" onclick={() => (editingKey = true)}>Change</button>
            <button class="btn" onclick={clearKey}>Remove</button>
          </div>
        {:else}
          <div class="flex gap-2">
            <input
              class="field font-mono"
              type="password"
              autocomplete="off"
              placeholder="sk-or-…"
              bind:value={keyDraft}
              onkeydown={(e) => e.key === "Enter" && keyDraft.trim() && saveKey()}
            />
            <button class="btn-primary shrink-0 whitespace-nowrap" onclick={saveKey} disabled={!keyDraft.trim()}>Save key</button>
            {#if key.set}<button class="btn" onclick={() => (editingKey = false)}>Keep current</button>{/if}
          </div>
          <p class="text-muted">
            Bring your own key: <button class="underline" onclick={() => openUrl(keyUrl)}>get one from OpenRouter</button>.
          </p>
        {/if}
      </section>

      <section class="space-y-1">
        <label class="label" for="ai-model">Model</label>
        <div class="flex gap-2">
          <select id="ai-model" class="field" bind:value={model} onchange={remember}>
            {#each groups as [author, ids] (author)}
              <optgroup label={author}>
                {#each ids as id (id)}<option value={id}>{id}</option>{/each}
              </optgroup>
            {/each}
            <option value={CUSTOM}>Other model ID…</option>
          </select>
          <button class="btn shrink-0" onclick={loadModels} disabled={busy !== null} title="Fetch every model OpenRouter offers">
            <RefreshCw size={14} /> Load all models
          </button>
        </div>
        {#if model === CUSTOM}
          <input class="field font-mono" placeholder="author/model-name" bind:value={customModel} onchange={remember} />
        {/if}
      </section>

      <fieldset class="space-y-1">
        <legend class="label">What to send</legend>
        <label class="flex items-center gap-2 text-muted">
          <input type="checkbox" checked disabled /> The script (legend labels and group names included; point data held back)
        </label>
        <label class="flex items-center gap-2">
          <input type="checkbox" bind:checked={send.columns} onchange={remember} /> Column names
        </label>
        <label class="flex items-center gap-2">
          <input type="checkbox" bind:checked={send.firstRows} onchange={remember} disabled={send.fullData} /> First
          <input
            class="field !w-16"
            type="number"
            min="1"
            max="1000"
            value={send.rows ?? 5}
            onchange={(e) => {
              send.rows = Math.max(1, Math.round(Number(e.currentTarget.value) || 5));
              remember();
            }}
            disabled={!send.firstRows || send.fullData}
          /> rows of each dataset
        </label>
        <label class="flex items-center gap-2" class:text-muted={!imageOk}>
          <input type="checkbox" bind:checked={send.mapImage} onchange={remember} disabled={!imageOk || !getMapImage} /> Map
          image
          {#if !imageOk}<span>(this model does not take images)</span>{/if}
        </label>
        <label class="flex items-center gap-2">
          <input type="checkbox" checked={send.fullData} onchange={(e) => toggleFullData(e.currentTarget.checked)} /> Full data
          (every row)
        </label>
      </fieldset>

      {#if preview}
        <section class="space-y-1">
          <div class="flex items-baseline justify-between">
            <span class="label">Request to {preview.url}</span>
            <span class="text-muted tabular-nums"
              >{preview.chars.toLocaleString()} characters, about {preview.approxTokens.toLocaleString()} tokens</span
            >
          </div>
          <pre
            class="max-h-64 overflow-auto rounded-md border border-line bg-raised p-2 font-mono text-[11px] whitespace-pre-wrap select-text">{payloadText}</pre>
          {#if preview.unmatched.length}
            <p class="text-danger">
              Some data could not be held back from this script, so it will not be sent. Regenerate the script first.
            </p>
          {/if}
        </section>
      {/if}
    {:else}
      <section class="space-y-2">
        {#if result.noChanges && (!result.code || stats.added + stats.removed === 0)}
          <p><strong>{result.model}</strong> found nothing to change.</p>
        {:else if !result.code}
          <p class="text-danger">The reply held no script, so there is nothing to apply.</p>
        {:else}
          <p>
            <strong>{result.model}</strong> suggests
            <span class="tabular-nums">{stats.added} added and {stats.removed} removed lines</span>.
          </p>
        {/if}
        {#if result.missing.length}
          <p class="text-danger">
            The reply dropped the data placeholder of dataset {result.missing.map((i) => i + 1).join(", ")}; its data is
            missing from the suggestion. Do not accept it as is.
          </p>
        {/if}
        {#if result.finishReason === "length"}
          <p class="text-danger">The reply was cut off: the suggested script is incomplete.</p>
        {/if}
        {#if result.changes.length}
          <ul class="list-disc space-y-0.5 pl-5">
            {#each result.changes as change, i (i)}<li>{change}</li>{/each}
          </ul>
        {:else if result.notes}
          <p class="whitespace-pre-wrap text-muted">{result.notes}</p>
        {/if}
        {#if diffHunks.length}
          <div class="max-h-[45vh] overflow-auto rounded-md border border-line bg-raised font-mono text-[11px] select-text">
            {#each diffHunks as hunk, h (h)}
              <div class="border-b border-line bg-accent-soft px-2 py-0.5 text-muted">
                @@ -{hunk.oldStart},{hunk.oldLines} +{hunk.newStart},{hunk.newLines} @@
              </div>
              {#each hunk.lines as line, i (i)}
                <div
                  class="flex whitespace-pre"
                  class:diff-add={line.kind === "add"}
                  class:diff-del={line.kind === "del"}
                >
                  <span class="w-10 shrink-0 pr-1 text-right text-muted">{line.oldNo ?? ""}</span>
                  <span class="w-10 shrink-0 pr-1 text-right text-muted">{line.newNo ?? ""}</span>
                  <span class="w-3 shrink-0">{line.kind === "add" ? "+" : line.kind === "del" ? "-" : " "}</span>
                  <span>{line.text}</span>
                </div>
              {/each}
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    {#if busy}<p class="text-muted" aria-live="polite">{busy}</p>{/if}
    {#if error}<p class="text-danger" aria-live="polite">{error}</p>{/if}
  </div>

  {#snippet actions()}
    {#if result}
      <button class="btn" onclick={onClose}>Discard</button>
      <button class="btn" onclick={() => (result = null)}>Back</button>
      <button
        class="btn-primary"
        onclick={accept}
        disabled={!result.code || stats.added + stats.removed === 0 || result.missing.length > 0}>Accept</button
      >
    {:else if jobId !== null}
      <button class="btn" onclick={cancel}>Cancel</button>
    {:else}
      <button class="btn" onclick={onClose}>Close</button>
      <button class="btn" onclick={showPreview} disabled={busy !== null}><Eye size={14} /> Preview request</button>
      <button class="btn-primary" onclick={run} disabled={!key.set || busy !== null || !chosenModel}
        ><Send size={14} /> Send</button
      >
    {/if}
  {/snippet}
</Modal>

<style>
  .diff-add {
    background: color-mix(in srgb, var(--accent) 16%, transparent);
  }
  .diff-del {
    background: color-mix(in srgb, var(--danger) 14%, transparent);
  }
</style>
