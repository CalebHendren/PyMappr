<script lang="ts">
  // The map legend as an SVG group in POINT units, laid out the way
  // matplotlib lays out PyMappr's legend (see ./layout.ts). Place it inside
  // an SVG whose user units are points over the map box, top-left origin.
  // Text is measured with matplotlib's own metrics at the figure's dpi and
  // drawn as the glyph outlines Agg draws (editable text in a vector export).
  import type { DrawnLegend, DrawnLegendRow } from "$lib/legend";
  import type { LegendOptions } from "$lib/model";
  import type { Figure } from "$lib/layout";
  import { pxPerUnit } from "$lib/layout";
  import { aggOrigin, markerPx, snapPx, textData, textShape } from "$lib/mpltext.svelte";
  import { markerPathAt } from "$lib/markers";
  import { DEJAVU_STACKS, type LegendClearance, type LegendLayout, type Measure, type PlacedMarker, type PlacedText, type Rect, dejaVuExtent, fontAttrs, framePath, legendLayout } from "./layout";

  let {
    legend,
    options,
    boxPt,
    fig,
    origin,
    pointEdge = { color: "#ffffff", width: 0.5 },
    markerSize,
    pointsPt,
    avoidPt,
    linesPt,
    clear = null,
    onlayout,
  }: {
    /** symbology(state).legend */
    legend: DrawnLegend;
    /** The legend options as drawn (symbology(state).options). */
    options: LegendOptions;
    /** The map box in points. */
    boxPt: { w: number; h: number };
    /** The figure it is drawn in: its dpi decides the text metrics. */
    fig: Figure;
    /** The map box's top-left corner in figure units. */
    origin: { x: number; y: number };
    /** The project's point outline (state.point_edge). */
    pointEdge?: { color: string; width: number };
    /** Swatch area (pt²) per row; the row's own by default. */
    markerSize?: (row: DrawnLegendRow) => number;
    /** Map points in the same coordinates, for location "best". */
    pointsPt?: [number, number][];
    /** Other boxes "best" keeps clear of. */
    avoidPt?: Rect[];
    /** Other shapes "best" keeps clear of (vertex lists). */
    linesPt?: [number, number][][];
    /** A scale bar or inset in the legend's corner. */
    clear?: LegendClearance | null;
    /** Called with the layout whenever it changes (the box is what a drag
     * handle needs; null when nothing is drawn). */
    onlayout?: (layout: LegendLayout | null) => void;
  } = $props();

  const mode = $derived(fig.vector ? "path" : "agg");
  /** Raster pixels per point. */
  const pxPt = $derived(fig.dpi / 72);

  const measure: Measure = (text, font) => {
    const s = textShape(text, font, fig.dpi, mode);
    // A stand-in until the backend answers; the layout re-runs then.
    if (!s) return { width: 0.6 * font.size * text.length, height: font.size, descent: 0.2 * font.size };
    return { width: s.w / pxPt, height: s.h / pxPt, descent: s.d / pxPt };
  };

  const layout = $derived(legendLayout({ legend, options, boxPt, measure, fontExtent: dejaVuExtent, markerSize, pointsPt, avoidPt, linesPt, clear, pointEdge, pxPerPt: pxPt }));

  $effect(() => {
    onlayout?.(layout);
  });

  /** Agg's glyph origin for a text at (x, y) legend points, back in points. */
  function glyphs(t: PlacedText) {
    const s = textShape(t.text, t.font, fig.dpi, "agg");
    if (!s) return null;
    const k = pxPerUnit(fig);
    const [ox, oy] = aggOrigin((origin.x + t.x * fig.perPt) * k, (origin.y + t.y * fig.perPt) * k, fig.h * k);
    return { d: s.path, x: (ox / k - origin.x) / fig.perPt, y: (oy / k - origin.y) / fig.perPt, scale: 1 / pxPt };
  }

  /** An underline, snapped to the pixel grid as Agg snaps a straight line. */
  function underlineY(y: number, width: number): number {
    const k = pxPerUnit(fig);
    return (snapPx((origin.y + y * fig.perPt) * k, width * pxPt) / k - origin.y) / fig.perPt;
  }
  function underlineX(x: number, width: number): number {
    const k = pxPerUnit(fig);
    return (snapPx((origin.x + x * fig.perPt) * k, width * pxPt) / k - origin.x) / fig.perPt;
  }

  /** A square frame, snapped as Agg snaps straight-edged paths. */
  const frameD = $derived.by(() => {
    const f = layout?.frame;
    if (!f || !layout) return "";
    if (fig.vector || options.rounded) return f.d;
    const k = pxPerUnit(fig);
    const sx = (v: number) => (snapPx((origin.x + v * fig.perPt) * k, f.width * pxPt) / k - origin.x) / fig.perPt;
    const sy = (v: number) => (snapPx((origin.y + v * fig.perPt) * k, f.width * pxPt) / k - origin.y) / fig.perPt;
    const b = layout.box;
    const x0 = sx(b.x);
    const y0 = sy(b.y);
    return framePath({ x: x0, y: y0, w: sx(b.x + b.w) - x0, h: sy(b.y + b.h) - y0 }, 0);
  });

  /** A swatch stamped at the nearest pixel corner, as Agg draws markers. */
  function swatchD(m: PlacedMarker): string {
    if (fig.vector) return m.d;
    const k = pxPerUnit(fig);
    const [px, py] = markerPx((origin.x + m.cx * fig.perPt) * k, (origin.y + m.cy * fig.perPt) * k);
    return markerPathAt(m.style.marker, m.size, (px / k - origin.x) / fig.perPt, (py / k - origin.y) / fig.perPt);
  }
