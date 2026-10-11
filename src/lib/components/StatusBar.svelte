<script lang="ts">
  import { CircleAlert, LoaderCircle } from "@lucide/svelte";
  import { store } from "$lib/store.svelte";

  const fmt = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(4)}° ${v < 0 ? neg : pos}`;
  const scale = $derived(store.map ? `Natural Earth 1:${store.map.resolution.replace("m", "")} million` : "");
</script>

<footer class="flex h-7 items-center gap-5 border-t border-line bg-panel px-3 text-[12px] text-muted">
  <span class="w-44 shrink-0 tabular-nums">
    {#if store.cursor}{fmt(store.cursor[1], "N", "S")}, {fmt(store.cursor[0], "E", "W")}{:else}&nbsp;{/if}
  </span>
  <span class="shrink-0">{scale}</span>
  {#if store.busy}<LoaderCircle size={13} class="shrink-0 animate-spin" aria-label="Drawing" />{/if}
  <span class="min-w-0 flex-1 truncate text-right" title={store.error ?? store.status}>
    {#if store.error}
      <span class="inline-flex items-center gap-1 text-danger"><CircleAlert size={13} /> {store.error}</span>
    {:else}
      {store.status}
    {/if}
  </span>
</footer>
