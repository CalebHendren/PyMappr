<script lang="ts">
  import { CircleAlert } from "@lucide/svelte";
  import { app } from "$lib/state.svelte";

  const fmt = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(4)}° ${v < 0 ? neg : pos}`;
  const scale = $derived(app.map ? `Natural Earth 1:${app.map.resolution.replace("m", "")} million` : "");
</script>

<footer class="flex h-7 items-center gap-5 border-t border-line bg-panel px-3 text-[12px] text-muted">
  <span class="w-44 tabular-nums">
    {#if app.cursor}{fmt(app.cursor[1], "N", "S")}, {fmt(app.cursor[0], "E", "W")}{:else}&nbsp;{/if}
  </span>
  <span>{scale}</span>
  <span>{app.pointCount} {app.pointCount === 1 ? "point" : "points"}</span>
  <span class="min-w-0 flex-1 truncate text-right" title={app.error ?? app.notice ?? ""}>
    {#if app.error}
      <span class="inline-flex items-center gap-1 text-danger"><CircleAlert size={13} /> {app.error}</span>
    {:else if app.notice}
      {app.notice}
    {/if}
  </span>
</footer>
