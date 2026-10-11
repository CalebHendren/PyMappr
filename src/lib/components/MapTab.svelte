<script lang="ts">
  import { app } from "$lib/state.svelte";
  import Section from "./Section.svelte";

  const custom = $derived(app.projection.name.startsWith("Globe") || app.projection.name.startsWith("Lambert"));
  const steps = [1, 5, 10, 15, 30];

  function setCentre(axis: "lon0" | "lat0", raw: string) {
    const v = raw.trim() === "" ? null : Number(raw);
    if (v !== null && !Number.isFinite(v)) return;
    app.projection = { ...app.projection, [axis]: v };
    app.view = null;
  }
</script>

<Section title="Projection">
  <select class="field" value={app.projection.name} onchange={(e) => app.setProjection(e.currentTarget.value)}>
    {#each app.info?.projections ?? [] as name (name)}<option value={name}>{name}</option>{/each}
  </select>
  {#if custom}
    <p class="text-[12px] text-muted">Centre of the map. Leave blank for the projection's own centre.</p>
    <div class="grid grid-cols-2 gap-2">
      <label class="block">
        <span class="label">Longitude</span>
        <input
          class="field mt-1"
          inputmode="decimal"
          placeholder="default"
          value={app.projection.lon0 ?? ""}
          onchange={(e) => setCentre("lon0", e.currentTarget.value)}
        />
      </label>
      <label class="block">
        <span class="label">Latitude</span>
        <input
          class="field mt-1"
          inputmode="decimal"
          placeholder="default"
          value={app.projection.lat0 ?? ""}
          onchange={(e) => setCentre("lat0", e.currentTarget.value)}
        />
      </label>
    </div>
  {/if}
</Section>

<Section title="Graticule">
  <div class="flex flex-wrap gap-1" role="radiogroup" aria-label="Graticule spacing">
    <button
      class="btn border border-line"
      class:!bg-accent-soft={!app.layers.graticule}
      role="radio"
      aria-checked={!app.layers.graticule}
      onclick={() => (app.layers.graticule = false)}>Off</button
    >
    {#each steps as s (s)}
      {@const on = app.layers.graticule && app.graticuleStep === s}
      <button
        class="btn border border-line"
        class:!bg-accent-soft={on}
        role="radio"
        aria-checked={on}
        onclick={() => {
          app.graticuleStep = s;
          app.layers.graticule = true;
        }}>{s}°</button
      >
    {/each}
  </div>
</Section>

<Section title="Water">
  <label class="block">
    <span class="label">Ocean</span>
    <select class="field mt-1" bind:value={app.oceanFill}>
      <option value="blue">Blue</option>
      <option value="grey">Grey</option>
      <option value="none">White</option>
    </select>
  </label>
</Section>
