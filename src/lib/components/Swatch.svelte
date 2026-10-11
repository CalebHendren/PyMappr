<script lang="ts">
  import { SHAPES } from "$lib/styles";
  let { shape, color, outline = "#666666", size = 14 }: { shape: string; color: string; outline?: string; size?: number } =
    $props();
  const s = $derived(SHAPES[shape] ?? SHAPES.circle);
</script>

<svg width={size} height={size} viewBox="-1.3 -1.3 2.6 2.6" aria-hidden="true">
  <path
    d={s.d}
    fill={s.line ? "none" : color}
    stroke={s.line ? color : outline}
    stroke-width={s.line ? 0.32 : 0.16}
    stroke-linecap="round"
  />
</svg>
