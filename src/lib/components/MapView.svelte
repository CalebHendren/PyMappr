<script lang="ts">
  import { untrack } from "svelte";
  import { api, type RenderRequest } from "$lib/api";
  import { app, fitView, groupKey, isHolotype } from "$lib/state.svelte";
  import { LAYERS, SHAPES, WATER } from "$lib/styles";
  import Legend from "./Legend.svelte";

  let container: HTMLDivElement;
  let requestSeq = 0;
  // The request whose result is already on screen (after fitting a fresh
  // projection the view changes, but nothing needs drawing again).
  let skipKey = "";

  // Screen pixels are `k` map units wide.
  const k = $derived(app.view ? app.view.w / app.size.w : 1);
  const pt = 1.25; // screen px per point of line width

  $effect(() => {
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) app.size = { w: width, h: height };
    });
    ro.observe(container);
    return () => ro.disconnect();
  });

  // Keep the view's shape matched to the window.
  $effect(() => {
    const { w, h } = app.size;
    const v = untrack(() => app.view);
    if (!v) return;
    const want = (v.w * h) / w;
    if (Math.abs(want - v.h) > v.h * 1e-6) app.view = { ...v, y: v.y + v.h / 2 - want / 2, h: want };
  });

  // Fetch the base map whenever what it shows changes.
  $effect(() => {
    if (!app.info?.dataDir) return;
    const request: RenderRequest = {
      projection: $state.snapshot(app.projection),
      view: app.view ? $state.snapshot(app.view) : null,
      pxWidth: Math.round(app.size.w),
      layers: LAYERS.map((l) => l.id).filter((id) => app.layers[id]),
      graticule: app.layers.graticule ? app.graticuleStep : 0,
    };
    const key = JSON.stringify(request);
    if (key === skipKey) return;
    const timer = setTimeout(
      async () => {
        const seq = ++requestSeq;
        app.busy = true;
        try {
          const map = await api.renderMap(request);
          if (seq !== requestSeq) return;
          app.map = map;
          app.error = map.missing.length ? map.missing.join("\n") : null;
          if (!request.view) {
            const view = fitView(map.extent, app.size);
            skipKey = JSON.stringify({ ...request, view });
            app.view = view;
          } else {
            skipKey = key;
          }
        } catch (e) {
          app.error = String(e);
        } finally {
          if (seq === requestSeq) app.busy = false;
        }
      },
      request.view ? 90 : 0,
    );
    return () => clearTimeout(timer);
  });

  // Project each dataset's points when the projection or the data change.
  $effect(() => {
    const projection = $state.snapshot(app.projection);
    const key = JSON.stringify(projection);
    for (const ds of app.datasets) {
      if (untrack(() => ds.xyKey) === key) continue;
      ds.xyKey = key;
      const lonlat = ds.points.map((p) => [p.lon, p.lat] as [number, number]);
      api.projectPoints(projection, lonlat).then((xy) => {
        if (ds.xyKey === key) ds.xy = xy;
      });
    }
  });

  // ---- pan, zoom, cursor ----------------------------------------------------
  let drag = $state<{ x: number; y: number; vx: number; vy: number } | null>(null);
  let cursorPending = false;

  function toMap(e: { clientX: number; clientY: number }): [number, number] {
    const r = container.getBoundingClientRect();
    const v = app.view!;
    return [v.x + (e.clientX - r.left) * k, v.y + (e.clientY - r.top) * k];
  }

  function onPointerDown(e: PointerEvent) {
    if (e.button !== 0 || !app.view) return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    drag = { x: e.clientX, y: e.clientY, vx: app.view.x, vy: app.view.y };
  }

  function onPointerMove(e: PointerEvent) {
    if (!app.view) return;
    if (drag) {
      app.view = { ...app.view, x: drag.vx - (e.clientX - drag.x) * k, y: drag.vy - (e.clientY - drag.y) * k };
    }
    if (cursorPending) return;
    cursorPending = true;
    const [x, y] = toMap(e);
    api
      .unproject($state.snapshot(app.projection), x, y)
      .then((ll) => (app.cursor = ll))
      .finally(() => (cursorPending = false));
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    app.zoomBy(Math.exp(-e.deltaY * 0.0015), toMap(e));
  }

  function onKey(e: KeyboardEvent) {
    if (!app.view) return;
    const step = app.view.w * 0.1;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    if (moves[e.key]) {
      const [dx, dy] = moves[e.key];
      app.view = { ...app.view, x: app.view.x + dx, y: app.view.y + dy };
    } else if (e.key === "+" || e.key === "=") app.zoomBy(1.5);
    else if (e.key === "-") app.zoomBy(1 / 1.5);
    else if (e.key === "0") app.fit();
    else return;
    e.preventDefault();
  }

  const layerById = (id: string) => app.map?.layers.find((l) => l.id === id);
  const fillFor = (fill: string | null) =>
    fill === "lakes" ? (app.lakeFill === "none" ? "none" : WATER.lakes[app.lakeFill]) : (fill ?? "none");
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div
  bind:this={container}
  class="relative h-full w-full overflow-hidden outline-none"
  class:cursor-grab={!drag}
  class:cursor-grabbing={!!drag}
  tabindex="0"
  role="application"
  aria-label="Map. Drag to pan, scroll or press plus and minus to zoom, 0 to fit."
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={() => (drag = null)}
  onpointerleave={() => (app.cursor = null)}
  onwheel={onWheel}
  onkeydown={onKey}
