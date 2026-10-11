<script lang="ts">
  // The map legend in figure units. Filled in from the symbology module
  // (legend rows + the matplotlib-style legend renderer).
  import type { Figure } from "$lib/layout";

  let { fig }: { fig: Figure } = $props();
</script>

<g data-legend="true" data-figure-width={fig.w}></g>
