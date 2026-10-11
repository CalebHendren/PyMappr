<script lang="ts">
  // Save the map as it is on screen: SVG as is, or PNG at a print width.
  import { save } from "@tauri-apps/plugin-dialog";
  import { api } from "$lib/api";
  import { app } from "$lib/state.svelte";
  import Modal from "./Modal.svelte";

  let { onClose }: { onClose: () => void } = $props();

  let format = $state<"png" | "svg">("png");
  let saving = $state(false);
  let error = $state<string | null>(null);

  const widths: [number | null, string][] = [
    [null, "As on screen"],
    [17, "17 cm (Zootaxa/Phytotaxa page)"],
    [8, "8 cm (one column)"],
  ];
  const dpis = [150, 300, 600];

  const aspect = $derived(app.size.h / app.size.w);
  // "As on screen" keeps the on-screen size, taken as 96 px per inch.
  const widthCm = $derived(app.exportWidthCm ?? (app.size.w / 96) * 2.54);
  const widthPx = $derived(Math.max(1, Math.round((widthCm / 2.54) * app.exportDpi)));

  function serialise(): string {
    const svg = app.svgEl!.cloneNode(true) as SVGSVGElement;
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svg.removeAttribute("class");
    if (format === "svg") {
      svg.setAttribute("width", `${widthCm.toFixed(2)}cm`);
      svg.setAttribute("height", `${(widthCm * aspect).toFixed(2)}cm`);
    }
    return new XMLSerializer().serializeToString(svg);
  }

  async function run() {
    const path = await save({
      defaultPath: `map.${format}`,
      filters: [{ name: format.toUpperCase(), extensions: [format] }],
    });
    if (!path) return;
    saving = true;
    error = null;
    try {
      await api.exportMap(serialise(), format, widthPx, app.exportDpi, path);
      app.notice = `Saved ${path}`;
      onClose();
    } catch (e) {
      error = String(e);
    } finally {
      saving = false;
    }
  }
</script>

<Modal title="Save map" {onClose}>
  <div class="max-w-md space-y-4">
    <div>
      <span class="label">Format</span>
      <div class="mt-1 flex gap-1" role="radiogroup" aria-label="Format">
        {#each [["png", "PNG image"], ["svg", "SVG (editable vector)"]] as [value, label] (value)}
          <button
            class="btn border border-line"
            class:!bg-accent-soft={format === value}
            role="radio"
            aria-checked={format === value}
            onclick={() => (format = value as "png" | "svg")}>{label}</button
          >
        {/each}
      </div>
    </div>

    <label class="block">
      <span class="label">Print width</span>
      <select
        class="field mt-1"
        value={String(app.exportWidthCm)}
        onchange={(e) => (app.exportWidthCm = e.currentTarget.value === "null" ? null : Number(e.currentTarget.value))}
      >
        {#each widths as [cm, label] (label)}<option value={String(cm)}>{label}</option>{/each}
      </select>
    </label>

    {#if format === "png"}
      <div>
        <span class="label">Resolution</span>
        <div class="mt-1 flex gap-1" role="radiogroup" aria-label="Resolution">
          {#each dpis as dpi (dpi)}
            <button
              class="btn border border-line"
              class:!bg-accent-soft={app.exportDpi === dpi}
              role="radio"
              aria-checked={app.exportDpi === dpi}
              onclick={() => (app.exportDpi = dpi)}>{dpi} DPI</button
            >
          {/each}
        </div>
      </div>
    {/if}

    <p class="text-muted tabular-nums">
      {widthCm.toFixed(1)} × {(widthCm * aspect).toFixed(1)} cm{#if format === "png"}, {widthPx} × {Math.round(widthPx * aspect)} pixels{/if}.
      The saved map shows what is in view now, legend included.
    </p>
    {#if error}<p class="text-danger">{error}</p>{/if}
  </div>

  {#snippet actions()}
    <button class="btn" onclick={onClose}>Cancel</button>
    <button class="btn-primary" onclick={run} disabled={saving}>{saving ? "Saving…" : "Save map"}</button>
  {/snippet}
</Modal>
