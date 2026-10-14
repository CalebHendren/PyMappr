<script lang="ts">
  // One line of map text, placed and drawn as matplotlib draws a Text: laid
  // out with Agg's metrics at the figure's dpi, then drawn as Agg's hinted
  // glyphs, or, with a halo (a path effect), as TextToPath's outlines with a
  // white stroke under them. A vector export keeps it as editable <text>.
  import type { Figure } from "$lib/layout";
  import { pxPerUnit } from "$lib/layout";
  import { type HAlign, type TextFont, type VAlign, aggOrigin, placeText, textData, textShape } from "$lib/mpltext.svelte";
  import { MAP_FONT } from "$lib/styles";

  let {
    fig,
    text,
    x,
    y,
    font,
    color,
    ha = "left",
    va = "baseline",
    halo = null,
    extent = null,
    ...rest
  }: {
    fig: Figure;
    text: string;
    /** The anchor, in figure units. */
    x: number;
    y: number;
    font: TextFont;
    color: string;
    ha?: HAlign;
    va?: VAlign;
    /** matplotlib's withStroke: width in points, colour and alpha. */
    halo?: { width: number; color: string; alpha: number } | null;
    /** More of the artist (an annotation's arrow) for the reported box:
     * [x0, y0, x1, y1] in figure units. */
    extent?: [number, number, number, number] | null;
    [attr: string]: unknown;
  } = $props();

  const k = $derived(pxPerUnit(fig));
  const layoutShape = $derived(textShape(text, font, fig.dpi, fig.vector ? "path" : "agg"));
  const placed = $derived(layoutShape ? placeText(layoutShape, font.size, fig.dpi, ha, va) : null);
  /** Baseline start in canvas pixels. */
  const base = $derived(placed ? [x * k + placed.dx, y * k + placed.dy] : null);
  const drawShape = $derived(fig.vector ? null : textShape(text, font, fig.dpi, halo ? "path" : "agg"));
  const origin = $derived(base ? (halo ? base : aggOrigin(base[0], base[1], fig.h * k)) : null);
  const data = $derived.by(() => {
    if (!placed) return null;
    let [x0, y0] = [x + placed.box.x / k, y + placed.box.y / k];
    let [x1, y1] = [x0 + placed.box.w / k, y0 + placed.box.h / k];
    if (extent) [x0, y0, x1, y1] = [Math.min(x0, extent[0]), Math.min(y0, extent[1]), Math.max(x1, extent[2]), Math.max(y1, extent[3])];
    return textData(text, x, y, font, color, { x: x0, y: y0, w: x1 - x0, h: y1 - y0 });
  });
</script>

{#if base && data}
  {#if fig.vector}
    <text
      x={base[0] / k}
      y={base[1] / k}
      font-family={MAP_FONT}
      font-size={font.size * fig.perPt}
      font-weight={font.bold ? "bold" : "normal"}
      font-style={font.italic ? "italic" : "normal"}
      fill={color}
      stroke={halo?.color}
      stroke-opacity={halo?.alpha}
      stroke-width={halo ? halo.width * fig.perPt : undefined}
      stroke-linejoin="round"
      paint-order="stroke"
      xml:space="preserve"
      style="white-space: pre"
      {...data}
      {...rest}>{text}</text
    >
  {:else if drawShape && origin}
    {@const t = `translate(${origin[0] / k} ${origin[1] / k}) scale(${1 / k})`}
    {#if halo}
      <!-- withStroke: the stroke pass fills too, then the plain fill on top. -->
      <path
        d={drawShape.path}
        transform={t}
        fill={color}
        stroke={halo.color}
        stroke-opacity={halo.alpha}
        stroke-width={(halo.width * fig.dpi) / 72}
        stroke-linejoin="round"
      />
    {/if}
    <path d={drawShape.path} transform={t} fill={color} {...data} {...rest} />
  {/if}
{/if}
