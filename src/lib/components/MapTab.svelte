<script lang="ts">
  import { store, CONTINENT_EXTENTS } from "$lib/store.svelte";
  import { BASEMAPS, CONTINENTS, CORNERS } from "$lib/styles";
  import Section from "./Section.svelte";

  let { onSaveMap, onExportCode }: { onSaveMap: () => void; onExportCode: () => void } = $props();

  const m = $derived(store.doc.map);
  const custom = $derived(m.projection.startsWith("Globe") || m.projection.startsWith("Lambert"));

  // Default centres PyMappr seeds when a Globe/Lambert projection is chosen.
  const ORIGINS: Record<string, [number, number]> = {
    "Globe (Orthographic)": [0, 0],
    "Lambert: N. America": [-96, 40],
    "Lambert: Europe": [10, 52],
    "Lambert: Asia": [95, 30],
    "Lambert: S. America": [-60, -32],
    "Lambert: Africa": [20, 5],
    "Lambert Azimuthal (custom)": [0, 0],
  };

  function chooseProjection(name: string) {
    const o = ORIGINS[name];
    store.setProjection(name, o ? String(o[0]) : "", o ? String(o[1]) : "");
  }

  function setCentre(axis: "proj_lon0" | "proj_lat0", value: string) {
    if (value.trim() !== "" && !Number.isFinite(Number(value))) return;
    store.doc.map[axis] = value.trim();
  }

  function limitTo(name: string) {
    m.continent = name;
    store.frame(CONTINENT_EXTENTS[name] ?? CONTINENT_EXTENTS.World);
  }

  function useCurrentView() {
    const v = store.view;
    if (!v) return;
    Promise.all([
      store.cursorAt(v.x, v.y + v.h),
      store.cursorAt(v.x + v.w, v.y),
    ]).then(([sw, ne]) => {
      if (!sw || !ne) return;
      Object.assign(m.inset, { region: "custom", lon_min: sw[0], lat_min: sw[1], lon_max: ne[0], lat_max: ne[1] });
    });
  }

  const num = (v: string, lo: number, hi: number, fallback: number) => {
    const n = Number(v.replace(",", "."));
    return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : fallback;
  };
  const optNum = (v: string) => (v.trim() === "" || !Number.isFinite(Number(v)) ? null : Number(v));
</script>

