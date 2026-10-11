<script lang="ts">
  // "Legend rows": rename, hide, reorder and restyle each legend row of one
  // dataset (PyMappr's ui/legend_editor.py). Edits apply live: every change
  // calls `onchange` with the dataset's new legend_overrides.
  import { untrack } from "svelte";
  import { ArrowDown, ArrowUp } from "@lucide/svelte";
  import { toHex } from "$lib/colors";
  import { MARKER_NAMES } from "$lib/markers";
  import type { RowOverride } from "$lib/model";
  import type { EditorRow } from "$lib/symbology";
  import MarkerSwatch from "../legend/MarkerSwatch.svelte";
  import DialogFrame from "./DialogFrame.svelte";

  let {
    rows,
    overrides,
    onchange,
    onreorder,
    onClose,
  }: {
    /** editorRows(entry, options, palette, offset), in legend order. */
    rows: EditorRow[];
    /** The dataset's legend_overrides as they are now. */
    overrides: Record<string, RowOverride>;
    /** Every edit, with the whole new legend_overrides. */
    onchange: (overrides: Record<string, RowOverride>) => void;
    /** A row moved: the caller switches the legend's order to "manual"
     * (moving does nothing while it sorts itself), then applies these. */
    onreorder?: (overrides: Record<string, RowOverride>) => void;
    onClose: () => void;
  } = $props();

  /** PyMappr redraws once typing pauses this long. */
  const TYPING_PAUSE_MS = 300;

  let list = $state(untrack(() => rows.map((r) => ({ ...r }))));
  let edits = $state<Record<string, RowOverride>>(untrack(() => structuredClone($state.snapshot(overrides))));
  let pending: ReturnType<typeof setTimeout> | null = null;

  const current = () => structuredClone($state.snapshot(edits)) as Record<string, RowOverride>;

  function apply(redraw = true) {
    if (pending) clearTimeout(pending);
    pending = null;
    if (redraw) onchange(current());
    else pending = setTimeout(() => apply(true), TYPING_PAUSE_MS);
  }

  /** Set one field; going back to the default drops it, and an empty
   * override goes altogether, so the project stays clean. */
  function set(key: string, field: keyof RowOverride, value: unknown, redraw = true) {
    const override: Record<string, unknown> = { ...(edits[key] ?? {}) };
    if (value === null || value === undefined || value === "" || value === false) delete override[field];
    else override[field] = value;
    if (Object.keys(override).length) edits[key] = override as RowOverride;
    else delete edits[key];
    apply(redraw);
  }

  function setSize(key: string, text: string, redraw = true) {
    const size = Number(text);
    if (text.trim() === "" || Number.isNaN(size)) return;
    if (size >= 1 && size <= 1000) set(key, "size", size, redraw);
  }

  /** Move a row up or down. Children move only within their parent's
   * block and a parent moves with its block; every row then gets an
   * explicit position, so untouched rows do not fall to the end. */
  function move(index: number, step: number) {
    const target = index + step;
    if (target < 0 || target >= list.length) return;
    if (list[index].depth === 0 && list.some((r) => r.depth > 0)) {
      // A parent moves as a block, past the whole neighbouring block.
      const blocks: EditorRow[][] = [];
      for (const row of list) {
        if (row.depth === 0) blocks.push([row]);
        else blocks[blocks.length - 1]?.push(row);
      }
      const b = blocks.findIndex((block) => block[0].key === list[index].key);
      const other = b + step;
      if (other < 0 || other >= blocks.length) return;
      [blocks[b], blocks[other]] = [blocks[other], blocks[b]];
      list = blocks.flat();
    } else {
      if (list[index].depth !== list[target].depth) return;
      const copy = [...list];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      list = copy;
    }
    list.forEach((row, position) => {
      edits[row.key] = { ...(edits[row.key] ?? {}), order: position };
    });
    (onreorder ?? onchange)(current());
  }

  function resetAll() {
    for (const key of Object.keys(edits)) delete edits[key];
    apply();
  }
</script>

<DialogFrame title="Legend rows" {onClose} width="w-[min(760px,94vw)]">
  <p class="mb-3 text-[13px] text-muted">
    Untick a row to leave it out of the legend; its points stay on the map. A blank label uses the value from the data.
  </p>
  <table class="w-full border-collapse text-[13px]">
    <thead>
      <tr class="text-left text-[12px] text-muted">
        <th class="w-7 pb-1 font-semibold"><span class="sr-only">Show</span></th>
        <th class="pb-1 font-semibold">Row</th>
        <th class="pb-1 font-semibold">Label</th>
        <th class="pb-1 font-semibold">Color</th>
        <th class="pb-1 font-semibold">Symbol</th>
        <th class="pb-1 font-semibold">Size</th>
        <th class="pb-1 font-semibold">Move</th>
      </tr>
    </thead>
    <tbody>
      {#each list as row, index (row.key)}
        {@const o = edits[row.key] ?? {}}
        {@const color = o.color || row.style.color}
        {@const marker = o.marker || row.style.marker}
        <tr class="border-t border-line/60">
          <td class="py-1">
            <input
              type="checkbox"
              checked={!o.hidden}
              aria-label="Show {row.value || '(blank)'}"
              onchange={(e) => set(row.key, "hidden", !e.currentTarget.checked)}
            />
          </td>
          <td class="max-w-48 truncate py-1 pr-2" style:padding-left="{row.depth * 1.4}rem" title={row.value}>
            {row.value || "(blank)"}
          </td>
          <td class="py-1 pr-2">
            <input
              class="field"
              value={o.label ?? ""}
              placeholder={row.value || "(blank)"}
              oninput={(e) => set(row.key, "label", e.currentTarget.value.trim(), false)}
              onchange={(e) => set(row.key, "label", e.currentTarget.value.trim())}
            />
          </td>
          <td class="py-1 pr-2">
            <input
              type="color"
              class="h-7 w-10 cursor-pointer rounded border border-line bg-raised p-0.5"
              value={toHex(color)}
              aria-label="Color for {row.value || '(blank)'}"
              onchange={(e) => set(row.key, "color", e.currentTarget.value)}
            />
          </td>
          <td class="py-1 pr-2">
            <div class="flex items-center gap-1.5">
              <MarkerSwatch {marker} {color} size={16} />
              <select class="field" value={marker} onchange={(e) => set(row.key, "marker", e.currentTarget.value)}>
                {#each MARKER_NAMES as name (name)}
                  <option value={name}>{name}</option>
                {/each}
              </select>
            </div>
          </td>
          <td class="py-1 pr-2">
            <input
              type="number"
              class="field w-20"
              min="4"
              max="400"
              step="4"
              value={o.size || row.style.size}
              oninput={(e) => setSize(row.key, e.currentTarget.value, false)}
              onchange={(e) => setSize(row.key, e.currentTarget.value)}
            />
          </td>
          <td class="py-1">
            <div class="flex">
              <button class="btn !p-1" aria-label="Move up" onclick={() => move(index, -1)}><ArrowUp size={14} /></button>
              <button class="btn !p-1" aria-label="Move down" onclick={() => move(index, 1)}><ArrowDown size={14} /></button>
            </div>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
  {#snippet actions()}
    <button class="btn border border-line" onclick={resetAll}>Reset all rows</button>
    <span class="flex-1"></span>
    <button class="btn-primary" onclick={onClose}>Close</button>
  {/snippet}
</DialogFrame>
