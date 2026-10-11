<script lang="ts">
  // One marker drawn as PyMappr draws it, for lists and pickers.
  import { markerPathAt, markerShape } from "$lib/markers";
  import { markerPaint, pointStyle } from "$lib/symbology";

  let {
    marker,
    color,
    fill = null,
    edge = { color: "#666666", width: 0.8 },
    size = 14,
  }: {
    /** A PyMappr marker name ("Circle", "Star (open)", …). */
    marker: string;
    color: string;
    /** The inside of an open marker; see-through when null. */
    fill?: string | null;
    /** Outline of filled markers, in px at this size. */
    edge?: { color: string; width: number };
    /** Box size in px. */
    size?: number;
  } = $props();

  const paint = $derived(markerPaint(pointStyle({ marker, color, fill }), edge));
  // The marker fills about three quarters of the box.
  const d = $derived(markerPathAt(marker, size * 0.72, size / 2, size / 2));
</script>

<svg width={size} height={size} viewBox="0 0 {size} {size}" aria-hidden="true">
  <path
    {d}
    fill={paint.face}
    stroke={paint.edgeWidth > 0 ? paint.edge : "none"}
    stroke-width={paint.edgeWidth}
    stroke-linejoin={markerShape(marker).join}
  />
</svg>
