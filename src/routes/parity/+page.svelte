<script lang="ts">
  // Dev only: render a project the way the parity check needs it, on PyMappr's
  // 900 x 650 px screen figure with the project's own view limits, measure every
  // text, marker and legend frame, and write it all through the dev bridge.
  // Used by scripts/parity.py; see scripts/parity_compare.py.
  //   /parity?project=<path to .pymappr>&out=<folder>
  import { flushSync, mount, unmount } from "svelte";
  import { api, call } from "$lib/api";
  import { docs } from "$lib/api-docs";
  import Scene from "$lib/components/map/Scene.svelte";
  import { hasTicks, screenFigure, viewFromLimits } from "$lib/layout";
  import { withDefaults } from "$lib/model";
  import { insetMarks, marks } from "$lib/points";
  import { parseProject } from "$lib/project";
  import { layerSettings, lonLats, projectionSpec } from "$lib/store.svelte";
  import { symbology } from "$lib/symbology";

  const W = 900;
  const H = 650;

  let host: HTMLDivElement;
  let status = $state("Rendering…");

  async function loadFonts() {
    const faces = ["DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono"].flatMap((f) =>
      ["", "bold ", "italic ", "italic bold "].map((s) => document.fonts.load(`${s}10px "${f}"`)),
    );
    await Promise.allSettled(faces);
  }

  function geometry(svg: SVGSVGElement, fig: ReturnType<typeof screenFigure>, view: { x: number; y: number; w: number; h: number }, insetRect: number[] | null, insetLimits: number[][] | null) {
    const root = svg.getScreenCTM()!.inverse();
    const toFig = (el: SVGGraphicsElement, x: number, y: number) => {
      const m = root.multiply(el.getScreenCTM()!);
      return [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f];
    };
    const b = fig.box;
    const axes = [{ box: [b.x, b.y, b.x + b.w, b.y + b.h], xlim: [view.x, view.x + view.w], ylim: [-(view.y + view.h), -view.y] }];
    if (insetRect && insetLimits) axes.push({ box: insetRect, xlim: insetLimits[0], ylim: insetLimits[1] });
    const texts = [...svg.querySelectorAll("text")].filter((t) => t.textContent?.trim()).map((t) => {
      const cs = getComputedStyle(t);
      const anchor = t.getAttribute("data-anchor");
      const [x, y] = anchor ? anchor.split(",").map(Number) : toFig(t, Number(t.getAttribute("x")), Number(t.getAttribute("y")));
      const m = root.multiply(t.getScreenCTM()!);
      const sizePx = parseFloat(cs.fontSize) * Math.hypot(m.a, m.b);
      return {
        text: t.textContent,
        x,
        y,
        size: Math.round((sizePx / fig.perPt) * 1000) / 1000,
        color: hex(cs.fill),
        weight: cs.fontWeight === "700" || cs.fontWeight === "bold" ? "bold" : "normal",
        style: cs.fontStyle === "italic" ? "italic" : "normal",
      };
    });
    const markers = [...svg.querySelectorAll("[data-mark]")].map((el) => {
      const [x, y, size, face, edge] = el.getAttribute("data-mark")!.split(",");
      return { x: Number(x), y: Number(y), size: Number(size), face: hex(face), edge: hex(edge) };
    });
    const patches = [...svg.querySelectorAll(".legend > path")].slice(0, 1).map((p) => {
      const bb = (p as SVGGraphicsElement).getBBox();
      const [x0, y0] = toFig(p as SVGGraphicsElement, bb.x, bb.y);
      const [x1, y1] = toFig(p as SVGGraphicsElement, bb.x + bb.width, bb.y + bb.height);
      return { kind: "LegendFrame", box: [x0, y0, x1, y1] };
    });
    return { size: [W, H], axes, texts, markers, patches };
  }

  function hex(color: string | null): string | null {
    if (!color || color === "none") return null;
    const m = color.match(/rgba?\((\d+), (\d+), (\d+)/);
    if (!m) return color.toLowerCase();
    return "#" + m.slice(1, 4).map((v) => Number(v).toString(16).padStart(2, "0")).join("");
  }

  $effect(() => {
    run().catch((e) => (status = `Failed: ${e instanceof Error ? e.message : e}`));
  });

  async function run() {
    if (!import.meta.env.DEV) throw new Error("The parity page only runs in development.");
    const params = new URLSearchParams(location.search);
    const projectPath = params.get("project");
    const out = params.get("out");
    if (!projectPath || !out) throw new Error("Pass ?project=…&out=…");
    await loadFonts();
    const { state } = parseProject(await docs.readProject(projectPath), projectPath);
    const doc = withDefaults(state);
    const projection = projectionSpec(doc);
    const globe = doc.map.projection.startsWith("Globe");
    const ticks = hasTicks(doc.map.graticule, doc.map.hide_grid_labels, globe);
    const fig = screenFigure(W, H, ticks, doc.map.orientation === "Portrait");
    // PyMappr's own limits, as they fill its axes (units need not be square).
    const view = viewFromLimits(doc.view.xlim, doc.view.ylim);
    const map = await api.renderMap({
      projection,
      view,
      pxWidth: fig.box.w,
      pxHeight: fig.box.h,
      pxPerPt: fig.perPt,
      detailBoost: 0,
      layers: layerSettings(doc),
      districts: [],
    });
    const projected = await Promise.all(doc.datasets.map((d) => api.projectPoints(projection, lonLats(d)).then((xy) => ({ xy }))));
    const scaleBar = doc.map.scale_bar.show
      ? await api.scaleBar({ projection, view, boxPt: { w: fig.box.w / fig.perPt, h: fig.box.h / fig.perPt }, options: doc.map.scale_bar })
      : null;
    const points = doc.datasets.filter((d) => d.visible).flatMap(lonLats);
    const inset = doc.map.inset.show
      ? await api.renderInset({ projection, view, pxWidth: fig.box.w, pxHeight: fig.box.h, pxPerPt: fig.perPt, options: doc.map.inset, scaleBar: doc.map.scale_bar, points })
      : null;
    const sym = symbology(doc, null);
    const scene = mount(Scene, {
      target: host,
      props: {
        fig,
        view,
        map,
        settings: doc.map,
        globe,
        marks: marks(doc, sym.points, projected),
        alpha: doc.point_alpha,
        showTicks: ticks,
        scaleBar,
        inset,
        insetMarks: inset ? insetMarks(doc, sym.points, inset.points) : [],
        legend: sym.legend,
        legendOptions: sym.options,
        pointEdge: doc.point_edge,
      },
    });
    flushSync();
    const svg = host.querySelector("svg") as SVGSVGElement;
    const b = fig.box;
    const insetRect = inset
      ? [b.x + inset.rect.x * b.w, b.y + (1 - inset.rect.y - inset.rect.h) * b.h, b.x + (inset.rect.x + inset.rect.w) * b.w, b.y + (1 - inset.rect.y) * b.h]
      : null;
    const insetLimits = inset ? [[inset.view.x, inset.view.x + inset.view.w], [-(inset.view.y + inset.view.h), -inset.view.y]] : null;
    const geo = geometry(svg, fig, view, insetRect, insetLimits);
    const text = svg.outerHTML;
    unmount(scene);
    const written = await call<string>("parity_write", { dir: out, svg: text, geometry: { ...geo, project: projectPath }, widthPx: W });
    status = `Done: ${written}`;
  }
</script>

<p class="p-2 text-[12px]" data-parity-status>{status}</p>
<div bind:this={host} style="width: 900px; height: 650px"></div>
