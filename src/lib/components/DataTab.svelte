<script lang="ts">
  import { Eye, EyeOff, X } from "@lucide/svelte";
  import { app, type Dataset, type GroupBy } from "$lib/state.svelte";
  import { PALETTES, SHAPE_ORDER, SHAPES } from "$lib/styles";
  import Section from "./Section.svelte";
  import Swatch from "./Swatch.svelte";

  let { onAddData }: { onAddData: () => void } = $props();

  function groupByValue(ds: Dataset): string {
    return String(ds.groupBy);
  }
  function setGroupBy(ds: Dataset, value: string) {
    ds.groupBy = (value === "all-names" || value === "dataset" ? value : Number(value)) as GroupBy;
    app.assignStyles(false);
  }
</script>

<Section title="Datasets">
  {#if !app.datasets.length}
    <p class="text-muted">No data yet. Each file you add gets its own entry here, with its groups and their symbols.</p>
    <button class="btn-primary" onclick={onAddData}>Add data</button>
  {/if}

  {#each app.datasets as ds (ds.id)}
    {@const groups = app.groups.filter((g) => g.datasetId === ds.id)}
    <!-- A dataset reads like a specimen label: file, counts, then its taxa. -->
    <article class="rounded-sm border border-ink/50 bg-raised px-3 pb-2 pt-2 shadow-[1px_1px_0_var(--line)]">
      <div class="flex items-start gap-1">
        <div class="min-w-0 flex-1">
          <h4 class="truncate text-[13px] font-semibold" title={ds.path}>{ds.fileName}</h4>
          <p class="text-[12px] text-muted">
            {ds.points.length} points{#if ds.skipped.length}, {ds.skipped.length} rows skipped{/if}
          </p>
        </div>
        <button
          class="btn !p-1"
          onclick={() => (ds.visible = !ds.visible)}
          aria-label={ds.visible ? "Hide dataset" : "Show dataset"}
          title={ds.visible ? "Hide" : "Show"}
        >
          {#if ds.visible}<Eye size={15} />{:else}<EyeOff size={15} />{/if}
        </button>
        <button class="btn !p-1" onclick={() => app.removeDataset(ds.id)} aria-label="Remove dataset" title="Remove">
          <X size={15} />
        </button>
      </div>

      <label class="mt-2 flex items-center gap-2">
        <span class="label shrink-0">Group by</span>
        <select class="field" value={groupByValue(ds)} onchange={(e) => setGroupBy(ds, e.currentTarget.value)}>
          <option value="all-names">All name columns</option>
          {#each ds.nameLabels as label, i (i)}
            <option value={String(i)}>{label}</option>
          {/each}
          <option value="dataset">Whole file</option>
        </select>
      </label>

      {#if ds.visible}
        <ul class="mt-2 border-t border-dashed border-line pt-1">
          {#each groups as g (g.id)}
            <li class="flex items-center gap-2 py-0.5" class:opacity-45={!g.visible}>
              <label class="relative cursor-pointer" title="Change colour">
                <Swatch shape={g.shape} color={g.color} />
                <input
                  type="color"
                  class="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  value={g.color}
                  oninput={(e) => app.setGroupStyle(g.id, { color: e.currentTarget.value })}
                />
              </label>
              <span class="min-w-0 flex-1 truncate italic" title={g.label}>{g.label}</span>
              <span class="text-[12px] tabular-nums text-muted">{g.count}</span>
              <select
                class="w-[5.5rem] rounded border border-line bg-raised px-1 text-[12px]"
                value={g.shape}
                aria-label="Symbol for {g.label}"
                onchange={(e) => app.setGroupStyle(g.id, { shape: e.currentTarget.value })}
              >
                {#each SHAPE_ORDER as s (s)}<option value={s}>{SHAPES[s].label}</option>{/each}
              </select>
              <input
                type="checkbox"
                class="accent-[var(--accent)]"
                checked={g.visible}
                aria-label="Show {g.label}"
                onchange={(e) => app.setGroupStyle(g.id, { visible: e.currentTarget.checked })}
              />
            </li>
          {/each}
        </ul>
      {/if}

      {#if ds.skipped.length}
        <details class="mt-1 text-[12px]">
          <summary class="cursor-pointer text-muted">Rows without usable coordinates</summary>
          <ul class="mt-1 max-h-32 overflow-y-auto text-danger">
            {#each ds.skipped as s, i (i)}<li>{s}</li>{/each}
          </ul>
        </details>
      {/if}
    </article>
  {/each}
</Section>

<Section title="Symbols">
  <label class="block">
    <span class="label">Palette</span>
    <select
      class="field mt-1"
      value={app.palette}
      onchange={(e) => {
        app.palette = e.currentTarget.value;
        app.assignStyles(true);
      }}
    >
      {#each Object.entries(PALETTES) as [id, p] (id)}<option value={id}>{p.label}</option>{/each}
    </select>
  </label>
  <label class="flex items-center gap-2">
    <input
      type="checkbox"
      class="accent-[var(--accent)]"
      checked={app.varySymbols}
      onchange={(e) => {
        app.varySymbols = e.currentTarget.checked;
        app.assignStyles(true);
      }}
    />
    Vary symbols between groups
  </label>
  <label class="block">
    <span class="label">Point size: {app.pointSize} px</span>
    <input type="range" min="3" max="24" step="1" class="w-full accent-[var(--accent)]" bind:value={app.pointSize} />
  </label>
  <div class="flex items-end gap-3">
    <label class="block">
      <span class="label">Outline</span>
      <input type="color" class="mt-1 block h-7 w-12 rounded border border-line bg-raised" bind:value={app.outlineColor} />
    </label>
    <label class="block flex-1">
      <span class="label">Outline width: {app.outlineWidth.toFixed(1)}</span>
      <input type="range" min="0" max="2" step="0.1" class="w-full accent-[var(--accent)]" bind:value={app.outlineWidth} />
    </label>
  </div>
  <label class="block">
    <span class="label">Opacity: {Math.round(app.opacity * 100)}%</span>
    <input type="range" min="0.1" max="1" step="0.05" class="w-full accent-[var(--accent)]" bind:value={app.opacity} />
  </label>
</Section>
