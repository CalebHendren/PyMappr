<script lang="ts">
  // The map legend as an SVG group in POINT units, laid out the way
  // matplotlib lays out PyMappr's legend (see ./layout.ts). Place it inside
  // an SVG whose user units are points over the map box, top-left origin.
  import type { DrawnLegend, DrawnLegendRow } from "$lib/legend";
  import type { LegendOptions } from "$lib/model";
  import {
    type FontExtent,
    type LegendClearance,
    type LegendLayout,
    type Measure,
    type Rect,
    type FontSet,
    SYSTEM_FONTS,
    canvasMeasure,
    fontAttrs,
    legendLayout,
  } from "./layout";

  let {
    legend,
    options,
    boxPt,
    pointEdge = { color: "#ffffff", width: 0.5 },
    markerSize,
    pointsPt,
    avoidPt,
    clear = null,
    measure,
    fonts = SYSTEM_FONTS,
    fontExtent,
    onlayout,
  }: {
    /** symbology(state).legend */
    legend: DrawnLegend;
    /** The legend options as drawn (symbology(state).options). */
    options: LegendOptions;
    /** The map box in points. */
    boxPt: { w: number; h: number };
    /** The project's point outline (state.point_edge). */
    pointEdge?: { color: string; width: number };
    /** Swatch area (pt²) per row; the row's own by default. */
    markerSize?: (row: DrawnLegendRow) => number;
    /** Map points in the same coordinates, for location "best". */
    pointsPt?: [number, number][];
    /** Other boxes "best" keeps clear of. */
    avoidPt?: Rect[];
    /** A scale bar or inset in the legend's corner. */
    clear?: LegendClearance | null;
    /** Text measurement; a canvas with the legend's fonts by default. */
    measure?: Measure;
    /** The faces: SYSTEM_FONTS (Arial…) by default, or DEJAVU_FONTS for
     * PyMappr's exact geometry when the DejaVu fonts are loaded. */
    fonts?: FontSet;
    /** Overrides `fonts.extent`. */
    fontExtent?: FontExtent;
    /** Called with the layout whenever it changes (the box is what a drag
     * handle needs; null when nothing is drawn). */
    onlayout?: (layout: LegendLayout | null) => void;
  } = $props();

  let fallback: { stacks: Record<string, string>; measure: Measure } | null = null;
  const measureText: Measure = (text, font) => {
    if (measure) return measure(text, font);
    if (fallback?.stacks !== fonts.stacks) fallback = { stacks: fonts.stacks, measure: canvasMeasure(fonts.stacks) };
    return fallback.measure(text, font);
  };

  const layout = $derived(
    legendLayout({ legend, options, boxPt, measure: measureText, fontExtent: fontExtent ?? fonts.extent, markerSize, pointsPt, avoidPt, clear, pointEdge }),
  );

  $effect(() => {
    onlayout?.(layout);
  });
</script>

{#if layout}
  <g class="legend">
    {#if layout.frame}
      {#if layout.frame.shadow}
        <path
          d={layout.frame.shadow.d}
          fill={layout.frame.shadow.fill}
          stroke={layout.frame.shadow.fill}
          stroke-width={layout.frame.width}
          opacity="0.5"
        />
      {/if}
      <path
        d={layout.frame.d}
        fill={layout.frame.fill}
        fill-opacity={layout.frame.alpha}
        stroke={layout.frame.width > 0 ? layout.frame.stroke : "none"}
        stroke-opacity={layout.frame.alpha}
        stroke-width={layout.frame.width}
        stroke-linejoin="miter"
      />
    {/if}
    {#if layout.title}
      {@const t = layout.title}
      <text x={t.x} y={t.y} fill={t.color} xml:space="preserve" style="white-space: pre" {...fontAttrs(t.font, fonts.stacks)}>{t.text}</text>
      {#if t.underline}
        <line x1={t.underline.x1} x2={t.underline.x2} y1={t.underline.y} y2={t.underline.y} stroke={t.color} stroke-width={t.underline.width} />
      {/if}
    {/if}
    {#each layout.rows as row, i (i)}
      {#if row.marker}
        <path
          d={row.marker.d}
          fill={row.marker.face}
          stroke={row.marker.edgeWidth > 0 ? row.marker.edge : "none"}
          stroke-width={row.marker.edgeWidth}
          stroke-linejoin={row.marker.join}
        />
      {/if}
      <text x={row.text.x} y={row.text.y} fill={row.text.color} xml:space="preserve" style="white-space: pre" {...fontAttrs(row.text.font, fonts.stacks)}
        >{row.text.text}</text
      >
      {#if row.text.underline}
        {@const u = row.text.underline}
        <line x1={u.x1} x2={u.x2} y1={u.y} y2={u.y} stroke={row.text.color} stroke-width={u.width} />
      {/if}
    {/each}
  </g>
{/if}
