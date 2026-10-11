<script lang="ts">
  // The filter bar under the map (PyMappr's ui/filter_bar.py): pick a name
  // column and tick the values to show. The filter is not saved with the
  // project, and it resets when another dataset is selected.
  import { columnKey, type PointFilter } from "$lib/symbology";
  import type { DatasetEntry } from "$lib/model";

  let {
    entry,
    datasetIndex,
    onchange,
  }: {
    /** The selected dataset, or null. */
    entry: DatasetEntry | null;
    datasetIndex: number | null;
    /** The new filter (null when none applies); pass it to symbology(). */
    onchange: (filter: PointFilter | null) => void;
  } = $props();

  let column = $state("None");
  let hidden = $state<string[]>([]);

  const key = $derived(entry ? columnKey(entry, column) : null);
  const at = $derived(entry && key ? entry.columns.indexOf(key) : -1);
  const values = $derived.by(() => {
    if (!entry || at < 0) return [] as string[];
    return [...new Set(entry.rows.map((r) => (r[at] === null || r[at] === undefined ? "" : String(r[at]))))];
  });
  const filter = $derived<PointFilter | null>(
    entry && key && values.length && datasetIndex !== null
      ? { dataset: datasetIndex, key, allowed: values.filter((v) => !hidden.includes(v)) }
      : null,
  );
  const shown = $derived(
    entry && filter ? entry.rows.filter((r) => filter.allowed.includes(r[at] === null || r[at] === undefined ? "" : String(r[at]))).length : 0,
  );

  // A different dataset starts unfiltered.
  let lastEntry: DatasetEntry | null = null;
  let lastIndex: number | null = null;
  $effect(() => {
    if (entry !== lastEntry || datasetIndex !== lastIndex) {
      const first = lastEntry === null && lastIndex === null;
      const same = lastIndex === datasetIndex && lastEntry?.name_labels.join("\x00") === entry?.name_labels.join("\x00");
      lastEntry = entry;
      lastIndex = datasetIndex;
      if (!first && !same) {
        column = "None";
        hidden = [];
        onchange(null);
      }
    }
  });

  function pick(label: string) {
    column = label;
    hidden = [];
    onchange(filter);
  }

  function setAll(on: boolean) {
    hidden = on ? [] : [...values];
    onchange(filter);
  }

  function toggle(value: string, on: boolean) {
    hidden = on ? hidden.filter((v) => v !== value) : [...hidden, value];
    onchange(filter);
  }
</script>

<div class="flex min-w-0 items-center gap-2 px-2 py-1 text-[13px]">
  <label class="flex shrink-0 items-center gap-1.5">
    <span class="label">Filter by</span>
    <select class="field w-36" value={column} disabled={!entry || !entry.rows.length} onchange={(e) => pick(e.currentTarget.value)}>
      <option value="None">None</option>
      {#each entry?.name_labels ?? [] as label (label)}
        <option value={label}>{label}</option>
      {/each}
    </select>
  </label>
  <button class="btn shrink-0 border border-line" disabled={!filter} onclick={() => setAll(true)}>All</button>
  <button class="btn shrink-0 border border-line" disabled={!filter} onclick={() => setAll(false)}>None</button>
  <div class="flex min-w-0 flex-1 items-center gap-3 overflow-x-auto whitespace-nowrap">
    {#each values as value (value)}
      <label class="flex items-center gap-1">
        <input type="checkbox" checked={!hidden.includes(value)} onchange={(e) => toggle(value, e.currentTarget.checked)} />
        {value || "(blank)"}
      </label>
    {/each}
  </div>
  {#if entry && filter}
    <span class="shrink-0 text-[12px] text-muted">Filter: showing {shown} of {entry.rows.length} points</span>
  {/if}
</div>
