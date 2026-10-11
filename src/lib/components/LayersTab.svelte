<script lang="ts">
  import { api } from "$lib/api";
  import { store } from "$lib/store.svelte";
  import { FILL_STYLES, LAYER_SECTIONS, LINE_STYLES, NE_MARKERS, SECTION_FOR_KIND, type LayerRow } from "$lib/styles";
  import Section from "./Section.svelte";

  let { onChooseDataDir, onDownloadData }: { onChooseDataDir: () => void; onDownloadData: () => void } = $props();

  const m = $derived(store.doc.map);

  function checked(row: LayerRow): boolean {
    return Boolean(m[SECTION_FOR_KIND[row.kind]][row.key]);
  }
  function toggle(row: LayerRow, on: boolean) {
    m[SECTION_FOR_KIND[row.kind]][row.key] = on;
  }
  function swatch(row: LayerRow) {
    if (row.kind === "fill") {
      const f = FILL_STYLES[row.key];
      return { bg: f?.face ?? "#ddd", border: f?.edge ?? "#c9c2b0" };
    }
    if (row.kind === "point") return { bg: NE_MARKERS[row.key]?.face ?? "#333", border: "transparent", dot: true };
    const l = LINE_STYLES[row.key];
    return { bg: "transparent", border: l?.color ?? "#555", dashed: Boolean(l?.dash) };
  }

  // Districts from geoBoundaries for countries outside the US.
  let districts = $state<{ iso3: string; name: string; license: string; source: string }[]>([]);
  let fetching = $state<string | null>(null);

  async function refreshDistricts() {
    try {
      districts = await api.districtsList();
    } catch {
      districts = [];
    }
  }
  $effect(() => {
    if (store.info?.dataDir) refreshDistricts();
  });

  async function getDistricts() {
    if (!store.view) return;
    try {
      const iso = await api.countriesInView($state.snapshot(store.projection), $state.snapshot(store.view));
      const missing = iso.filter((c) => !districts.some((d) => d.iso3 === c));
      if (!missing.length) {
        store.setStatus(iso.length ? "Districts for every country in view are already downloaded." : "No country outside the US is in view.");
        return;
      }
      const id = await api.districtsFetch(missing);
      fetching = `Downloading districts for ${missing.join(", ")}…`;
      const poll = async () => {
        const s = await api.jobStatus(id);
        if (!s || s.done) {
          fetching = null;
          if (s?.error) store.fail(s.error);
          await refreshDistricts();
          showDistricts(missing, true);
          return;
        }
        fetching = s.step || fetching;
        setTimeout(poll, 600);
      };
      poll();
    } catch (e) {
      store.fail(e);
    }
  }

  function showDistricts(iso: string[], on: boolean) {
    const next = on ? [...new Set([...store.districts, ...iso])] : store.districts.filter((c) => !iso.includes(c));
    store.districts = next;
    api.setSettings({ districtsShown: next }).catch(() => {});
  }

  async function removeDistricts(iso3: string) {
    await api.districtsRemove(iso3).catch((e) => store.fail(e));
    showDistricts([iso3], false);
    refreshDistricts();
  }
</script>

<p class="hint mb-3">Detail switches between Natural Earth's 1:110m, 1:50m and 1:10m data as you zoom.</p>

<label class="check mb-4 rounded-md border border-line bg-raised px-2 py-1.5">
  <input type="checkbox" checked={store.advanced} onchange={(e) => store.setAdvanced(e.currentTarget.checked)} />
  <span>
    Show advanced options
    <span class="block text-[12px] text-muted">Sovereign states, map units, disputed areas, time zones, maritime and EEZ lines</span>
  </span>
