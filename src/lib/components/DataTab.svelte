<script lang="ts">
  // The Data tab: presets, the dataset list, and the selected dataset's
  // styling, as in PyMappr. Dialogs are opened by the page.
  import type { Snippet } from "svelte";
  import { Eye, EyeOff } from "@lucide/svelte";
  import { store } from "$lib/store.svelte";
  import Section from "./Section.svelte";

  let {
    presets,
    onAddData,
    onManualEntry,
    onEditManual,
    onRemove,
    onCombine,
  }: {
    presets?: Snippet;
    onAddData: () => void;
    onManualEntry: () => void;
    onEditManual: (index: number) => void;
    onRemove: (index: number) => void;
    onCombine: () => void;
  } = $props();

  const PALETTES = ["Default", "Colourblind safe (Okabe-Ito)", "Black & white"];

  const ds = $derived(store.active);
  const total = $derived(store.doc.datasets.reduce((n, d) => n + d.rows.length, 0));

  /** Distinct values of a name column in the active dataset. */
  function values(label: string): string[] {
    if (!ds) return [];
    const col = ds.name_labels.indexOf(label);
    if (col < 0) return [];
    return [...new Set(ds.rows.map((r) => String(r[col] ?? "")))].sort();
  }

  function setOpenBy(label: string) {
    if (!ds) return;
    ds.open_by = label;
    // Picking a column pre-selects "Holotype" when the column has it.
    const holotype = values(label).find((v) => v.toLowerCase() === "holotype");
    ds.open_values = holotype ? [holotype] : [];
  }

  function setPalette(name: string) {
    const m = store.doc.map;
    m.palette = name;
    // White points vanish behind a white outline: switch it to black.
    if (name === "Black & white" && store.doc.point_edge.color.toLowerCase() === "#ffffff") {
      store.doc.point_edge.color = "#000000";
      store.setStatus("The point outline is now black, so white points stay visible.");
    }
  }
</script>

{#if presets}
  <Section title="Presets">
    {@render presets()}
  </Section>
{/if}

<Section title="Datasets">
  <div class="flex flex-wrap gap-2">
    <button class="btn-primary" onclick={onAddData}>Add data file…</button>
    <button class="btn border border-line" onclick={onManualEntry}>Manual entry…</button>
  </div>
  {#if store.doc.datasets.length}
    <ul role="listbox" aria-label="Datasets" class="max-h-40 overflow-y-auto rounded-md border border-line bg-raised">
      {#each store.doc.datasets as d, i (i)}
        <li
          role="option"
          aria-selected={store.doc.active === i}
          class="flex cursor-pointer items-center gap-2 px-2 py-1 hover:bg-accent-soft"
          class:!bg-accent-soft={store.doc.active === i}
          onclick={() => store.setActive(i)}
          onkeydown={(e) => e.key === "Enter" && store.setActive(i)}
          tabindex="0"
        >
          <button
            class="text-muted hover:text-ink"
            aria-label={d.visible ? `Hide ${d.name}` : `Show ${d.name}`}
            onclick={(e) => {
              e.stopPropagation();
              d.visible = !d.visible;
            }}
          >
            {#if d.visible}<Eye size={14} />{:else}<EyeOff size={14} />{/if}
          </button>
          <span class="min-w-0 flex-1 truncate" class:text-muted={!d.visible} title={d.source_path || d.name}>{d.name}</span>
          <span class="text-[12px] tabular-nums text-muted">{d.rows.length}</span>
        </li>
      {/each}
    </ul>
    <div class="flex flex-wrap gap-2">
      <button class="btn border border-line" disabled={!ds?.manual} title={ds && !ds.manual ? "Only typed-in datasets can be edited" : ""}
        onclick={() => store.doc.active !== null && onEditManual(store.doc.active)}>Edit…</button>
      <button class="btn border border-line" disabled={!ds} onclick={() => store.doc.active !== null && onRemove(store.doc.active)}>Remove</button>
    </div>
    <p class="hint">{store.doc.datasets.length} {store.doc.datasets.length === 1 ? "dataset" : "datasets"}, {total} points</p>
  {:else}
    <p class="hint">No data yet. Add a CSV, TSV or spreadsheet of localities, or type coordinates in.</p>
  {/if}
</Section>

{#if ds}
  <Section title="Styling ({ds.name})">
    {#each [["group_by", "Group by"], ["color_by", "Color by"], ["symbol_by", "Symbol by"]] as [key, label] (key)}
      <label class="row">
        <span class="label">{label}</span>
        <select class="field" value={ds[key as "group_by"]} onchange={(e) => (ds[key as "group_by"] = e.currentTarget.value)}>
          <option value="">None</option>
          {#each ds.name_labels as l (l)}<option>{l}</option>{/each}
        </select>
      </label>
    {/each}
    {#if ds.symbol_by}
      <p class="hint">Symbol by shows a second column as marker shapes, with a compact colour and symbol key in the legend.</p>
    {/if}
    <label class="row">
      <span class="label">Open symbols for</span>
      <select class="field" value={ds.open_by} onchange={(e) => setOpenBy(e.currentTarget.value)}>
        <option value="">None</option>
        {#each ds.name_labels as l (l)}<option>{l}</option>{/each}
      </select>
    </label>
    {#if ds.open_by}
      <label class="row">
        <span class="label">where it is</span>
        <select class="field" value={ds.open_values[0] ?? ""} onchange={(e) => (ds.open_values = e.currentTarget.value ? [e.currentTarget.value] : [])}>
          <option value="">(choose a value)</option>
          {#each values(ds.open_by) as v (v)}<option value={v}>{v || "(blank)"}</option>{/each}
        </select>
      </label>
    {/if}
    <button class="btn border border-line" disabled={ds.name_labels.length < 2} onclick={onCombine}>Combine columns…</button>
    <label class="check"><input type="checkbox" bind:checked={ds.vary_symbols} /> Vary symbols per group</label>
  </Section>
{/if}

<Section title="Points">
  <label class="row">
    <span class="label">Palette</span>
    <select class="field" value={store.doc.map.palette} onchange={(e) => setPalette(e.currentTarget.value)}>
      {#each PALETTES as p (p)}<option>{p}</option>{/each}
    </select>
  </label>
  <label class="row">
    <span class="label">Point outline</span>
    <input type="color" class="h-7 w-12 rounded border border-line" bind:value={store.doc.point_edge.color} />
  </label>
  <label class="row">
    <span class="label">Outline width</span>
    <input class="field" type="number" min="0" max="3" step="0.1" value={store.doc.point_edge.width}
      onchange={(e) => (store.doc.point_edge.width = Math.min(3, Math.max(0, Number(e.currentTarget.value) || 0)))} />
  </label>
  <label class="block">
    <span class="label">Point opacity: {store.doc.point_alpha.toFixed(2)}</span>
    <input type="range" min="0.1" max="1" step="0.05" class="w-full accent-[var(--accent)]" bind:value={store.doc.point_alpha} />
  </label>
</Section>
