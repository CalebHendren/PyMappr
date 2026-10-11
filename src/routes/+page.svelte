<script lang="ts">
  import { onMount } from "svelte";
  import { open } from "@tauri-apps/plugin-dialog";
  import { FolderOpen, LoaderCircle } from "@lucide/svelte";
  import { api, type TablePreview } from "$lib/api";
  import { app } from "$lib/state.svelte";
  import Toolbar from "$lib/components/Toolbar.svelte";
  import Sidebar from "$lib/components/Sidebar.svelte";
  import MapView from "$lib/components/MapView.svelte";
  import StatusBar from "$lib/components/StatusBar.svelte";
  import ColumnMapper from "$lib/components/ColumnMapper.svelte";
  import ExportDialog from "$lib/components/ExportDialog.svelte";

  let importing = $state<{ path: string; preview: TablePreview } | null>(null);
  let exporting = $state(false);

  onMount(() => {
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) app.toggleTheme();
    app.init();
  });

  async function addData() {
    const path = await open({
      multiple: false,
      filters: [
        { name: "Tables", extensions: ["csv", "tsv", "txt", "xlsx", "xlsm", "xls", "ods"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    if (typeof path !== "string") return;
    try {
      importing = { path, preview: await api.inspectTable(path, null, null) };
    } catch (e) {
      app.error = String(e);
    }
  }

  async function chooseDataDir() {
    const dir = await open({ directory: true, title: "Folder with the Natural Earth shapefiles" });
    if (typeof dir !== "string") return;
    try {
      await api.setDataDir(dir);
      await app.init();
    } catch (e) {
      app.error = String(e);
    }
  }
</script>

<div class="grid h-screen grid-cols-[320px_1fr] grid-rows-[auto_1fr_auto]">
  <div class="col-span-2">
    <Toolbar onAddData={addData} onExport={() => (exporting = true)} />
  </div>

  <Sidebar onAddData={addData} onChooseDataDir={chooseDataDir} />

  <main class="relative min-w-0 bg-paper">
    <MapView />

    {#if app.info && !app.info.dataDir}
      <div class="absolute inset-0 grid place-items-center p-6">
        <div class="max-w-md rounded-lg border border-line bg-panel p-6 shadow-sm">
          <h2 class="text-lg font-semibold">Map data needed</h2>
          <p class="mt-2 text-muted">
            RustyMappr draws its base map from Natural Earth shapefiles. Point it at PyMappr's
            <code class="text-ink">data\shapes</code> folder, which <code class="text-ink">scripts/fetch_data.py</code> fills.
          </p>
          <button class="btn-primary mt-4" onclick={chooseDataDir}><FolderOpen size={15} /> Choose folder</button>
        </div>
      </div>
    {:else if app.info && !app.datasets.length}
      <div class="pointer-events-none absolute inset-x-0 top-4 flex justify-center">
        <div class="pointer-events-auto flex items-center gap-3 rounded-lg border border-line bg-panel/95 px-4 py-2 shadow-sm">
          <span class="text-muted">Add a CSV or spreadsheet of localities to plot it.</span>
          <button class="btn-primary" onclick={addData}>Add data</button>
        </div>
      </div>
    {/if}

    {#if app.busy}
      <div class="absolute right-3 top-3 text-muted" aria-label="Drawing map">
        <LoaderCircle size={18} class="animate-spin" />
      </div>
    {/if}
  </main>

  <div class="col-span-2">
    <StatusBar />
  </div>
</div>

{#if importing}
  <ColumnMapper path={importing.path} initial={importing.preview} onClose={() => (importing = null)} />
{/if}

{#if exporting}
  <ExportDialog onClose={() => (exporting = false)} />
{/if}
