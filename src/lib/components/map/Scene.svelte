<script lang="ts">
  // A complete map figure: MapSvg plus the legend. Used on screen (inside
  // MapView) and mounted offscreen to build exports, so both are identical.
  import type { ComponentProps } from "svelte";
  import type { DrawnLegend } from "$lib/legend";
  import type { LegendOptions } from "$lib/model";
  import { legendObstacles } from "$lib/obstacles";
  import LegendLayer from "./LegendLayer.svelte";
  import MapSvg from "./MapSvg.svelte";

  type Props = Omit<ComponentProps<typeof MapSvg>, "legend"> & {
    legend: DrawnLegend | null;
    legendOptions: LegendOptions;
    pointEdge: { color: string; width: number };
  };
  let { legend, legendOptions, pointEdge, svgEl = $bindable(null), ...rest }: Props = $props();

  // Everything else on the map that "best" keeps the legend off.
  const obstacles = $derived(
    legendObstacles({
      fig: rest.fig,
      view: rest.view,
      map: rest.map,
      settings: rest.settings,
      scaleBar: rest.scaleBar ?? null,
      inset: rest.inset ?? null,
      labelOffsets: rest.labelOffsets ?? {},
    }),
  );

  const points = $derived(
    rest.marks.map((m) => {
      const v = rest.view;
      const b = rest.fig.box;
      return [b.x + ((m.x - v.x) / v.w) * b.w, b.y + ((m.y - v.y) / v.h) * b.h] as [number, number];
    }),
  );
</script>

<MapSvg bind:svgEl {...rest} legend={legend?.visible && legendOptions.show ? legendSnippet : undefined} />

{#snippet legendSnippet()}
  {#if legend}
    <LegendLayer
      fig={rest.fig}
      {legend}
      options={legendOptions}
      {pointEdge}
      points={[...points, ...obstacles.points]}
      {obstacles}
      scaleBar={rest.scaleBar ?? null}
      scaleBarOptions={rest.settings.scale_bar}
    />
  {/if}
{/snippet}
