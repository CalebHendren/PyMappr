// Map text measured, placed and outlined the way matplotlib's Agg renderer
// does it, so every label sits where PyMappr puts it. The backend does the
// font work (mappr_core::text: hinted DejaVu at FreeType's rounded ppem,
// shaped like libraqm); this caches its answers, reactively, and turns them
// into matplotlib's Text layout.
import { SvelteMap } from "svelte/reactivity";
import { call } from "./api";

/** "agg": Agg's own hinted text. "path": TextToPath's unhinted outlines,
 * which matplotlib draws for text with a path effect (the white halo). */
export type TextMode = "agg" | "path";

export type TextFont = {
  /** Points. */
  size: number;
  bold: boolean;
  italic: boolean;
  /** "", "sans-serif", "serif" or "monospace" (DejaVu Sans, Serif, Sans Mono). */
  family: string;
};

/** A string's matplotlib metrics in pixels at the dpi it was asked for, and
 * its glyph outlines (SVG path data, y down, origin at the baseline start). */
export type TextShape = { w: number; h: number; d: number; path: string };

const FAMILIES: Record<string, number> = { "": 0, "sans-serif": 0, serif: 1, monospace: 2 };

/** DejaVu's OS/2 typo ascender and descender per em (all twelve faces),
 * which matplotlib lays single lines out with. */
export const TYPO_ASCENT = 1556 / 2048;
export const TYPO_DESCENT = 492 / 2048;

type Request = { text: string; family: number; bold: boolean; italic: boolean; size: number; dpi: number; mode: TextMode };

const cache = new SvelteMap<string, TextShape>();
const pending = new Map<string, Request>();
let inflight: Promise<void> | null = null;
let scheduled = false;
let failed: unknown = null;

function keyOf(r: Request): string {
  return `${r.mode}|${r.dpi}|${r.size}|${r.family}|${+r.bold}${+r.italic}|${r.text}`;
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  queueMicrotask(() => {
    scheduled = false;
    void flush();
  });
}

async function flush(): Promise<void> {
  if (inflight) {
    await inflight;
    if (pending.size) await flush();
    return;
  }
  if (!pending.size) return;
  const batch = [...pending.entries()];
  pending.clear();
  inflight = (async () => {
    try {
      const shapes = await call<TextShape[]>("text_shapes", { items: batch.map(([, r]) => r) });
      batch.forEach(([key], i) => cache.set(key, shapes[i]));
    } catch (e) {
      failed = e;
    } finally {
      inflight = null;
    }
  })();
  await inflight;
  if (pending.size) await flush();
}

/** The shape of `text`, or undefined until the backend has answered (the
 * caller re-runs then, as the cache is reactive). */
export function textShape(text: string, font: TextFont, dpi: number, mode: TextMode = "agg"): TextShape | undefined {
  const r: Request = { text, family: FAMILIES[font.family] ?? 0, bold: font.bold, italic: font.italic, size: font.size, dpi, mode };
  const key = keyOf(r);
  const hit = cache.get(key);
  if (hit) return hit;
  if (!pending.has(key)) {
    pending.set(key, r);
    schedule();
  }
  return undefined;
}

/** Resolves once every shape asked for so far has arrived. */
export async function textSettled(): Promise<void> {
  await new Promise<void>((ok) => queueMicrotask(ok));
  await flush();
  if (failed) {
    const e = failed;
    failed = null;
    throw e;
  }
}

/** Whether shapes are still on their way. */
export function textPending(): boolean {
  return pending.size > 0 || inflight !== null;
}

export type HAlign = "left" | "center" | "right";
export type VAlign = "top" | "bottom" | "center" | "baseline" | "center_baseline";

/** matplotlib's single-line Text layout (text.py `_get_layout`): where the
 * baseline starts relative to the anchor, and the text's box, in pixels
 * with y down. The line's ascent and descent are the measured ones or the
 * font's typo metrics at the dpi (unrounded), whichever is larger. */
export function placeText(shape: TextShape, sizePt: number, dpi: number, ha: HAlign, va: VAlign) {
  const em = (sizePt * dpi) / 72;
  const a = Math.max(shape.h - shape.d, TYPO_ASCENT * em);
  const d = Math.max(shape.d, TYPO_DESCENT * em);
  const w = shape.w;
  const dx = ha === "left" ? 0 : ha === "right" ? -w : -w / 2;
  // Baseline above the anchor (y up), per vertical alignment.
  const up = va === "bottom" ? d : va === "top" ? -a : va === "center" ? (d - a) / 2 : va === "baseline" ? 0 : -a / 2;
  const dy = -up;
  return { dx, dy, ascent: a, descent: d, box: { x: dx, y: dy - a, w, h: a + d } };
}

/** Python's round(): halves go to the even neighbour. */
export function roundHalfEven(v: number): number {
  const r = Math.round(v);
  return Math.abs(v - Math.trunc(v)) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

/** Where Agg puts a glyph run whose baseline starts at (x, y) canvas pixels
 * (y down) on a canvas `height` pixels tall: FreeType's pen is the
 * position rounded to 1/64 pixel, measured from the bottom. */
export function aggOrigin(x: number, y: number, height: number): [number, number] {
  return [roundHalfEven(64 * x) / 64, height - roundHalfEven(64 * (height - y)) / 64];
}

/** Agg's snapping of a straight-edged (horizontal and vertical only) path:
 * each vertex, in canvas pixels with y down, goes to the nearest pixel
 * corner, plus half a pixel when the stroke, rounded to whole pixels, is
 * odd, so a one-pixel line covers exactly one row (PathSnapper in
 * matplotlib's path_converters.h). */
export function snapPx(v: number, strokePx: number): number {
  return Math.floor(v + 0.5) + (Math.floor(strokePx + 0.5) % 2 ? 0.5 : 0);
}

/** Where Agg stamps a marker centred at (x, y) canvas pixels: the nearest
 * pixel corner (draw_markers renders the marker once and blits it). */
export function markerPx(x: number, y: number): [number, number] {
  return [Math.floor(x + 0.5), Math.floor(y + 0.5)];
}

type Box = { x: number; y: number; w: number; h: number };

/** Data attributes describing a drawn text (figure units), which the
 * parity check reads back; drawn glyphs are paths, not <text>. */
export function textData(text: string, x: number, y: number, font: TextFont, color: string, box?: Box) {
  return {
    "data-text": text,
    "data-anchor": `${x},${y}`,
    "data-size": font.size,
    "data-weight": font.bold ? "bold" : "normal",
    "data-style": font.italic ? "italic" : "normal",
    "data-color": color,
    "data-box": box ? `${box.x},${box.y},${box.w},${box.h}` : undefined,
  };
}
