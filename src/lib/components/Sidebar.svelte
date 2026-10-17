<script lang="ts">
  import type { Snippet } from "svelte";
  import { Heart, X } from "@lucide/svelte";

  let {
    data,
    legend,
    map,
    layers,
    labels,
    showKofi,
    onKofi,
    onHideKofi,
    onCheckUpdates,
  }: {
    data: Snippet;
    legend: Snippet;
    map: Snippet;
    layers: Snippet;
    labels: Snippet;
    showKofi: boolean;
    onKofi: () => void;
    onHideKofi: () => void;
    onCheckUpdates: () => void;
  } = $props();

  const tabs = ["Data", "Legend", "Map", "Layers", "Labels"] as const;
  let tab = $state<(typeof tabs)[number]>("Data");
  const panels = $derived({ Data: data, Legend: legend, Map: map, Layers: layers, Labels: labels });
</script>

<aside class="flex min-h-0 flex-col border-r border-line bg-panel">
  <div role="tablist" class="flex gap-0.5 border-b border-line px-2 pt-2">
    {#each tabs as t (t)}
      <button
        role="tab"
        aria-selected={tab === t}
        class="-mb-px rounded-t-md border border-transparent px-2.5 py-1.5 text-[13px] font-medium text-muted hover:text-ink"
        class:!border-line={tab === t}
        class:!border-b-panel={tab === t}
        class:!text-ink={tab === t}
        class:bg-panel={tab === t}
        onclick={() => (tab = t)}>{t}</button
      >
    {/each}
  </div>
  <div class="min-h-0 flex-1 overflow-y-auto p-3" role="tabpanel">
    {@render panels[tab]()}
  </div>
  <footer class="flex flex-wrap items-center gap-2 border-t border-line px-3 py-2">
    {#if showKofi}
      <div class="flex items-center">
        <button class="btn rounded-r-none border border-line" onclick={onKofi}><Heart size={14} /> Support on Ko-fi</button>
        <button
          class="btn -ml-px rounded-l-none border border-line px-1.5"
          aria-label="Hide this button"
          title="Hide this button (the Help menu still has the link)"
          onclick={onHideKofi}><X size={14} /></button
        >
      </div>
    {/if}
    <button class="btn" onclick={onCheckUpdates}>Check for updates…</button>
  </footer>
</aside>
