<script lang="ts">
  // The map legend in figure units: the matplotlib-style legend (drawn in
  // points from the map box's top-left) scaled into the figure.
  import type { ScaleBar } from "$lib/api";
  import type { Figure } from "$lib/layout";
  import type { DrawnLegend } from "$lib/legend";
  import type { LegendOptions, ScaleBarOptions } from "$lib/model";
  import Legend from "../legend/Legend.svelte";
  import type { LegendClearance } from "../legend/layout";
  import type { Mark } from "./MapSvg.svelte";

  let {
    fig,
    legend,
    options,
    pointEdge,
    points,
    scaleBar,
    scaleBarOptions,
  }: {
    fig: Figure;
    legend: DrawnLegend;
    options: LegendOptions;
    pointEdge: { color: string; width: number };
    /** Point positions in figure units, for "best" placement. */
    points: [number, number][];
    scaleBar: ScaleBar | null;
    scaleBarOptions: ScaleBarOptions;
  } = $props();

  const box = $derived(fig.box);
  const boxPt = $derived({ w: box.w / fig.perPt, h: box.h / fig.perPt });
  const pointsPt = $derived(points.map(([x, y]) => [(x - box.x) / fig.perPt, (y - box.y) / fig.perPt] as [number, number]));

  // A legend in the scale bar's corner sits beyond the bar and its label
  // (PyMappr's _scale_bar_clearance): an axes fraction plus points.
  const clear = $derived.by((): LegendClearance | null => {
    if (!scaleBar || !scaleBarOptions.show || !scaleBar.bars.length || scaleBarOptions.anchor_x !== null) return null;
    const text = scaleBarOptions.fontsize * 1.4;
    const ys = scaleBar.bars.map((b) => b.y);
    if (scaleBarOptions.position.startsWith("lower")) {
      const stack = Math.max(...ys) - Math.min(...ys) + 0.011;
      return { corner: scaleBarOptions.position, frac: Math.min(...ys) + stack + 0.012, liftPt: text };
    }
    if (scaleBar.bars.length > 1) return { corner: scaleBarOptions.position, frac: Math.min(...ys) - 0.012, liftPt: -text };
    return { corner: scaleBarOptions.position, frac: Math.min(...ys), liftPt: 0 };
  });
</script>

<g data-legend="true" data-drag="legend" transform="translate({box.x} {box.y}) scale({fig.perPt})">
  <Legend {legend} {options} {boxPt} {fig} origin={{ x: box.x, y: box.y }} {pointEdge} {pointsPt} {clear} />
</g>
