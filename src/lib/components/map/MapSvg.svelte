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
  import { mapToFigure, pxPerUnit } from "$lib/layout";
  import { compassGeometry } from "$lib/compass";
  import { markerPx, snapPx } from "$lib/mpltext.svelte";
  import MplText from "./MplText.svelte";
  import type { MapSettings } from "$lib/model";
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
    SCALE_BAR,
    TICK,
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
  /** Raster pixels per figure unit. */
  const px = $derived(pxPerUnit(fig));
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

  /** A straight-edged shape's coordinate snapped as Agg snaps it (vector
   * exports are left alone). `width` is the stroke in points. */
  const snap = (v: number, width: number) => (fig.vector ? v : snapPx(v * px, width * pt * px) / px);
  const snapRect = (r: Rect, width: number) => {
    const x0 = snap(r.x, width);
    const y0 = snap(r.y, width);
    return { x: x0, y: y0, w: snap(r.x + r.w, width) - x0, h: snap(r.y + r.h, width) - y0 };
  };

  /** A tick: matplotlib draws it as a marker, stamped at the nearest pixel
   * corner with its own straight path snapped; (dx, dy) is its far end in
   * points from the spine. */
  function tickMark(x: number, y: number, dx: number, dy: number) {
    if (fig.vector) return { x1: x, y1: y, x2: x + dx * pt, y2: y + dy * pt };
    const [ox, oy] = markerPx(x * px, y * px);
    const w = TICK.width * pt * px;
    const end = (d: number) => snapPx(d * pt * px, w);
    return { x1: (ox + snapPx(0, w)) / px, y1: (oy + snapPx(0, w)) / px, x2: (ox + end(dx)) / px, y2: (oy + end(dy)) / px };
  }
  const markerR = (area: number) => (Math.sqrt(area) / 2) * pt;

  // ---- compass -------------------------------------------------------------
  const compass = $derived(compassGeometry(fig, settings.compass_options));

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
      <MplText
        {fig}
        text={l.text}
        x={fx}
        y={fy}
        font={{ size: s.size * l.fontScale, bold: !!s.bold, italic: !!s.italic, family: "" }}
        color={s.color}
        ha="center"
        va={l.va === "bottom" ? "bottom" : "center"}
        halo={LABEL_HALO}
        data-label="{l.layer}|{l.text}"
      />
    {/each}
  </g>

  {#if !globe}
    <!-- The spines: straight lines, snapped to the pixel grid as Agg snaps them. -->
    {@const fb = snapRect(box, FRAME.width)}
    <rect x={fb.x} y={fb.y} width={fb.w} height={fb.h} fill="none" stroke={FRAME.color} stroke-width={FRAME.width * pt} />
  {/if}

  {#if showTicks && map.graticule}
    {@const tickFont = { size: GRATICULE.tickSize, bold: false, italic: false, family: "" }}
    {@const gap = (TICK.length + TICK.pad) * pt}
    {#each map.graticule.xTicks as t, i (i)}
      {@const fx = box.x + ((t.pos - view.x) / view.w) * box.w}
      {@const m = tickMark(fx, box.y + box.h, 0, TICK.length)}
      <line x1={m.x1} x2={m.x2} y1={m.y1} y2={m.y2} stroke="#000000" stroke-width={TICK.width * pt} />
      <!-- Tick labels sit the tick length plus matplotlib's 3.5 pt pad away. -->
      <MplText {fig} text={t.text} x={fx} y={box.y + box.h + gap} font={tickFont} color="#000000" ha="center" va="top" />
    {/each}
    {#each map.graticule.yTicks as t, i (i)}
      {@const fy = box.y + ((t.pos - view.y) / view.h) * box.h}
      {@const m = tickMark(box.x, fy, -TICK.length, 0)}
      <line x1={m.x1} x2={m.x2} y1={m.y1} y2={m.y2} stroke="#000000" stroke-width={TICK.width * pt} />
      <MplText {fig} text={t.text} x={box.x - gap} y={fy} font={tickFont} color="#000000" ha="right" va="center_baseline" />
    {/each}
  {/if}

  {#if scaleBar && settings.scale_bar.show}
    {@const sb = settings.scale_bar}
    <!-- PyMappr's bars and labels are placed in axes fractions. -->
    {@const fy = (f: number) => box.y + (1 - f) * box.h}
    <g data-drag="scalebar">
      {#each scaleBar.bars as bar, bi (bi)}
        {#each Array.from({ length: sb.style === "segmented" ? bar.segments : 1 }) as _, si (si)}
          {@const n = sb.style === "segmented" ? bar.segments : 1}
          {@const r = snapRect(
            { x: box.x + (bar.x + (bar.width * si) / n) * box.w, y: fy(bar.y + SCALE_BAR.height), w: (bar.width / n) * box.w, h: SCALE_BAR.height * box.h },
            SCALE_BAR.edge,
          )}
          <rect x={r.x} y={r.y} width={r.w} height={r.h} fill={si % 2 === 0 ? sb.color : "#ffffff"} stroke={sb.color} stroke-width={SCALE_BAR.edge * pt} />
        {/each}
        {@const above = bi === 0}
        <MplText
          {fig}
          text={bar.label}
          x={box.x + (bar.x + bar.width / 2) * box.w}
          y={fy(above ? bar.y + SCALE_BAR.height + SCALE_BAR.labelGap : bar.y - SCALE_BAR.labelGap)}
          font={{ size: sb.fontsize, bold: false, italic: false, family: "" }}
          color={sb.color}
          ha="center"
          va={above ? "bottom" : "top"}
          halo={LABEL_HALO}
        />
      {/each}
    </g>
  {/if}

  {#if compass}
    {@const k = compass}
    <g data-compass="true">
      {#if k.tri}
        <path d="M{k.tri[0].join(' ')}L{k.tri[1].join(' ')}L{k.tri[2].join(' ')}Z" fill={settings.compass_options.color} stroke="#ffffff" stroke-width={0.8 * k.c.size * pt} stroke-linejoin="miter" />
      {/if}
      {#if k.arrow}
        <path d={k.arrow.shaft} fill="none" stroke={settings.compass_options.color} stroke-width={k.arrow.width} stroke-linecap="butt" />
        <path d={k.arrow.head} fill={settings.compass_options.color} stroke={settings.compass_options.color} stroke-width={k.arrow.width} stroke-linejoin="miter" />
      {/if}
      <MplText {fig} text="N" x={k.label[0]} y={k.label[1]} font={k.font} color={settings.compass_options.color} ha="center" va="center" halo={LABEL_HALO} extent={k.arrow?.extent ?? null} />
    </g>
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
          {@const area = Math.max(m.size * INSET.pointScale, 3)}
          {@const r = markerR(area)}
          <path
            d={markerPath(m.marker)}
            transform="translate({fx} {fy}) scale({r})"
            fill={m.face}
            stroke={m.edgeWidth > 0 ? m.edge : "none"}
            stroke-width={(m.edgeWidth * INSET.lineScale * pt) / r}
            opacity={alpha}
            data-mark="{fx},{fy},{area},{m.face},{m.edge}"
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
