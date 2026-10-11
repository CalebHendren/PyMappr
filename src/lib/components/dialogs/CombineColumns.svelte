<script lang="ts">
  // "Combine columns": join name columns into one, e.g. Genus + Species
  // (PyMappr's ui/combine_columns.py). Apply the result with applyCombine,
  // which adds the column, groups by it and clears Symbol by.
  import { untrack } from "svelte";
  import { combinePreview, defaultCombineColumns } from "$lib/datasets";
  import type { DatasetEntry } from "$lib/model";
  import DialogFrame from "./DialogFrame.svelte";

  let {
    entry,
    onaccept,
    onClose,
  }: {
    /** The dataset; it needs two name columns or more (else show COMBINE_NEEDS_TWO). */
    entry: DatasetEntry;
    /** The ticked columns in table order, and the separator. */
    onaccept: (labels: string[], separator: string) => void;
    onClose: () => void;
  } = $props();

  const labels = $derived(entry.name_labels);
  let ticked = $state<string[]>(untrack(() => defaultCombineColumns(entry.name_labels)));
  let separator = $state(" ");
  const chosen = $derived(labels.filter((l) => ticked.includes(l)));
  const sample = $derived(chosen.length >= 2 ? combinePreview(entry, chosen, separator) : "");

  function toggle(label: string, on: boolean) {
    ticked = on ? [...ticked, label] : ticked.filter((l) => l !== label);
  }

  function accept() {
    if (chosen.length >= 2) onaccept(chosen, separator);
  }
</script>

<DialogFrame title="Combine columns" {onClose} width="w-[min(420px,92vw)]">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="space-y-3" onkeydown={(e) => e.key === "Enter" && accept()}>
    <p class="text-[13px]">Join these name columns, in this order:</p>
    <div class="space-y-1 pl-2">
      {#each labels as label (label)}
        <label class="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={ticked.includes(label)} onchange={(e) => toggle(label, e.currentTarget.checked)} />
          {label}
        </label>
      {/each}
    </div>
    <label class="flex items-center gap-2">
      <span class="label">Separator</span>
      <input class="field w-20" bind:value={separator} />
    </label>
    <p class="text-[13px] text-muted">
      {#if chosen.length < 2}Tick at least two columns.{:else if sample}First row: {sample}{/if}
    </p>
  </div>
  {#snippet actions()}
    <span class="flex-1"></span>
    <button class="btn border border-line" onclick={onClose}>Cancel</button>
    <button class="btn-primary" disabled={chosen.length < 2} onclick={accept}>Add column</button>
  {/snippet}
</DialogFrame>
