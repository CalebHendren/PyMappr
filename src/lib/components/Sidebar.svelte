<script lang="ts">
  import DataTab from "./DataTab.svelte";
  import MapTab from "./MapTab.svelte";
  import LayersTab from "./LayersTab.svelte";
  import LegendTab from "./LegendTab.svelte";

  let { onAddData, onChooseDataDir }: { onAddData: () => void; onChooseDataDir: () => void } = $props();

  const tabs = ["Data", "Map", "Layers", "Legend"] as const;
  let tab = $state<(typeof tabs)[number]>("Data");
</script>

<aside class="flex min-h-0 flex-col border-r border-line bg-panel">
  <div role="tablist" class="flex gap-1 border-b border-line px-2 pt-2">
    {#each tabs as t (t)}
      <button
        role="tab"
        aria-selected={tab === t}
        class="-mb-px rounded-t-md border border-transparent px-3 py-1.5 text-[13px] font-medium text-muted hover:text-ink"
        class:!border-line={tab === t}
        class:!border-b-panel={tab === t}
        class:!text-ink={tab === t}
        class:bg-panel={tab === t}
        onclick={() => (tab = t)}>{t}</button
      >
    {/each}
  </div>
  <div class="min-h-0 flex-1 overflow-y-auto p-3" role="tabpanel">
    {#if tab === "Data"}
      <DataTab {onAddData} />
    {:else if tab === "Map"}
      <MapTab />
    {:else if tab === "Layers"}
      <LayersTab {onChooseDataDir} />
    {:else}
      <LegendTab />
    {/if}
  </div>
</aside>
