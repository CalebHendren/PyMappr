<script lang="ts" module>
  /** A user point, already projected (SVG map coordinates) and painted. */
  export type Mark = {
    x: number;
    y: number;
    marker: string;
    /** matplotlib area in pt². */
    size: number;
    face: string;
    edge: string;
    /** Outline width in pt. */
    edgeWidth: number;
  };
</script>

<script lang="ts">
  // One map figure, drawn from props alone so the same component renders the
  // screen and every export. Figure units are pixels on screen and points in
  // an export (`fig.perPt` converts). Map content sits in a nested <svg>
  // whose viewBox is the view; overlays (labels, points, ticks, legend,
  // compass, scale bar, inset) are drawn in figure units on top.
  import type { Snippet } from "svelte";
  import type { Rect, RenderedInset, RenderedMap, ScaleBar } from "$lib/api";
  import type { Figure } from "$lib/layout";
  import { mapToFigure } from "$lib/layout";
  import type { CompassOptions, MapSettings } from "$lib/model";
  import { markerPath } from "$lib/markers";
  import {
    BATHYMETRY,
    FILL_STYLES,
    FRAME,
    GRATICULE,
    INSET,
    LABEL_HALO,
    LABEL_STYLES,
    LINE_STYLES,
    MAP_FONT,
    NE_MARKERS,
    PORTRAIT_MAT,
    WATER,
  } from "$lib/styles";

  type Props = {
    fig: Figure;
    view: Rect;
    map: RenderedMap;
    settings: MapSettings;
    globe: boolean;
    marks: Mark[];
    alpha: number;
    showTicks: boolean;
    labelOffsets?: Record<string, [number, number]>;
    scaleBar?: ScaleBar | null;
    inset?: RenderedInset | null;
    insetMarks?: Mark[];
    /** The legend, drawn by the caller in figure units. */
    legend?: Snippet;
    svgEl?: SVGSVGElement | null;
    /** Width/height attributes; screen pixels by default. */
    sizeUnit?: "" | "pt";
  };

  let {
    fig,
    view,
    map,
    settings,
    globe,
    marks,
    alpha,
    showTicks,
    labelOffsets = {},
    scaleBar = null,
    inset = null,
    insetMarks = [],
    legend,
    svgEl = $bindable(null),
    sizeUnit = "",
  }: Props = $props();

  const pt = $derived(fig.perPt);
  // DejaVu Sans's typo ascender and descender per em, as matplotlib lays text out.
  const ASCENT = 1556 / 2048;
  const DESCENT = 492 / 2048;
  const box = $derived(fig.box);
  /** Map units per figure unit. */
  const k = $derived(view.w / box.w);
  const lineScale = $derived(settings.line_width || 1);
  const clipId = `mapclip-${Math.random().toString(36).slice(2, 8)}`;

  function layerStyle(id: string, kind: "fill" | "line", scale: number, unitsPerPt: number) {
    if (id.startsWith("bathymetry:")) {
      return { fill: BATHYMETRY[Number(id.slice(11))] ?? "#c0dff0", stroke: "none", width: 0, opacity: 1, dash: undefined };
    }
    if (kind === "fill") {
      if (id === "lakes") {
        const face = WATER.lakes[settings.lake_fill];
        return { fill: face ?? "none", stroke: "none", width: 0, opacity: 1, dash: undefined };
      }
      const s = FILL_STYLES[id] ?? { face: "#cccccc", edge: null, width: 0, alpha: 1 };
      return {
        fill: s.face,
        stroke: s.edge ?? "none",
        width: s.width * scale * unitsPerPt,
        opacity: s.alpha,
        dash: undefined,
      };
    }
    const s = LINE_STYLES[id] ?? { color: "#555555", width: 0.5, dash: null };
    const w = s.width * scale * unitsPerPt;
    return {
      fill: "none",
      stroke: s.color,
      width: w,
      opacity: 1,
      dash: s.dash ? s.dash.map((d) => d * w).join(" ") : undefined,
    };
  }

  const toFig = (x: number, y: number) => mapToFigure(view, box, x, y);
  const markerR = (area: number) => (Math.sqrt(area) / 2) * pt;

  // ---- compass -------------------------------------------------------------
  const compass = $derived.by(() => {
    const o: CompassOptions = settings.compass_options;
    if (!o.show) return null;
    const size = o.size || 1;
    const reach = 0.07 * size * box.h;
    const pad = 0.025;
    const right = o.position.includes("right");
    const upper = o.position.includes("upper");
    const x = right ? box.x + box.w * (1 - pad) - 6 * pt * size : box.x + box.w * pad + 6 * pt * size;
    const nSize = (o.style === "arrow" ? 11 : 10) * size * pt;
    // Top corner: the tip is at the anchor; bottom corner: the N sits on it.
    const tipY = upper ? box.y + box.h * pad : box.y + box.h * (1 - pad) - nSize * 0.5 - reach - nSize;
    return { o, size, x, tipY, reach, nSize };
  });

  // ---- inset ---------------------------------------------------------------
  // The backend places the inset (corner, drag anchor, stepping around a
  // scale bar) in axes fractions from the bottom-left, as PyMappr does.
  const insetBox = $derived.by(() => {
    if (!inset || !settings.inset.show) return null;
    const r = inset.rect;
    return { x: box.x + r.x * box.w, y: box.y + (1 - r.y - r.h) * box.h, w: r.w * box.w, h: r.h * box.h };
  });
  const insetK = $derived(inset && insetBox ? inset.view.w / insetBox.w : 1);
