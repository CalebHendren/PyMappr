<script lang="ts">
  // Shown for every import: which columns hold the coordinates and names.
  import { ArrowDown, ArrowUp } from "@lucide/svelte";
  import { api, type ColumnMapping, type TablePreview } from "$lib/api";
  import { app } from "$lib/state.svelte";
  import Modal from "./Modal.svelte";

  let { path, initial, onClose }: { path: string; initial: TablePreview; onClose: () => void } = $props();

  // svelte-ignore state_referenced_locally
  let preview = $state(initial);
  let sheet = $state<string | null>(null);
  let lon = $state("");
  let lat = $state("");
  let names = $state<string[]>([]);
  let useHeaders = $state(true);
  let error = $state<string | null>(null);
  let loading = $state(false);

  function adopt(p: TablePreview) {
    preview = p;
    lon = p.mapping?.longitude ?? p.headers[0] ?? "";
    lat = p.mapping?.latitude ?? p.headers[1] ?? "";
    names = p.mapping?.names ?? [];
    useHeaders = p.headerRow;
    error = p.mappingError;
  }
  // svelte-ignore state_referenced_locally
  adopt(initial);

  async function reread(headerRow: boolean, newSheet: string | null) {
    try {
      sheet = newSheet;
      adopt(await api.inspectTable(path, headerRow, newSheet));
    } catch (e) {
      error = String(e);
    }
  }

  const others = $derived(preview.headers.filter((h) => h !== lon && h !== lat && !names.includes(h)));

  const chosen = $derived(names.filter((n) => n !== lon && n !== lat));

  function move(i: number, by: number) {
    const next = [...chosen];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    names = next;
  }

  async function add() {
    if (!lon || !lat || lon === lat) {
      error = "Pick two different columns for longitude and latitude.";
      return;
    }
    const mapping: ColumnMapping = {
      longitude: lon,
      latitude: lat,
      names: names.filter((n) => n !== lon && n !== lat),
      useHeaders,
      headerRow: preview.headerRow,
    };
    loading = true;
    try {
      await app.addDataset(path, sheet, mapping);
      onClose();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }
</script>

<Modal title="Add {preview.fileName}" {onClose}>
  <div class="grid grid-cols-[260px_1fr] gap-5">
    <div class="space-y-3">
      <label class="flex items-center gap-2">
        <input
          type="checkbox"
          class="accent-[var(--accent)]"
          checked={preview.headerRow}
          onchange={(e) => reread(e.currentTarget.checked, sheet)}
        />
        First row holds column names
      </label>
      {#if preview.sheets.length > 1}
        <label class="block">
          <span class="label">Worksheet</span>
          <select class="field mt-1" value={sheet ?? preview.sheets[0]} onchange={(e) => reread(preview.headerRow, e.currentTarget.value)}>
            {#each preview.sheets as s (s)}<option value={s}>{s}</option>{/each}
          </select>
        </label>
      {/if}
      <div class="grid grid-cols-2 gap-2">
        <label class="block">
          <span class="label">Longitude</span>
          <select class="field mt-1" bind:value={lon}>
            {#each preview.headers as h (h)}<option value={h}>{h}</option>{/each}
          </select>
        </label>
        <label class="block">
          <span class="label">Latitude</span>
          <select class="field mt-1" bind:value={lat}>
            {#each preview.headers as h (h)}<option value={h}>{h}</option>{/each}
          </select>
        </label>
      </div>

      <div>
        <span class="label">Name columns, in order</span>
        <ul class="mt-1 space-y-1">
          {#each chosen as n, i (n)}
            <li class="flex items-center gap-1 rounded border border-line bg-raised px-2 py-0.5">
              <input
                type="checkbox"
                class="accent-[var(--accent)]"
                checked
                aria-label="Use {n}"
                onchange={() => (names = names.filter((x) => x !== n))}
              />
              <span class="flex-1 truncate">{n}</span>
              <button class="btn !p-0.5" disabled={i === 0} onclick={() => move(i, -1)} aria-label="Move {n} up"
                ><ArrowUp size={13} /></button
              >
              <button class="btn !p-0.5" disabled={i === chosen.length - 1} onclick={() => move(i, 1)} aria-label="Move {n} down"
                ><ArrowDown size={13} /></button
              >
            </li>
          {/each}
          {#each others as n (n)}
            <li class="flex items-center gap-1 px-2 py-0.5 text-muted">
              <input type="checkbox" class="accent-[var(--accent)]" aria-label="Use {n}" onchange={() => (names = [...names, n])} />
              <span class="flex-1 truncate">{n}</span>
            </li>
          {/each}
        </ul>
      </div>
      {#if !preview.headerRow}
        <label class="flex items-center gap-2">
          <input type="checkbox" class="accent-[var(--accent)]" bind:checked={useHeaders} />
          Use the column titles as labels
        </label>
      {/if}
    </div>

    <div class="min-w-0">
      <p class="label mb-1">First {Math.min(8, preview.rowCount)} of {preview.rowCount} rows</p>
      <div class="overflow-auto rounded border border-line">
        <table class="w-full text-[12px]">
          <thead class="bg-paper text-left">
            <tr>
              {#each preview.headers as h (h)}
                <th class="whitespace-nowrap px-2 py-1 font-semibold" class:text-accent={h === lon || h === lat}>
                  {h}{#if h === lon}<span class="font-normal text-muted">{" "}(lon)</span>{:else if h === lat}<span
                      class="font-normal text-muted">{" "}(lat)</span
                    >{/if}
                </th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each preview.preview as row, r (r)}
              <tr class="border-t border-line">
                {#each row as cell, c (c)}<td class="whitespace-nowrap px-2 py-0.5">{cell}</td>{/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  {#if error}<p class="mt-3 text-danger">{error}</p>{/if}

  {#snippet actions()}
    <button class="btn" onclick={onClose}>Cancel</button>
    <button class="btn-primary" onclick={add} disabled={loading}>{loading ? "Adding…" : "Add to map"}</button>
  {/snippet}
</Modal>
