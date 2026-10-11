<script lang="ts">
  // The map legend, drawn inside the map's SVG in screen pixels so exports
  // carry it. Arial keeps the screen and the rasterised export alike.
  import { app } from "$lib/state.svelte";
  import { SHAPES } from "$lib/styles";

  const FONT = "Arial, Helvetica, sans-serif";
  const SIZE = 12;
  const ROW = 18;
  const PAD = 9;
  const MARGIN = 14;

  let canvas: HTMLCanvasElement | undefined;
  function textWidth(text: string, italic: boolean, bold = false): number {
    canvas ??= document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    ctx.font = `${italic ? "italic " : ""}${bold ? "bold " : ""}${SIZE}px ${FONT}`;
    return ctx.measureText(text).width;
  }

  const entries = $derived(
    app.groups
      .filter((g) => g.visible)
      .map((g) => ({ ...g, text: app.legend.counts ? `${g.label} (${g.count})` : g.label })),
  );
  const title = $derived(app.legend.title.trim());
  const swatch = $derived(Math.max(app.pointSize, 8));

  const box = $derived.by(() => {
    const labelW = Math.max(0, ...entries.map((e) => textWidth(e.text, app.legend.italic)));
    const titleW = title ? textWidth(title, false, true) : 0;
    const w = Math.ceil(Math.max(swatch + 8 + labelW, titleW) + PAD * 2);
    const h = Math.ceil(entries.length * ROW + (title ? ROW + 2 : 0) + PAD * 2 - (ROW - SIZE) / 2);
    const right = app.legend.corner.endsWith("right");
    const bottom = app.legend.corner.startsWith("lower");
    return {
      x: right ? app.size.w - w - MARGIN : MARGIN,
      y: bottom ? app.size.h - h - MARGIN : MARGIN,
      w,
      h,
    };
  });
</script>

<g transform="translate({box.x} {box.y})" font-family={FONT} font-size={SIZE}>
  {#if app.legend.framed}
    <rect width={box.w} height={box.h} fill="#ffffff" stroke="#000000" stroke-width="0.6" />
  {/if}
  {#if title}
    <text x={PAD} y={PAD + SIZE - 1} font-weight="bold" fill="#000000">{title}</text>
  {/if}
  {#each entries as e, i (e.id)}
    {@const cy = PAD + (title ? ROW + 2 : 0) + i * ROW + SIZE / 2}
    {@const shape = SHAPES[e.shape] ?? SHAPES.circle}
    {@const r = swatch / 2}
    <use
      href="#m-{e.shape}"
      transform="translate({PAD + r} {cy}) scale({r})"
      fill={shape.line ? "none" : e.color}
      stroke={shape.line ? e.color : app.outlineColor === "#ffffff" ? "#666666" : app.outlineColor}
      stroke-width={(shape.line ? 1.6 : Math.max(app.outlineWidth, 0.5) * 1.25) / r}
    />
    <text x={PAD + swatch + 8} y={cy + SIZE * 0.36} fill="#000000" font-style={app.legend.italic ? "italic" : "normal"}
      >{e.text}</text
    >
  {/each}
</g>