<Section title="View">
  <label class="row">
    <span class="label">Limit to</span>
    <select class="field" value={m.continent} onchange={(e) => limitTo(e.currentTarget.value)}>
      {#each CONTINENTS as c (c)}<option>{c}</option>{/each}
    </select>
  </label>
  <label class="row">
    <span class="label">Orientation</span>
    <select class="field" bind:value={m.orientation}>
      <option>Landscape</option>
      <option>Portrait</option>
    </select>
  </label>
  <label class="row">
    <span class="label">Projection</span>
    <select class="field" value={m.projection} onchange={(e) => chooseProjection(e.currentTarget.value)}>
      {#each store.info?.projections ?? [] as p (p)}<option>{p}</option>{/each}
    </select>
  </label>
  <div class="grid grid-cols-2 gap-2">
    <label class="block">
      <span class="label">Centre lon</span>
      <input class="field mt-1" disabled={!custom} value={m.proj_lon0} onchange={(e) => setCentre("proj_lon0", e.currentTarget.value)} />
    </label>
    <label class="block">
      <span class="label">Centre lat</span>
      <input class="field mt-1" disabled={!custom} value={m.proj_lat0} onchange={(e) => setCentre("proj_lat0", e.currentTarget.value)} />
    </label>
  </div>
  {#if m.projection.startsWith("Globe")}
    <p class="hint">Drag the globe to turn it.</p>
  {/if}
  <label class="row">
    <span class="label">Basemap</span>
    <select class="field" bind:value={m.basemap}>
      {#each BASEMAPS as [v, label] (v)}<option value={v}>{label}</option>{/each}
    </select>
  </label>
</Section>

<Section title="Compass">
  <label class="check"><input type="checkbox" bind:checked={m.compass_options.show} onchange={() => (m.compass = m.compass_options.show)} /> Show north arrow</label>
  {#if m.compass_options.show}
    <label class="row">
      <span class="label">Position</span>
      <select class="field" bind:value={m.compass_options.position}>
        {#each CORNERS as c (c)}<option>{c}</option>{/each}
      </select>
    </label>
    <label class="row">
      <span class="label">Style</span>
      <select class="field" bind:value={m.compass_options.style}>
        <option value="arrow">Arrow with N</option>
        <option value="triangle">Filled triangle</option>
      </select>
    </label>
    <label class="row">
      <span class="label">Size</span>
      <input class="field" type="number" min="0.5" max="3" step="0.1" value={m.compass_options.size}
        onchange={(e) => (m.compass_options.size = num(e.currentTarget.value, 0.5, 3, 1))} />
    </label>
  {/if}
</Section>

<Section title="Scale bar">
  <label class="check"><input type="checkbox" bind:checked={m.scale_bar.show} /> Show scale bar</label>
  {#if m.scale_bar.show}
    <label class="row">
      <span class="label">Units</span>
      <select class="field" bind:value={m.scale_bar.units}>
        <option value="km">Kilometres</option>
        <option value="mi">Miles</option>
        <option value="both">Both</option>
      </select>
    </label>
    <label class="row">
      <span class="label">Position</span>
      <select class="field" value={m.scale_bar.position}
        onchange={(e) => Object.assign(m.scale_bar, { position: e.currentTarget.value, anchor_x: null, anchor_y: null })}>
        {#each CORNERS as c (c)}<option>{c}</option>{/each}
      </select>
    </label>
    <label class="row">
      <span class="label">Style</span>
      <select class="field" bind:value={m.scale_bar.style}>
        <option value="segmented">Segmented</option>
        <option value="plain">Plain bar</option>
      </select>
    </label>
    <label class="row">
      <span class="label">Length</span>
      <select class="field" bind:value={m.scale_bar.length_mode}>
        <option value="auto">Automatic</option>
        <option value="fixed">Fixed</option>
      </select>
    </label>
    {#if m.scale_bar.length_mode === "fixed"}
      <label class="row">
        <span class="label">Fixed length</span>
        <input class="field" type="number" min="0.1" max="100000" value={m.scale_bar.fixed_length ?? ""}
          onchange={(e) => (m.scale_bar.fixed_length = optNum(e.currentTarget.value))} />
      </label>
    {/if}
    <label class="check"><input type="checkbox" bind:checked={m.scale_bar.draggable} /> Drag to reposition</label>
    <button class="btn border border-line" onclick={() => Object.assign(m.scale_bar, { anchor_x: null, anchor_y: null })}>Reset position</button>
    <p class="hint">Lengths are measured along the bar's own row, so they stay accurate on any projection.</p>
  {/if}
</Section>

<Section title="Inset map">
  <label class="check"><input type="checkbox" bind:checked={m.inset.show} /> Show inset map</label>
  {#if m.inset.show}
    <label class="row">
      <span class="label">Shows</span>
      <select class="field" bind:value={m.inset.region}>
        <option value="state">State / province</option>
        <option value="country">Country</option>
        <option value="around">Around the map</option>
        {#each CONTINENTS as c (c)}<option value={c}>{c}</option>{/each}
        <option value="custom">Custom</option>
      </select>
    </label>
    <label class="row">
      <span class="label">Times the map's area</span>
      <input class="field" type="number" min="2" max="50" disabled={m.inset.region !== "around"} value={m.inset.zoom_out}
        onchange={(e) => (m.inset.zoom_out = num(e.currentTarget.value, 2, 50, 6))} />
    </label>
    <div class="grid grid-cols-2 gap-2" class:opacity-50={m.inset.region !== "custom"}>
      {#each [["lon_min", "West lon"], ["lon_max", "East lon"], ["lat_min", "South lat"], ["lat_max", "North lat"]] as [key, label] (key)}
        <label class="block">
          <span class="label">{label}</span>
          <input class="field mt-1" disabled={m.inset.region !== "custom"} value={m.inset[key as "lon_min"] ?? ""}
            onchange={(e) => (m.inset[key as "lon_min"] = optNum(e.currentTarget.value))} />
        </label>
      {/each}
    </div>
    <button class="btn border border-line" onclick={useCurrentView}>Use current view</button>
    <label class="row">
      <span class="label">Projection</span>
      <select class="field" bind:value={m.inset.projection}>
        <option value="same">Same as map</option>
        <option>Equirectangular</option>
        <option>Robinson</option>
        <option>Globe</option>
      </select>
    </label>
    <label class="row">
      <span class="label">Position</span>
      <select class="field" value={m.inset.position}
        onchange={(e) => Object.assign(m.inset, { position: e.currentTarget.value, anchor_x: null, anchor_y: null })}>
        {#each CORNERS as c (c)}<option>{c}</option>{/each}
      </select>
    </label>
    <label class="row">
      <span class="label">Width (of the map)</span>
      <input class="field" type="number" min="0.1" max="0.6" step="0.05" value={m.inset.size}
        onchange={(e) => (m.inset.size = num(e.currentTarget.value, 0.1, 0.6, 0.3))} />
    </label>
    <div class="grid grid-cols-2 gap-1">
      <label class="check"><input type="checkbox" bind:checked={m.inset.countries} /> Countries</label>
      <label class="check"><input type="checkbox" bind:checked={m.inset.states} /> States</label>
      <label class="check"><input type="checkbox" bind:checked={m.inset.counties} /> US Counties</label>
      <label class="check"><input type="checkbox" bind:checked={m.inset.land} /> Land fill</label>
      <label class="check"><input type="checkbox" bind:checked={m.inset.points} /> Your points</label>
      <label class="check"><input type="checkbox" bind:checked={m.inset.box} /> Linking box</label>
    </div>
    <label class="row">
      <span class="label">Ocean</span>
      <select class="field" bind:value={m.inset.ocean}>
        <option value="none">None</option>
        <option value="grey">Grey</option>
        <option value="blue">Blue</option>
      </select>
    </label>
    <label class="row">
      <span class="label">Box colour</span>
      <input type="color" class="h-7 w-12 rounded border border-line" bind:value={m.inset.box_color} />
    </label>
    <label class="check"><input type="checkbox" bind:checked={m.inset.draggable} /> Drag to reposition</label>
    <button class="btn border border-line" onclick={() => Object.assign(m.inset, { anchor_x: null, anchor_y: null })}>Reset position</button>
  {/if}
</Section>

<Section title="Graticule">
  <label class="row">
    <span class="label">Grid spacing</span>
    <select class="field" bind:value={m.graticule}>
      <option>Off</option>
      <option>1°</option>
      <option>5°</option>
      <option>10°</option>
    </select>
  </label>
  <label class="check"><input type="checkbox" bind:checked={m.hide_grid_labels} /> Hide grid labels</label>
</Section>

<Section title="Export">
  <div class="flex flex-wrap gap-2">
    <button class="btn border border-line" onclick={onSaveMap}>Save map as…</button>
    <button class="btn border border-line" onclick={onExportCode}>Export as code (Python/R)…</button>
  </div>
</Section>
