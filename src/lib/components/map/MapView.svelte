<script lang="ts">
  // The interactive map: sizes the figure to the window, asks the backend
  // for what to draw, and turns the mouse into pans, zooms, globe spins and
  // drags. Drawing itself is MapSvg's job.
  import { untrack } from "svelte";
  import { api, type RenderRequest } from "$lib/api";
  import { figureToMap, hasTicks, screenFigure } from "$lib/layout";
  import { insetMarks as buildInsetMarks, marks as buildMarks, type PointStyle } from "$lib/points";
  import { layerSettings, lonLats, store } from "$lib/store.svelte";
  import Scene from "./Scene.svelte";

  let { styles }: { styles: (PointStyle | null)[][] } = $props();

  let container: HTMLDivElement;
  let size = $state({ w: 900, h: 650 });

  const globe = $derived(store.doc.map.projection.startsWith("Globe"));
  const showTicks = $derived(hasTicks(store.doc.map.graticule, store.doc.map.hide_grid_labels, globe));
  const fig = $derived(screenFigure(size.w, size.h, showTicks, store.doc.map.orientation === "Portrait"));
  const k = $derived(store.view ? store.view.w / fig.box.w : 1);

  $effect(() => {
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      if (width > 10 && height > 10) size = { w: width, h: height };
    });
    ro.observe(container);
    return () => ro.disconnect();
  });

  $effect(() => {
    store.screenFig = fig;
  });

  // Keep the view's shape matched to the map box.
  $effect(() => {
    const aspect = fig.box.h / fig.box.w;
    store.boxAspect = aspect;
    const v = untrack(() => store.view);
    if (v && Math.abs(v.h / v.w - aspect) > 1e-6) {
      const h = v.w * aspect;
      store.view = { ...v, y: v.y + v.h / 2 - h / 2, h };
    }
  });

  // Frame the map when nothing is framed yet (startup, new projection).
  $effect(() => {
    if (!store.info?.dataDir || store.view) return;
    untrack(() => store.zoomToData());
  });

  // Draw: ask for the base map whenever what it shows changes.
  let seq = 0;
  $effect(() => {
    const view = store.view;
    if (!store.info?.dataDir || !view) return;
    const request: RenderRequest = {
      projection: $state.snapshot(store.projection),
      view: $state.snapshot(view),
      pxWidth: Math.round(fig.box.w),
      pxPerPt: fig.perPt,
      detailBoost: 0,
      layers: $state.snapshot(layerSettings(store.doc)),
      districts: $state.snapshot(store.districts),
    };
    const timer = setTimeout(async () => {
      const mine = ++seq;
      store.busy = true;
      try {
        const map = await api.renderMap(request);
        if (mine !== seq) return;
        store.map = map;
        if (map.missing.length) store.error = map.missing.join(" ");
      } catch (e) {
        if (mine === seq) store.fail(e);
      } finally {
        if (mine === seq) store.busy = false;
      }
    }, 80);
    return () => clearTimeout(timer);
  });

  // Project each dataset's points under the current projection.
  $effect(() => {
    const projection = $state.snapshot(store.projection);
    const key = JSON.stringify(projection);
    store.doc.datasets.forEach((ds, i) => {
      const slot = untrack(() => store.projected[i]);
      if (slot && slot.key === key && slot.xy.length === ds.rows.length) return;
      const pts = lonLats($state.snapshot(ds) as typeof ds);
      api.projectPoints(projection, pts).then((xy) => {
        if (store.projected[i]) store.projected[i] = { key, xy };
      });
    });
  });

  // Scale bar and inset follow the view.
  $effect(() => {
    const sb = $state.snapshot(store.doc.map.scale_bar);
    const view = store.view;
    if (!sb.show || !view) {
      store.scaleBar = null;
      return;
    }
    const request = {
      projection: $state.snapshot(store.projection),
      view: $state.snapshot(view),
      boxPt: { w: fig.box.w / fig.perPt, h: fig.box.h / fig.perPt },
      options: sb,
    };
    const timer = setTimeout(() => {
      api
        .scaleBar(request)
        .then((r) => {
          store.scaleBar = r;
          if (r.error) store.status = r.error;
        })
        .catch(() => (store.scaleBar = null));
    }, 120);
    return () => clearTimeout(timer);
  });

  $effect(() => {
    const options = $state.snapshot(store.doc.map.inset);
    const view = store.view;
    if (!options.show || !view) {
      store.inset = null;
      return;
    }
    const points = store.doc.datasets.filter((d) => d.visible).flatMap((d) => lonLats($state.snapshot(d) as typeof d));
    const request = {
      projection: $state.snapshot(store.projection),
      view: $state.snapshot(view),
      pxWidth: Math.round(fig.box.w * options.size),
      pxPerPt: fig.perPt,
      options,
      points,
    };
    const timer = setTimeout(() => {
      api
        .renderInset(request)
        .then((r) => (store.inset = r))
        .catch((e) => store.fail(e));
    }, 150);
    return () => clearTimeout(timer);
  });

  const marks = $derived(buildMarks(store.doc, styles, store.projected, store.filter));
  const insetMarks = $derived(store.inset ? buildInsetMarks(store.doc, styles, store.inset.points) : []);

  // ---- mouse --------------------------------------------------------------
  type Drag =
    | { kind: "pan"; x: number; y: number; vx: number; vy: number }
    | { kind: "box"; x0: number; y0: number; x1: number; y1: number }
    | { kind: "spin"; x: number; y: number; lon0: number; lat0: number }
    | { kind: "label"; key: string; x: number; y: number; ox: number; oy: number }
    | { kind: "anchor"; what: "legend" | "scalebar" | "inset"; x: number; y: number; ax: number; ay: number };
  let drag = $state<Drag | null>(null);
  let cursorBusy = false;

  function local(e: MouseEvent): [number, number] {
    const r = container.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  function inBox([fx, fy]: [number, number]) {
    const b = fig.box;
    return fx >= b.x && fx <= b.x + b.w && fy >= b.y && fy <= b.y + b.h;
  }

  function onDown(e: PointerEvent) {
    if (!store.view) return;
    const p = local(e);
    const target = e.target as Element;
    const dragEl = target.closest("[data-drag]");
    const what = dragEl?.getAttribute("data-drag") as "legend" | "scalebar" | "inset" | undefined;
    if (e.button === 2) {
      if (what) resetAnchor(what);
      const label = target.closest("[data-label]")?.getAttribute("data-label");
      if (label && store.labelOffsets[label]) {
        const { [label]: _gone, ...rest } = store.labelOffsets;
        store.labelOffsets = rest;
      }
      return;
    }
    if (e.button !== 0) return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    if (dragEl && what && draggable(what)) {
      // Anchors are the lower-left corner in axes fractions, as PyMappr keeps them.
      const r = dragEl.getBoundingClientRect();
      const c = container.getBoundingClientRect();
      const b = fig.box;
      const ax = (r.left - c.left - b.x) / b.w;
      const ay = 1 - (r.bottom - c.top - b.y) / b.h;
      drag = { kind: "anchor", what, x: p[0], y: p[1], ax, ay };
      return;
    }
    if (!inBox(p)) return;
    const label = target.closest("[data-label]")?.getAttribute("data-label");
    if (label && store.allowLabelDrag) {
      const [ox, oy] = store.labelOffsets[label] ?? [0, 0];
      drag = { kind: "label", key: label, x: p[0], y: p[1], ox, oy };
    } else if (globe) {
      drag = {
        kind: "spin",
        x: p[0],
        y: p[1],
        lon0: store.projection.lon0 ?? 0,
        lat0: store.projection.lat0 ?? 0,
      };
    } else if (e.shiftKey) {
      drag = { kind: "box", x0: p[0], y0: p[1], x1: p[0], y1: p[1] };
    } else {
      drag = { kind: "pan", x: p[0], y: p[1], vx: store.view.x, vy: store.view.y };
    }
  }

  let spinTimer = 0;
  function onMove(e: PointerEvent) {
    if (!store.view) return;
    const p = local(e);
    const d = drag;
    if (d?.kind === "pan") {
      store.view = { ...store.view, x: d.vx - (p[0] - d.x) * k, y: d.vy - (p[1] - d.y) * k };
    } else if (d?.kind === "box") {
      drag = { ...d, x1: p[0], y1: p[1] };
    } else if (d?.kind === "label") {
      // Labels move at most 1% of the view from their spot, as in PyMappr.
      const lim = 0.01 * store.view.w;
      const clamp = (v: number) => Math.max(-lim, Math.min(lim, v));
      store.labelOffsets = {
        ...store.labelOffsets,
        [d.key]: [clamp(d.ox + (p[0] - d.x) * k), clamp(d.oy + (p[1] - d.y) * k)],
      };
    } else if (d?.kind === "anchor") {
      const ax = d.ax + (p[0] - d.x) / fig.box.w;
      const ay = d.ay - (p[1] - d.y) / fig.box.h;
      setAnchor(d.what, ax, ay);
    } else if (d?.kind === "spin") {
      // About 180° per disk diameter, at most every 50 ms.
      const now = performance.now();
      if (now - spinTimer > 50) {
        spinTimer = now;
        const per = 180 / (Math.min(fig.box.w, fig.box.h) * 0.88);
        const lon = ((((d.lon0 - (p[0] - d.x) * per + 180) % 360) + 360) % 360) - 180;
        const lat = Math.max(-90, Math.min(90, d.lat0 + (p[1] - d.y) * per));
        store.doc.map.proj_lon0 = String(Math.round(lon * 10) / 10);
        store.doc.map.proj_lat0 = String(Math.round(lat * 10) / 10);
      }
    }
    if (!cursorBusy && inBox(p)) {
      cursorBusy = true;
      const [mx, my] = figureToMap(store.view, fig.box, p[0], p[1]);
      api
        .unproject($state.snapshot(store.projection), mx, my)
        .then((ll) => (store.cursor = ll))
        .catch(() => {})
        .finally(() => (cursorBusy = false));
    }
  }

  function onUp() {
    const d = drag;
    drag = null;
    if (!d || !store.view) return;
    if (d.kind === "pan") {
      // Remember the view before the pan for Back.
      store.back = [...store.back.slice(-49), { ...store.view, x: d.vx, y: d.vy }];
      store.forward = [];
    } else if (d.kind === "box") {
      const [ax, ay] = figureToMap(store.view, fig.box, Math.min(d.x0, d.x1), Math.min(d.y0, d.y1));
      const [bx, by] = figureToMap(store.view, fig.box, Math.max(d.x0, d.x1), Math.max(d.y0, d.y1));
      if (bx - ax > 0 && by - ay > 0 && Math.abs(d.x1 - d.x0) > 4) store.setView({ x: ax, y: ay, w: bx - ax, h: by - ay });
    }
  }

  function draggable(what: "legend" | "scalebar" | "inset"): boolean {
    const m = store.doc.map;
    return what === "legend" ? store.doc.legend.draggable : what === "scalebar" ? m.scale_bar.draggable : m.inset.draggable;
  }

  function setAnchor(what: "legend" | "scalebar" | "inset", ax: number, ay: number) {
    const m = store.doc.map;
    if (what === "legend") {
      // The legend may go anywhere, even outside the map.
      store.doc.legend.anchor = [ax, ay];
    } else if (what === "scalebar") {
      m.scale_bar.anchor_x = Math.min(0.99, Math.max(0.01, ax));
      m.scale_bar.anchor_y = Math.min(0.97, Math.max(0.01, ay));
    } else {
      // The inset stays on the map.
      m.inset.anchor_x = Math.min(0.99, Math.max(0, ax));
      m.inset.anchor_y = Math.min(0.99, Math.max(0, ay));
    }
  }

  function resetAnchor(what: "legend" | "scalebar" | "inset") {
    const m = store.doc.map;
    if (what === "legend") store.doc.legend.anchor = null;
    else if (what === "scalebar") Object.assign(m.scale_bar, { anchor_x: null, anchor_y: null });
    else Object.assign(m.inset, { anchor_x: null, anchor_y: null });
  }

  function onWheel(e: WheelEvent) {
    if (!store.view) return;
    e.preventDefault();
    const p = local(e);
    const factor = e.deltaY < 0 ? 1.25 : 1 / 1.25;
    // The globe zooms about its centre.
    store.zoomBy(factor, globe ? undefined : figureToMap(store.view, fig.box, p[0], p[1]));
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  bind:this={container}
  class="relative h-full w-full overflow-hidden"
  class:cursor-grab={!drag && !globe}
  class:cursor-grabbing={drag?.kind === "pan" || drag?.kind === "spin"}
  class:cursor-crosshair={drag?.kind === "box"}
  onpointerdown={onDown}
  onpointermove={onMove}
  onpointerup={onUp}
  onpointerleave={() => (store.cursor = null)}
  onwheel={onWheel}
  oncontextmenu={(e) => e.preventDefault()}
>
  {#if store.view && store.map}
    <Scene
      bind:svgEl={store.svgEl}
      showLegend={store.doc.legend.show}
      {fig}
      view={store.view}
      map={store.map}
      settings={store.doc.map}
      {globe}
      {marks}
      edge={store.doc.point_edge}
      alpha={store.doc.point_alpha}
      {showTicks}
      labelOffsets={store.labelOffsets}
      scaleBar={store.scaleBar}
      inset={store.inset}
      {insetMarks}
    />
  {/if}
  {#if drag?.kind === "box"}
    <div
      class="pointer-events-none absolute border border-dashed border-ink bg-accent/10"
      style:left="{Math.min(drag.x0, drag.x1)}px"
      style:top="{Math.min(drag.y0, drag.y1)}px"
      style:width="{Math.abs(drag.x1 - drag.x0)}px"
      style:height="{Math.abs(drag.y1 - drag.y0)}px"
    ></div>
  {/if}
</div>
