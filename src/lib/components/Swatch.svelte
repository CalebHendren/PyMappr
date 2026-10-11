<script lang="ts">
  // A marker sample for lists in the panel.
  import { markerPath, isOpenMarker } from "$lib/marker-paths";

  let {
    marker,
    color,
    outline = "#666666",
    size = 14,
    open = false,
  }: { marker: string; color: string; outline?: string; size?: number; open?: boolean } = $props();

  const hollow = $derived(open || isOpenMarker(marker));
</script>

<svg width={size} height={size} viewBox="-1.5 -1.5 3 3" aria-hidden="true">
  <path
    d={markerPath(marker)}
    fill={hollow ? "#ffffff" : color}
    stroke={hollow ? color : outline}
    stroke-width={hollow ? 0.3 : 0.15}
    stroke-linejoin="round"
  />
</svg>
