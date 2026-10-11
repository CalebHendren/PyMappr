<script lang="ts">
  import { app, type Corner } from "$lib/state.svelte";
  import Section from "./Section.svelte";

  const corners: [Corner, string][] = [
    ["upper-left", "Upper left"],
    ["upper-right", "Upper right"],
    ["lower-left", "Lower left"],
    ["lower-right", "Lower right"],
  ];
</script>

<Section title="Legend">
  <label class="flex items-center gap-2">
    <input type="checkbox" class="accent-[var(--accent)]" bind:checked={app.legend.show} />
    Show the legend
  </label>
  <label class="block">
    <span class="label">Title</span>
    <input class="field mt-1" placeholder="No title" bind:value={app.legend.title} />
  </label>
  <div>
    <span class="label">Corner</span>
    <div class="mt-1 grid grid-cols-2 gap-1" role="radiogroup" aria-label="Legend corner">
      {#each corners as [value, label] (value)}
        <button
          class="btn justify-center border border-line"
          class:!bg-accent-soft={app.legend.corner === value}
          role="radio"
          aria-checked={app.legend.corner === value}
          onclick={() => (app.legend.corner = value)}>{label}</button
        >
      {/each}
    </div>
  </div>
</Section>

<Section title="Entries">
  <label class="flex items-center gap-2">
    <input type="checkbox" class="accent-[var(--accent)]" bind:checked={app.legend.italic} />
    Italic names
  </label>
  <label class="flex items-center gap-2">
    <input type="checkbox" class="accent-[var(--accent)]" bind:checked={app.legend.counts} />
    Point counts
  </label>
  <label class="flex items-center gap-2">
    <input type="checkbox" class="accent-[var(--accent)]" bind:checked={app.legend.framed} />
    Frame
  </label>
  <label class="block">
    <span class="label">Order</span>
    <select class="field mt-1" bind:value={app.legend.sort}>
      <option value="data">As in the data</option>
      <option value="az">A to Z</option>
    </select>
  </label>
</Section>
