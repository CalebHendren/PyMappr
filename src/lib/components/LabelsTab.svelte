<script lang="ts">
  import { store } from "$lib/store.svelte";
  import { LABEL_ROWS } from "$lib/styles";
  import Section from "./Section.svelte";

  const m = $derived(store.doc.map);
</script>

<Section title="Labels">
  {#each LABEL_ROWS.filter((r) => store.advanced || !r.advanced) as row (row.key)}
    <label class="check">
      <input type="checkbox" checked={m.labels[row.key]} onchange={(e) => (m.labels[row.key] = e.currentTarget.checked)} />
      {row.text}
    </label>
  {/each}
  <p class="hint">Labels appear as you zoom in, biggest features first. Overlapping labels are left out.</p>
</Section>

<Section title="Placement">
  <label class="check"><input type="checkbox" bind:checked={store.allowLabelDrag} /> Allow dragging labels</label>
  <p class="hint">Drag a label to nudge it a little; right-click it to put it back.</p>
</Section>
