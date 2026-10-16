<script lang="ts">
  // "Manual coordinate entry": type or paste points with a legend name and a
  // symbol (PyMappr's ui/manual_entry.py). The same dialog edits a manual
  // dataset. Lines are parsed by the backend's coordinate parser.
  import { untrack } from "svelte";
  import { docs, type ManualParse } from "$lib/api-docs";
  import { toHex } from "$lib/colors";
  import { type ManualOrder, type ManualResult, skippedReport } from "$lib/datasets";
  import { MARKER_NAMES } from "$lib/markers";
  import { type PointStyle, pointStyle } from "$lib/symbology";
  import MarkerSwatch from "../legend/MarkerSwatch.svelte";
  import DialogFrame from "./DialogFrame.svelte";

  let {
    legend = "",
    text = "",
    order = "lat,lon",
    style = pointStyle(),
    parse = docs.parseManual,
    onaccept,
    onClose,
  }: {
    legend?: string;
    text?: string;
    order?: ManualOrder;
    /** The set's symbol; manualStyle(entry) when editing. */
    style?: PointStyle;
    /** The parser; the backend's parse_manual by default. */
    parse?: (legend: string, text: string, order: ManualOrder) => Promise<ManualParse>;
    /** OK with at least one point read. Build the dataset with manualEntry /
     * editManualEntry; `parsed.skipped` lists lines that were not read
     * (skippedReport words the warning). */
    onaccept: (result: ManualResult, parsed: ManualParse) => void;
    onClose: () => void;
  } = $props();

  const ORDERS: [ManualOrder, string][] = [
    ["lat,lon", "Latitude, Longitude"],
    ["lon,lat", "Longitude, Latitude"],
  ];
  const SIZE_CHOICES = ["10", "20", "30", "45", "60", "90", "120"];

  let name = $state(untrack(() => legend));
  let lines = $state(untrack(() => text));
  let coordOrder = $state<ManualOrder>(untrack(() => order));
  let marker = $state(untrack(() => style.marker));
  let size = $state(untrack(() => String(style.size)));
  let color = $state(untrack(() => toHex(style.color)));
  let error = $state("");
  let busy = $state(false);
  let nameField: HTMLInputElement;

  $effect(() => {
    nameField.focus();
  });

  async function accept() {
    const legendName = name.trim();
    if (!legendName) {
      error = "Give the point set a legend name.";
      return;
    }
    const body = lines.trim();
    if (!body) {
      error = "Enter at least one coordinate line.";
      return;
    }
    let chosen = Number(size);
    chosen = size.trim() === "" || Number.isNaN(chosen) ? 30 : Math.max(Math.min(chosen, 1000), 1);
    busy = true;
    try {
      const parsed = await parse(legendName, body, coordOrder);
      const problem = skippedReport(parsed.rows.length, parsed.skipped);
      if (problem?.kind === "error") {
        error = problem.message;
        return;
      }
      onaccept({ legend: legendName, text: body, order: coordOrder, style: pointStyle({ color, marker, size: chosen }) }, parsed);
    } catch (e) {
      error = String(e instanceof Error ? e.message : e);
    } finally {
      busy = false;
    }
  }
</script>

<DialogFrame title="Manual coordinate entry" {onClose}>
  <div class="space-y-3">
    <label class="flex items-center gap-2">
      <span class="label w-32 shrink-0">Legend name</span>
      <input class="field" bind:this={nameField} bind:value={name} />
    </label>
    <label class="flex items-center gap-2">
      <span class="label w-32 shrink-0">Coordinate order</span>
      <select class="field max-w-56" bind:value={coordOrder}>
        {#each ORDERS as [value, label] (value)}
          <option {value}>{label}</option>
        {/each}
      </select>
    </label>
    <div>
      <p class="text-[12px] text-muted">
        One point per line, e.g. 38, -100 (optionally add a label: 38, -100, Site A). Decimal degrees or DMS.
      </p>
      <textarea class="field mt-1 h-48 resize-y font-mono" spellcheck="false" bind:value={lines}></textarea>
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <label class="flex items-center gap-1.5">
        <span class="label">Shape</span>
        <MarkerSwatch {marker} {color} size={16} />
        <select class="field w-40" bind:value={marker}>
          {#each MARKER_NAMES as m (m)}
            <option value={m}>{m}</option>
          {/each}
        </select>
      </label>
      <label class="flex items-center gap-1.5">
        <span class="label">Size</span>
        <input class="field w-20" list="manual-entry-sizes" bind:value={size} />
        <datalist id="manual-entry-sizes">
          {#each SIZE_CHOICES as s (s)}<option value={s}></option>{/each}
        </datalist>
      </label>
      <label class="flex items-center gap-1.5">
        <span class="label">Color</span>
        <input type="color" class="h-7 w-10 cursor-pointer rounded border border-line bg-raised p-0.5" bind:value={color} />
      </label>
    </div>
    {#if error}
      <p class="whitespace-pre-line text-[13px] text-danger" role="alert">{error}</p>
    {/if}
  </div>
  {#snippet actions()}
    <button class="btn border border-line" onclick={() => (lines = "")}>Clear</button>
    <span class="flex-1"></span>
    <button class="btn border border-line" onclick={onClose}>Cancel</button>
    <button class="btn-primary" disabled={busy} onclick={accept}>OK</button>
  {/snippet}
</DialogFrame>