</script>

<svg
  bind:this={svgEl}
  xmlns="http://www.w3.org/2000/svg"
  width="{fig.w}{sizeUnit}"
  height="{fig.h}{sizeUnit}"
  viewBox="0 0 {fig.w} {fig.h}"
  font-family={MAP_FONT}
>
  <defs>
    <clipPath id={clipId}><rect x={box.x} y={box.y} width={box.w} height={box.h} /></clipPath>
  </defs>
  <rect width={fig.w} height={fig.h} fill={fig.mat ? PORTRAIT_MAT : "#ffffff"} />
  <rect x={box.x} y={box.y} width={box.w} height={box.h} fill="#ffffff" />

  <!-- Map content in map units. -->
  <svg x={box.x} y={box.y} width={box.w} height={box.h} viewBox="{view.x} {view.y} {view.w} {view.h}" preserveAspectRatio="none">
    {#if map.raster}
      <image href={map.raster.href} x={map.raster.x} y={map.raster.y} width={map.raster.w} height={map.raster.h} preserveAspectRatio="none" />
    {/if}
    {#if WATER.ocean[settings.ocean]}
      <path d={map.outline} fill={WATER.ocean[settings.ocean]} />
    {/if}
    {#each map.layers as layer, i (layer.id + i)}
      {@const s = layerStyle(layer.id, layer.kind, lineScale, pt * k)}
      {#if layer.d}
        <path
          d={layer.d}
          fill={s.fill}
          fill-rule="nonzero"
          fill-opacity={s.opacity}
          stroke={s.stroke}
          stroke-width={s.width}
          stroke-dasharray={s.dash}
          stroke-linejoin="round"
          stroke-linecap="round"
        />
      {/if}
    {/each}
    {#if map.graticule}
      <path
        d={map.graticule.d}
        fill="none"
        stroke={GRATICULE.color}
        stroke-opacity={GRATICULE.alpha}
        stroke-width={GRATICULE.width * pt * k}
      />
      {#if map.graticule.horizon}
        <path d={map.graticule.horizon} fill="none" stroke={GRATICULE.color} stroke-width={GRATICULE.horizonWidth * pt * k} />
      {/if}
    {/if}
    {#if inset && insetBox && settings.inset.box && inset.box.on === "map" && inset.box.d}
      <path d={inset.box.d} fill="none" stroke={settings.inset.box_color} stroke-width={INSET.boxWidth * pt * k} />
    {/if}
  </svg>

  <!-- Points, markers and labels in figure units, clipped to the map box. -->
  <g clip-path="url(#{clipId})">
    {#each map.markers as m, i (i)}
      {@const s = NE_MARKERS[m.layer]}
      {@const [fx, fy] = toFig(m.x, m.y)}
      <path
        d={markerPath(s.marker)}
        transform="translate({fx} {fy}) scale({markerR(s.size)})"
        fill={s.face}
        stroke={s.edge}
        stroke-width={(0.5 * pt) / markerR(s.size)}
        data-mark="{fx},{fy},{s.size},{s.face},{s.edge}"
      />
    {/each}
    <g opacity={alpha}>
      {#each marks as m, i (i)}
        {@const [fx, fy] = toFig(m.x, m.y)}
        {@const r = markerR(m.size)}
        <path
          d={markerPath(m.marker)}
          transform="translate({fx} {fy}) scale({r})"
          fill={m.face}
          stroke={m.edgeWidth > 0 ? m.edge : "none"}
          stroke-width={(m.edgeWidth * pt) / r}
          data-mark="{fx},{fy},{m.size},{m.face},{m.edge}"
        />
      {/each}
    </g>
    {#each map.labels as l, i (i)}
      {@const s = LABEL_STYLES[l.layer] ?? LABEL_STYLES.states}
      {@const off = labelOffsets[`${l.layer}|${l.text}`] ?? [0, 0]}
      {@const [fx, fy] = toFig(l.x + off[0], l.y + off[1])}
      {@const size = s.size * l.fontScale * pt}
      <!-- matplotlib places the text box from DejaVu's ascent and descent. -->
      <text
        x={fx}
        y={l.va === "bottom" ? fy - DESCENT * size : fy + ((ASCENT - DESCENT) / 2) * size}
        data-anchor="{fx},{fy}"
        font-size={size}
        font-weight={s.bold ? "bold" : "normal"}
        font-style={s.italic ? "italic" : "normal"}
        text-anchor="middle"
        fill={s.color}
        stroke={LABEL_HALO.color}
        stroke-opacity={LABEL_HALO.alpha}
        stroke-width={LABEL_HALO.width * pt}
        stroke-linejoin="round"
        paint-order="stroke"
        data-label="{l.layer}|{l.text}">{l.text}</text
      >
    {/each}
  </g>

  {#if !globe}
    <rect x={box.x} y={box.y} width={box.w} height={box.h} fill="none" stroke={FRAME.color} stroke-width={FRAME.width * pt} />
  {/if}

  {#if showTicks && map.graticule}
    {@const fs = GRATICULE.tickSize * pt}
    {@const tick = 2.5 * pt}
    {@const gap = (2.5 + 3.5) * pt}
    <g font-size={fs} fill="#000000">
      {#each map.graticule.xTicks as t, i (i)}
        {@const fx = box.x + ((t.pos - view.x) / view.w) * box.w}
        <line x1={fx} x2={fx} y1={box.y + box.h} y2={box.y + box.h + tick} stroke="#000000" stroke-width={FRAME.width * pt} />
        <!-- Tick labels sit the tick length plus matplotlib's 3.5 pt pad away. -->
        <text x={fx} y={box.y + box.h + gap + ASCENT * fs} text-anchor="middle" data-anchor="{fx},{box.y + box.h + gap}">{t.text}</text>
      {/each}
      {#each map.graticule.yTicks as t, i (i)}
        {@const fy = box.y + ((t.pos - view.y) / view.h) * box.h}
        <line x1={box.x - tick} x2={box.x} y1={fy} y2={fy} stroke="#000000" stroke-width={FRAME.width * pt} />
        <text x={box.x - gap} y={fy + ((ASCENT - DESCENT) / 2) * fs} text-anchor="end" data-anchor="{box.x - gap},{fy}">{t.text}</text>
      {/each}
    </g>
  {/if}

  {#if scaleBar && settings.scale_bar.show}
    {@const sb = settings.scale_bar}
    {@const barH = 0.011 * box.h}
    <g font-size={sb.fontsize * pt} fill={sb.color} data-drag="scalebar">
      {#each scaleBar.bars as bar, bi (bi)}
        {@const x0 = box.x + bar.x * box.w}
        {@const w = bar.width * box.w}
        {@const y0 = box.y + (1 - bar.y) * box.h - barH}
        {#if sb.style === "segmented"}
          {#each Array.from({ length: bar.segments }) as _, si (si)}
            <rect
              x={x0 + (w / bar.segments) * si}
              y={y0}
              width={w / bar.segments}
              height={barH}
              fill={si % 2 === 0 ? sb.color : "#ffffff"}
              stroke={sb.color}
              stroke-width={0.8 * pt}
            />
          {/each}
        {:else}
          <rect x={x0} y={y0} width={w} height={barH} fill={sb.color} stroke={sb.color} stroke-width={0.8 * pt} />
        {/if}
        {@const above = bar.units === "km" || scaleBar.bars.length === 1}
        <text
          x={x0 + w / 2}
          y={above ? y0 - 0.012 * box.h + sb.fontsize * pt * 0.2 : y0 + barH + 0.012 * box.h + sb.fontsize * pt * 0.7}
          text-anchor="middle"
          stroke="#ffffff"
          stroke-opacity={LABEL_HALO.alpha}
          stroke-width={LABEL_HALO.width * pt}
          paint-order="stroke">{bar.label}</text
        >
      {/each}
    </g>
  {/if}

  {#if compass}
    {@const c = compass}
    {@const col = c.o.color}
    {#if c.o.style === "arrow"}
      {@const tailY = c.tipY + c.reach}
      <g>
        <line x1={c.x} x2={c.x} y1={tailY} y2={c.tipY + c.nSize * 0.55} stroke={col} stroke-width={1.4 * c.size * pt} />
        <path
          d="M{c.x} {c.tipY} L{c.x - c.nSize * 0.28} {c.tipY + c.nSize * 0.6} L{c.x + c.nSize * 0.28} {c.tipY + c.nSize * 0.6} Z"
          fill={col}
        />
        <text
          x={c.x}
          y={tailY + c.nSize}
          font-size={c.nSize}
          font-weight="bold"
          text-anchor="middle"
          fill={col}
          stroke="#ffffff"
          stroke-width={LABEL_HALO.width * pt}
          paint-order="stroke">N</text
        >
      </g>
    {:else}
      {@const half = 0.016 * c.size * box.w}
      <g>
        <path
          d="M{c.x} {c.tipY} L{c.x - half} {c.tipY + c.reach * 0.75} L{c.x + half} {c.tipY + c.reach * 0.75} Z"
          fill={col}
          stroke="#ffffff"
          stroke-width={0.8 * c.size * pt}
        />
        <text x={c.x} y={c.tipY + c.reach * 0.75 + 0.02 * c.size * box.h + c.nSize} font-size={c.nSize} font-weight="bold" text-anchor="middle" fill={col}
          >N</text
        >
      </g>
    {/if}
  {/if}

  {#if inset && insetBox}
    {@const o = settings.inset}
    {@const ib = insetBox}
    {@const iv = inset.view}
    {@const inGlobe = inset.projection.name.startsWith("Globe")}
    <g data-inset="true" data-drag="inset">
      {#if inGlobe}
        <svg x={ib.x} y={ib.y} width={ib.w} height={ib.h} viewBox="{iv.x} {iv.y} {iv.w} {iv.h}" preserveAspectRatio="none">
          <path d={inset.map.outline} fill={WATER.ocean[o.ocean] ?? "#ffffff"} stroke="#000000" stroke-width={INSET.frameWidth * pt * insetK} />
          {@render insetLayers()}
        </svg>
      {:else}
        <rect x={ib.x} y={ib.y} width={ib.w} height={ib.h} fill={WATER.ocean[o.ocean] ?? "#ffffff"} />
        <svg x={ib.x} y={ib.y} width={ib.w} height={ib.h} viewBox="{iv.x} {iv.y} {iv.w} {iv.h}" preserveAspectRatio="none">
          {@render insetLayers()}
        </svg>
        <rect x={ib.x} y={ib.y} width={ib.w} height={ib.h} fill="none" stroke="#000000" stroke-width={INSET.frameWidth * pt} />
      {/if}
      {#if o.points}
        {#each insetMarks as m, i (i)}
          {@const fx = ib.x + ((m.x - iv.x) / iv.w) * ib.w}
          {@const fy = ib.y + ((m.y - iv.y) / iv.h) * ib.h}
          {@const r = markerR(Math.max(m.size * INSET.pointScale, 3))}
          <path
            d={markerPath(m.marker)}
            transform="translate({fx} {fy}) scale({r})"
            fill={m.face}
            stroke={m.edgeWidth > 0 ? m.edge : "none"}
            stroke-width={(m.edgeWidth * INSET.lineScale * pt) / r}
            opacity={alpha}
          />
        {/each}
      {/if}
    </g>
  {/if}

  {@render legend?.()}
</svg>

{#snippet insetLayers()}
  {#if inset}
    {#each inset.map.layers as layer, i (layer.id + i)}
      {@const s = layerStyle(layer.id, layer.kind, Math.max(lineScale * INSET.lineScale, 0.2), pt * insetK)}
      {#if layer.d && layer.id !== "ocean"}
        <path
          d={layer.d}
          fill={layer.id === "land" ? INSET.land : s.fill}
          fill-rule="nonzero"
          fill-opacity={s.opacity}
          stroke={s.stroke}
          stroke-width={s.width}
          stroke-linejoin="round"
        />
      {/if}
    {/each}
    {#if settings.inset.box && inset.box.on === "inset" && inset.box.d}
      <path d={inset.box.d} fill="none" stroke={settings.inset.box_color} stroke-width={INSET.boxWidth * pt * insetK} />
    {/if}
  {/if}
{/snippet}
