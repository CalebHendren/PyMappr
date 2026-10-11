<script lang="ts">
  import { app } from "$lib/state.svelte";
  import { LAYERS } from "$lib/styles";
  import Section from "./Section.svelte";

  let { onChooseDataDir }: { onChooseDataDir: () => void } = $props();

  const shown = LAYERS.filter((l) => l.id !== "graticule");
</script>

<Section title="Base layers">
  {#each shown as layer (layer.id)}
    <label class="flex items-center gap-2">
      <input type="checkbox" class="accent-[var(--accent)]" bind:checked={app.layers[layer.id]} />
      <span
        class="inline-block h-3 w-5 rounded-[2px] border"
        style:background={layer.fill === "lakes" ? "#a6cae0" : (layer.fill ?? "transparent")}
        style:border-color={layer.stroke ?? "#c9c2b0"}
        style:border-width="{Math.max(1, layer.width * 1.6)}px"
        aria-hidden="true"
      ></span>
      {layer.label}
    </label>
  {/each}
  {#if app.layers.lakes}
    <label class="block pl-6">
      <span class="label">Lake fill</span>
      <select class="field mt-1" bind:value={app.lakeFill}>
        <option value="blue">Blue</option>
        <option value="grey">Grey</option>
        <option value="none">Outline only</option>
      </select>
    </label>
  {/if}
  <p class="text-[12px] text-muted">
    States and provinces exist only at the finest scale, so they take a moment to load the first time.
  </p>
</Section>

<Section title="Map data">
  <p class="break-all text-[12px] text-muted">{app.info?.dataDir ?? "Not set"}</p>
  <button class="btn border border-line" onclick={onChooseDataDir}>Change folder</button>
</Section>
