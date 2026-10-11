<script lang="ts">
  // A complete map figure: MapSvg plus the legend. Used on screen (inside
  // MapView) and mounted offscreen to build exports, so both are identical.
  import type { ComponentProps } from "svelte";
  import LegendLayer from "./LegendLayer.svelte";
  import MapSvg from "./MapSvg.svelte";

  type Props = Omit<ComponentProps<typeof MapSvg>, "legend"> & { showLegend: boolean };
  let { showLegend, svgEl = $bindable(null), ...rest }: Props = $props();
</script>

<MapSvg bind:svgEl {...rest} legend={showLegend ? legendSnippet : undefined} />

{#snippet legendSnippet()}
  <LegendLayer fig={rest.fig} />
{/snippet}
