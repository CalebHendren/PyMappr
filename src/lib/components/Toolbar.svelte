<script lang="ts">
  import { Bug, Download, Maximize, Minus, Moon, Plus, Stamp, Sun, TablePropertiesIcon } from "@lucide/svelte";
  import { app } from "$lib/state.svelte";

  let { onAddData, onExport }: { onAddData: () => void; onExport: () => void } = $props();
</script>

<header class="flex h-12 items-center gap-1 border-b border-line bg-panel px-3">
  <div class="mr-3 flex items-center gap-2">
    <Bug size={20} class="text-accent" />
    <span class="text-[15px] font-semibold tracking-tight">RustyMappr</span>
  </div>

  <button class="btn-primary" onclick={onAddData}><TablePropertiesIcon size={15} /> Add data</button>

  <div class="mx-2 h-5 w-px bg-line"></div>

  <button class="btn" onclick={() => app.zoomBy(1.5)} disabled={!app.view} title="Zoom in (+)" aria-label="Zoom in">
    <Plus size={16} />
  </button>
  <button class="btn" onclick={() => app.zoomBy(1 / 1.5)} disabled={!app.view} title="Zoom out (−)" aria-label="Zoom out">
    <Minus size={16} />
  </button>
  <button class="btn" onclick={() => app.fit()} disabled={!app.view} title="Fit the whole map (0)">
    <Maximize size={15} /> Fit
  </button>

  <div class="mx-2 h-5 w-px bg-line"></div>

  <button
    class="btn"
    onclick={() => app.applyStandard()}
    title="Black-and-white symbols, italic legend, 600 DPI at 17 cm: ready for Zootaxa and Phytotaxa"
  >
    <Stamp size={15} /> Standard preset
  </button>

  <div class="flex-1"></div>

  <button class="btn" onclick={onExport} disabled={!app.svgEl}><Download size={15} /> Save map</button>
  <button class="btn" onclick={() => app.toggleTheme()} aria-label="Switch light or dark theme">
    {#if app.theme === "light"}<Moon size={16} />{:else}<Sun size={16} />{/if}
  </button>
</header>
