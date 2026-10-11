<script lang="ts">
  // Download the map data (a port of PyMappr's fetch_data.py), or point at
  // a folder that already has it, such as PyMappr's own data folder.
  import { api, type DataStatus, type JobStatus } from "$lib/api";
  import { store } from "$lib/store.svelte";
  import Modal from "./Modal.svelte";

  let { onClose, onChooseFolder, required = false }: { onClose: () => void; onChooseFolder: () => void; required?: boolean } =
    $props();

  let status = $state<DataStatus | null>(null);
  let rasters = $state(true);
  let extras = $state(false);
  let job = $state<JobStatus | null>(null);
  let error = $state<string | null>(null);

  $effect(() => {
    api.dataStatus(null).then((s) => (status = s)).catch(() => {});
  });

  async function start() {
    error = null;
    try {
      const id = await api.dataDownload(null, rasters, extras);
      const poll = async () => {
        const s = await api.jobStatus(id);
        job = s;
        if (!s || s.done) {
          if (s?.error) error = s.error;
          else {
            await store.init();
            store.view = null;
            store.setStatus("Map data is ready.");
            onClose();
          }
          return;
        }
        setTimeout(poll, 500);
      };
      poll();
    } catch (e) {
      error = String(e);
    }
  }
</script>

<Modal title="Map data" {onClose}>
  <div class="max-w-xl space-y-3">
    {#if required}
      <p>RustyMappr draws its maps from Natural Earth data. Download it once, or use a folder that already has it.</p>
    {/if}
    {#if status}
      <p class="text-muted">
        In {status.dir}: {status.vectorsReady} of {status.vectorsTotal} vector layers, {status.rastersReady} of {status.rastersTotal} relief
        basemaps{status.extrasReady.length ? `, ${status.extrasReady.length} optional overlays` : ""}.
      </p>
    {/if}
    <label class="check"><input type="checkbox" bind:checked={rasters} disabled={!!job} /> Relief and Blue Marble basemaps (about 290 MB more to download; the vector layers are about 70 MB)</label>
    <label class="check">
      <input type="checkbox" bind:checked={extras} disabled={!!job} />
      Biodiversity hotspots and ecoregion overlays (RESOLVE, Conservation International, WWF/TNC; CC-BY)
    </label>
    {#if job}
      <div class="space-y-1">
        <div class="h-2 overflow-hidden rounded-full bg-line">
          <div class="h-full bg-accent transition-[width]" style:width="{Math.round((job.progress ?? 0) * 100)}%"></div>
        </div>
        <p class="hint">{job.step}</p>
      </div>
    {/if}
    {#if error}<p class="text-danger">{error}</p>{/if}
    <p class="hint">Natural Earth data is public domain. Downloads are kept, so an interrupted download picks up where it stopped.</p>
  </div>

  {#snippet actions()}
    <button class="btn mr-auto" onclick={onChooseFolder} disabled={!!job && !job.done}>Use an existing folder…</button>
    {#if job && !job.done}
      <button class="btn" onclick={() => api.jobCancel(job!.id)}>Cancel download</button>
    {:else}
      {#if !required}<button class="btn" onclick={onClose}>Close</button>{/if}
      <button class="btn-primary" onclick={start}>Download</button>
    {/if}
  {/snippet}
</Modal>