>
  {#if app.view && app.map}
    {@const v = app.view}
    <svg
      bind:this={app.svgEl}
      xmlns="http://www.w3.org/2000/svg"
      width={app.size.w}
      height={app.size.h}
      viewBox="{v.x} {v.y} {v.w} {v.h}"
      class="absolute inset-0"
    >
      <defs>
        {#each Object.entries(SHAPES) as [id, shape] (id)}
          <path id="m-{id}" d={shape.d} />
        {/each}
      </defs>
      <path d={app.map.outline} fill={WATER.ocean[app.oceanFill]} stroke="none" />
      {#each LAYERS as layer (layer.id)}
        {@const rendered = app.layers[layer.id] ? layerById(layer.id) : undefined}
        {#if rendered && rendered.d}
          <path
            d={rendered.d}
            fill={fillFor(layer.fill)}
            fill-rule="evenodd"
            stroke={layer.stroke ?? "none"}
            stroke-width={layer.width * pt * k}
            stroke-linejoin="round"
            stroke-linecap="round"
            opacity={layer.id === "graticule" ? 0.7 : 1}
          />
        {/if}
      {/each}
      <path d={app.map.outline} fill="none" stroke="#333333" stroke-width={0.8 * pt * k} />

      {#each app.datasets as ds (ds.id)}
        {#if ds.visible}
          <g opacity={app.opacity}>
            {#each ds.points as p, i (i)}
              {@const xy = ds.xy[i]}
              {@const style = app.groupStyles[`${ds.id}:${groupKey(ds, p.names)}`]}
              {#if xy && style?.visible !== false}
                {@const shape = style?.shape ?? "circle"}
                {@const color = style?.color ?? "#d62728"}
                {@const r = (app.pointSize / 2) * k}
                {@const open = isHolotype(ds, p.names)}
                {@const line = SHAPES[shape]?.line}
                <use
                  href="#m-{shape}"
                  transform="translate({xy[0]} {xy[1]}) scale({r})"
                  fill={open || line ? "none" : color}
                  stroke={open || line ? color : app.outlineColor}
                  stroke-width={(open || line ? 1.6 : app.outlineWidth * pt) / (app.pointSize / 2)}
                />
              {/if}
            {/each}
          </g>
        {/if}
      {/each}

      {#if app.legend.show && app.groups.length}
        <g transform="translate({v.x} {v.y}) scale({k})">
          <Legend />
        </g>
      {/if}
    </svg>
  {/if}
</div>
