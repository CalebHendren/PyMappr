<script lang="ts">
  // Save map as…: PyMappr's formats, DPI and print widths, with a live size
  // read-out. The chosen DPI and width are kept in the project.
  import { api, saveFile } from "$lib/api";
  import { exportFigure, exportSvg, FORMATS, VECTOR, type Format } from "$lib/exporting.svelte";
  import { printPixels } from "$lib/layout";
  import type { Symbology } from "$lib/symbology";
  import { store } from "$lib/store.svelte";
  import Modal from "./Modal.svelte";

  let { onClose, sym }: { onClose: () => void; sym: Symbology } = $props();

  const AS_ON_SCREEN = "As on screen";
  const WIDTHS: [string, string][] = [
    [AS_ON_SCREEN, "As on screen"],
    ["17 cm (Zootaxa / Phytotaxa page)", "17 cm (Zootaxa / Phytotaxa page)"],
    ["8 cm (one column)", "8 cm (one column)"],
  ];
  const DPIS = ["100", "150", "200", "300", "600"];

  let format = $state<Format>("png");
  let saving = $state(false);
  let error = $state<string | null>(null);

  const m = $derived(store.doc.map);
  const preset = $derived(WIDTHS.some(([v]) => v === m.export_width));
  let customCm = $state("");

  /** The print width in cm, from the stored setting ("17 cm (…)", "12,5"). */
  const widthCm = $derived.by(() => {
    if (m.export_width === AS_ON_SCREEN) return null;
    const n = parseFloat(m.export_width.replace(",", "."));
    return Number.isFinite(n) && n >= 1 && n <= 100 ? n : null;
  });
  const dpi = $derived(Math.max(1, Math.round(Number(m.dpi) || 200)));
  const fig = $derived(exportFigure(widthCm));
  const px = $derived(fig ? printPixels(fig, dpi) : null);
  const cm = $derived(fig ? { w: (fig.w / 72) * 2.54, h: (fig.h / 72) * 2.54 } : null);

  async function run() {
    const ext = format === "jpeg" ? "jpg" : format === "tiff" ? "tif" : format;
    const path = await saveFile("Save map as", `map.${ext}`, [{ name: format.toUpperCase(), extensions: [ext] }]);
    if (!path) return;
    saving = true;
    error = null;
    try {
      const { svg, px } = await exportSvg(widthCm, dpi, sym);
      await api.exportMap(svg, format, px.w, dpi, path);
      store.setStatus(`Saved ${path}`);
      onClose();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }
</script>

<Modal title="Save map as" {onClose}>
  <div class="max-w-lg space-y-3">
    <label class="row">
      <span class="label">Format</span>
      <select class="field" bind:value={format}>
        {#each FORMATS as [v, label] (v)}<option value={v}>{label}</option>{/each}
      </select>
    </label>
    <label class="row">
      <span class="label">Print width</span>
      <select class="field" value={preset ? m.export_width : "custom"}
        onchange={(e) => (m.export_width = e.currentTarget.value === "custom" ? customCm || "12" : e.currentTarget.value)}>
        {#each WIDTHS as [v, label] (v)}<option value={v}>{label}</option>{/each}
        <option value="custom">Custom width (cm)</option>
      </select>
    </label>
    {#if !preset}
      <label class="row">
        <span class="label">Width in cm</span>
        <input class="field" value={m.export_width} oninput={(e) => {
          customCm = e.currentTarget.value;
          m.export_width = e.currentTarget.value;
        }} />
      </label>
    {/if}
    <label class="row">
      <span class="label">Resolution (DPI)</span>
      <input class="field" list="dpi-choices" bind:value={m.dpi} disabled={VECTOR.includes(format)} />
      <datalist id="dpi-choices">{#each DPIS as d (d)}<option value={d}></option>{/each}</datalist>
    </label>
    {#if cm}
      <p class="text-muted tabular-nums">
        {#if VECTOR.includes(format)}
          Vector, {cm.w.toFixed(1)} × {cm.h.toFixed(1)} cm.
        {:else if px}
          {px.w} × {px.h} px ({cm.w.toFixed(1)} × {cm.h.toFixed(1)} cm at {dpi} DPI).
        {/if}
        Text and symbols print at their point sizes; the map fills the width.
      </p>
    {/if}
    {#if widthCm === null && m.export_width !== AS_ON_SCREEN}<p class="text-danger">Type a width between 1 and 100 cm.</p>{/if}
    {#if error}<p class="text-danger">{error}</p>{/if}
  </div>

  {#snippet actions()}
    <button class="btn" onclick={onClose}>Cancel</button>
    <button class="btn-primary" onclick={run} disabled={saving || !fig}>{saving ? "Saving…" : "Save map"}</button>
  {/snippet}
</Modal>
