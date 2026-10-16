<script lang="ts">
  // Every legend setting, built from PyMappr's table of them (styles.ts
  // LEGEND_SECTIONS) so the rows match its Legend tab.
  import { ChevronDown, ChevronRight } from "@lucide/svelte";
  import { store } from "$lib/store.svelte";
  import { LEGEND_SECTIONS } from "$lib/styles";

  let { onCustomize }: { onCustomize: () => void } = $props();

  const legend = $derived(store.doc.legend as unknown as Record<string, unknown>);
  let open = $state<Record<string, boolean>>(
    Object.fromEntries(LEGEND_SECTIONS.map(([title, expanded]) => [title, expanded !== false])),
  );

  function setNumber(field: string, raw: string, [lo, hi]: [number, number, number]) {
    if (raw.trim() === "" && field === "handle_text_pad") {
      legend[field] = null;
      return;
    }
    const n = Number(raw.replace(",", "."));
    if (Number.isFinite(n)) legend[field] = Math.min(hi, Math.max(lo, n));
  }

  function setLocation(value: string) {
    // Picking a position forgets where the legend was dragged.
    store.doc.legend.location = value;
    store.doc.legend.anchor = null;
  }
</script>

{#each LEGEND_SECTIONS as [title, expanded, rows] (title)}
  <section class="mb-4">
    {#if expanded === null}
      <h3 class="mb-2 text-[13px] font-semibold">{title}</h3>
    {:else}
      <button class="mb-2 flex w-full items-center gap-1 text-left text-[13px] font-semibold" aria-expanded={open[title]}
        onclick={() => (open[title] = !open[title])}>
        {#if open[title]}<ChevronDown size={14} />{:else}<ChevronRight size={14} />{/if}
        {title}
      </button>
    {/if}
    {#if expanded === null || open[title]}
      <div class="space-y-2">
        {#each rows as row, i (i)}
          {@const [field, kind, label] = row}
          {#if kind === "note"}
            <p class="hint">{label}</p>
          {:else if kind === "check" && field}
            <label class="check"><input type="checkbox" checked={Boolean(legend[field])} onchange={(e) => (legend[field] = e.currentTarget.checked)} /> {label}</label>
          {:else if kind === "combo" && field}
            <label class="row">
              <span class="label">{label}</span>
              <select class="field" value={String(legend[field])} onchange={(e) => setLocation(e.currentTarget.value)}>
                {#each row[3] as string[] as v (v)}<option>{v}</option>{/each}
              </select>
            </label>
          {:else if kind === "choice" && field}
            <label class="row">
              <span class="label">{label}</span>
              <select class="field" value={String(legend[field] ?? "")} onchange={(e) => (legend[field] = e.currentTarget.value)}>
                {#each Object.entries(row[3] as Record<string, string>) as [name, v] (v)}<option value={v}>{name}</option>{/each}
              </select>
            </label>
          {:else if kind === "text" && field}
            <label class="row">
              <span class="label">{label}</span>
              <input class="field" value={(legend[field] as string | null) ?? ""}
                oninput={(e) => (legend[field] = field === "title" && e.currentTarget.value === "" ? null : e.currentTarget.value)} />
            </label>
          {:else if kind === "number" && field}
            {@const range = row[3] as [number, number, number]}
            <label class="row">
              <span class="label">{label}</span>
              <input class="field" type="number" min={range[0]} max={range[1]} step={range[2]}
                value={legend[field] === null ? "" : String(legend[field])}
                onchange={(e) => setNumber(field, e.currentTarget.value, range)} />
            </label>
          {:else if kind === "color" && field}
            <label class="row">
              <span class="label">{label}</span>
              <input type="color" class="h-7 w-12 rounded border border-line" value={String(legend[field])}
                oninput={(e) => (legend[field] = e.currentTarget.value)} />
            </label>
          {:else if kind === "style" && field}
            <div class="row">
              <span class="label">{label}</span>
              <div class="flex gap-1">
                {#each [["bold", "B", "font-bold"], ["italic", "I", "italic"], ["underline", "U", "underline"]] as [suffix, text, cls] (suffix)}
                  {@const key = `${field}_${suffix}`}
                  <button
                    class="btn w-8 justify-center border border-line {cls}"
                    class:!bg-accent-soft={Boolean(legend[key])}
                    aria-pressed={Boolean(legend[key])}
                    onclick={() => (legend[key] = !legend[key])}>{text}</button
                  >
                {/each}
              </div>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  </section>
{/each}

<section class="mb-4">
  <h3 class="mb-2 text-[13px] font-semibold">Placement</h3>
  <div class="space-y-2">
    <label class="check"><input type="checkbox" bind:checked={store.doc.legend.draggable} /> Allow dragging the legend</label>
    <p class="hint">Drag it anywhere; right-click it to snap it back to its position.</p>
    <button class="btn border border-line" onclick={onCustomize} disabled={!store.active}>Customize legend rows…</button>
  </div>
</section>
