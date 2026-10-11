<script lang="ts">
  import { ArrowLeft, ArrowRight, Download, House, Minus, Moon, Plus, Sun, TablePropertiesIcon } from "@lucide/svelte";
  import { store } from "$lib/store.svelte";

  let { onAddData, onSaveMap }: { onAddData: () => void; onSaveMap: () => void } = $props();

  const dark = $derived(store.theme === "dark");
</script>

<header class="flex h-11 items-center gap-1 border-b border-line bg-panel px-3">
  <span class="mr-3 text-[15px] font-semibold tracking-tight">RustyMappr</span>

  <button class="btn-primary" onclick={onAddData}><TablePropertiesIcon size={15} /> Add data</button>

  <div class="mx-2 h-5 w-px bg-line"></div>

  <button class="btn" onclick={() => store.home()} disabled={!store.view} title="Home: frame the Limit to area">
    <House size={15} />
  </button>
  <button class="btn" onclick={() => store.goBack()} disabled={!store.back.length} title="Back to the previous view" aria-label="Back">
    <ArrowLeft size={15} />
  </button>
  <button class="btn" onclick={() => store.goForward()} disabled={!store.forward.length} title="Forward" aria-label="Forward">
    <ArrowRight size={15} />
  </button>
  <button class="btn" onclick={() => store.zoomBy(1.5)} disabled={!store.view} title="Zoom in (Ctrl +)" aria-label="Zoom in">
    <Plus size={16} />
  </button>
  <button class="btn" onclick={() => store.zoomBy(1 / 1.5)} disabled={!store.view} title="Zoom out (Ctrl −)" aria-label="Zoom out">
    <Minus size={16} />
  </button>
  <span class="ml-2 hidden text-[12px] text-muted xl:inline">Drag to pan, Shift-drag to zoom to a box</span>

  <div class="flex-1"></div>

  <button class="btn" onclick={onSaveMap} disabled={!store.svgEl}><Download size={15} /> Save map</button>

  <!-- Light / dark switch -->
  <button
    role="switch"
    aria-checked={dark}
    aria-label="Dark mode"
    title={dark ? "Switch to light mode" : "Switch to dark mode"}
    class="ml-2 flex h-7 w-[3.25rem] items-center rounded-full border border-line bg-raised px-0.5 transition-colors"
    onclick={() => store.setTheme(dark ? "light" : "dark")}
  >
    <span
      class="grid h-6 w-6 place-items-center rounded-full bg-accent text-accent-ink transition-transform"
      class:translate-x-[1.375rem]={dark}
    >
      {#if dark}<Moon size={13} />{:else}<Sun size={13} />{/if}
    </span>
  </button>
</header>
