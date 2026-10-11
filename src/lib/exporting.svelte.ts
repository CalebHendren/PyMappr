// Building an export: the figure at print size, the base map re-drawn at
// the export's pixel detail, and the same Scene component the screen uses
// mounted offscreen and serialised.
import { flushSync, mount, unmount } from "svelte";
import { api } from "./api";
import Scene from "./components/map/Scene.svelte";
import { hasTicks, printFigure, printPixels, type Figure } from "./layout";
import { insetMarks, marks as buildMarks, type PointStyle } from "./points";
import { layerSettings, store } from "./store.svelte";

export const FORMATS = [
  ["png", "PNG"],
  ["jpeg", "JPEG"],
  ["tiff", "TIFF (LZW; greyscale when the map has no colour)"],
  ["pdf", "PDF (vector, editable text)"],
  ["svg", "SVG (vector, editable text)"],
  ["webp", "WebP"],
] as const;
export type Format = (typeof FORMATS)[number][0];
export const VECTOR: Format[] = ["pdf", "svg"];

/** The printed figure for a print width (null = as on screen). */
export function exportFigure(widthCm: number | null): Figure | null {
  return store.screenFig ? printFigure(store.screenFig, widthCm) : null;
}

/** Render the current map at print size and return its SVG text. */
export async function exportSvg(widthCm: number | null, dpi: number, styles: (PointStyle | null)[][]): Promise<{ svg: string; px: { w: number; h: number } }> {
  const screen = store.screenFig;
  const view = store.view;
  if (!screen || !view || !store.map) throw new Error("There is no map to save yet.");
  const fig = printFigure(screen, widthCm);
  const px = printPixels(fig, dpi);
  const boxPx = (fig.box.w / 72) * dpi;
  // More data detail for a bigger export, as PyMappr's detail boost.
  const boost = Math.log2(boxPx / screen.box.w);
  const map = await api.renderMap({
    projection: $state.snapshot(store.projection),
    view: $state.snapshot(view),
    pxWidth: Math.round(boxPx),
    pxPerPt: dpi / 72,
    detailBoost: boost >= 0.5 ? boost : 0,
    layers: $state.snapshot(layerSettings(store.doc)),
    districts: $state.snapshot(store.districts),
  });
  const globe = store.doc.map.projection.startsWith("Globe");
  const target = document.createElement("div");
  const scene = mount(Scene, {
    target,
    props: {
      fig,
      view: $state.snapshot(view),
      map,
      settings: $state.snapshot(store.doc.map),
      globe,
      marks: buildMarks(store.doc, styles, store.projected, store.filter),
      edge: $state.snapshot(store.doc.point_edge),
      alpha: store.doc.point_alpha,
      showTicks: hasTicks(store.doc.map.graticule, store.doc.map.hide_grid_labels, globe),
      labelOffsets: $state.snapshot(store.labelOffsets),
      scaleBar: $state.snapshot(store.scaleBar),
      inset: $state.snapshot(store.inset),
      insetMarks: store.inset ? insetMarks(store.doc, styles, store.inset.points) : [],
      showLegend: store.doc.legend.show,
      sizeUnit: "pt",
    },
  });
  flushSync();
  const svg = target.querySelector("svg")!.outerHTML;
  unmount(scene);
  return { svg, px };
}