</script>

{#snippet label(t: PlacedText)}
  {@const data = textData(t.text, origin.x + t.x * fig.perPt, origin.y + t.y * fig.perPt, t.font, t.color, {
    x: origin.x + t.box.x * fig.perPt,
    y: origin.y + t.box.y * fig.perPt,
    w: t.box.w * fig.perPt,
    h: t.box.h * fig.perPt,
  })}
  {#if fig.vector}
    <text x={t.x} y={t.y} fill={t.color} xml:space="preserve" style="white-space: pre" {...fontAttrs(t.font, DEJAVU_STACKS)} {...data}>{t.text}</text>
  {:else}
    {@const g = glyphs(t)}
    {#if g}
      <path d={g.d} transform="translate({g.x} {g.y}) scale({g.scale})" fill={t.color} {...data} />
    {/if}
  {/if}
  {#if t.underline}
    {@const u = t.underline}
    {@const y = underlineY(u.y, u.width)}
    <line x1={underlineX(u.x1, u.width)} x2={underlineX(u.x2, u.width)} y1={y} y2={y} stroke={t.color} stroke-width={u.width} />
  {/if}
{/snippet}

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
        d={frameD}
        fill={layout.frame.fill}
        fill-opacity={layout.frame.alpha}
        stroke={layout.frame.width > 0 ? layout.frame.stroke : "none"}
        stroke-opacity={layout.frame.alpha}
        stroke-width={layout.frame.width}
        stroke-linejoin="miter"
        data-frame="{origin.x + layout.box.x * fig.perPt},{origin.y + layout.box.y * fig.perPt},{layout.box.w * fig.perPt},{layout.box.h * fig.perPt}"
      />
    {/if}
    {#if layout.title}
      {@render label(layout.title)}
    {/if}
    {#each layout.rows as row, i (i)}
      {#if row.marker}
        <path
          d={swatchD(row.marker)}
          fill={row.marker.face}
          stroke={row.marker.edgeWidth > 0 ? row.marker.edge : "none"}
          stroke-width={row.marker.edgeWidth}
          stroke-linejoin={row.marker.join}
        />
      {/if}
      {@render label(row.text)}
    {/each}
  </g>
{/if}