</label>
{#if store.hiddenAdvancedOn}
  <p class="hint mb-3">
    {store.hiddenAdvancedOn} advanced {store.hiddenAdvancedOn === 1 ? "layer is" : "layers are"} on in this project and still drawn.
  </p>
{/if}

{#each LAYER_SECTIONS as section (section.title)}
  {@const rows = section.rows.filter((r) => store.advanced || !r.advanced)}
  <Section title={section.title}>
    {#each rows as row (row.key + row.kind)}
      {@const s = swatch(row)}
      <label class="check">
        <input type="checkbox" checked={checked(row)} onchange={(e) => toggle(row, e.currentTarget.checked)} />
        <span
          class="inline-block h-3 w-5 shrink-0 border"
          class:rounded-full={s.dot}
          class:border-dashed={s.dashed}
          style:background={s.bg}
          style:border-color={s.border}
          aria-hidden="true"
        ></span>
        {row.text}
      </label>
      {#if row.key === "countries" && section.title === "Borders & areas"}
        <!-- Cities and capitals sit with the borders in PyMappr. -->
        <label class="check">
          <input type="checkbox" checked={m.points.cities} onchange={(e) => (m.points.cities = e.currentTarget.checked)} />
          <span class="inline-block h-3 w-5 shrink-0 rounded-full" style:background="#333333" aria-hidden="true"></span>
          Populated places (cities)
        </label>
        {#if m.points.cities}
          <label class="check pl-6"><input type="checkbox" bind:checked={m.capitals_only} /> Capitals only</label>
        {/if}
      {/if}
    {/each}
    {#if section.title === "Borders & areas"}
      <p class="hint">Cities appear as you zoom in.</p>
    {:else if section.title === "Water & marine"}
      <label class="row">
        <span class="label">Oceans</span>
        <select class="field" bind:value={m.ocean}>
          <option value="none">None</option>
          <option value="grey">Greyscale</option>
          <option value="blue">Blue</option>
        </select>
      </label>
      <label class="check"><input type="checkbox" bind:checked={m.bathymetry} /> Bathymetry (slower)</label>
      <label class="check">
        <input type="checkbox" checked={m.lines.lakes_outline} onchange={(e) => (m.lines.lakes_outline = e.currentTarget.checked)} />
        Lakes (outlines)
      </label>
      <label class="row">
        <span class="label">Lakes fill</span>
        <select class="field" bind:value={m.lake_fill}>
          <option value="none">None</option>
          <option value="grey">Greyscale</option>
          <option value="blue">Blue</option>
        </select>
      </label>
    {:else if section.title === "Biodiversity & ecoregions"}
      <p class="hint">Optional downloads; get them with Download map data.</p>
    {/if}
  </Section>
{/each}

<Section title="Counties and districts outside the US">
  <p class="hint">
    US counties come with Natural Earth. For other countries, RustyMappr can download district (ADM2) boundaries from
    geoBoundaries for the countries in view.
  </p>
  <button class="btn border border-line" onclick={getDistricts} disabled={!store.view || fetching !== null}>Get districts for countries in view</button>
  {#if fetching}<p class="hint">{fetching}</p>{/if}
  {#each districts as d (d.iso3)}
    <div class="flex items-center gap-2">
      <label class="check flex-1">
        <input type="checkbox" checked={store.districts.includes(d.iso3)} onchange={(e) => showDistricts([d.iso3], e.currentTarget.checked)} />
        <span class="truncate" title="{d.name}: {d.license}">{d.name}</span>
      </label>
      <button class="btn !px-1.5 !py-0.5 text-[12px]" onclick={() => removeDistricts(d.iso3)}>Remove</button>
    </div>
  {/each}
</Section>

<Section title="Lines">
  <label class="block">
    <span class="label">Line thickness: {m.line_width.toFixed(2)}×</span>
    <input type="range" min="0.25" max="3" step="0.25" class="w-full accent-[var(--accent)]" bind:value={m.line_width} />
  </label>
</Section>

<Section title="Map data">
  <p class="break-all text-[12px] text-muted">{store.info?.dataDir ?? "Not set up"}</p>
  <div class="flex flex-wrap gap-2">
    <button class="btn border border-line" onclick={onDownloadData}>Download map data…</button>
    <button class="btn border border-line" onclick={onChooseDataDir}>Use another folder…</button>
  </div>
</Section>
