<script lang="ts">
  import { onMount } from "svelte";
  import { api, confirmDialog, openUrl, pickFile, pickFolder, type TablePreview } from "$lib/api";
  import { basicStyles } from "$lib/points";
  import { store } from "$lib/store.svelte";
  import ColumnMapper from "$lib/components/ColumnMapper.svelte";
  import DataDownload from "$lib/components/DataDownload.svelte";
  import DataTab from "$lib/components/DataTab.svelte";
  import ExportDialog from "$lib/components/ExportDialog.svelte";
  import LabelsTab from "$lib/components/LabelsTab.svelte";
  import LayersTab from "$lib/components/LayersTab.svelte";
  import LegendTab from "$lib/components/LegendTab.svelte";
  import MapTab from "$lib/components/MapTab.svelte";
  import MenuBar, { type Menu } from "$lib/components/MenuBar.svelte";
  import Modal from "$lib/components/Modal.svelte";
  import Sidebar from "$lib/components/Sidebar.svelte";
  import StatusBar from "$lib/components/StatusBar.svelte";
  import Toolbar from "$lib/components/Toolbar.svelte";
  import MapView from "$lib/components/map/MapView.svelte";

  const KOFI = "https://ko-fi.com/calebhendren";

  let importing = $state<{ path: string; preview: TablePreview } | null>(null);
  let saving = $state(false);
  let downloading = $state(false);
  type Notice = { title: string; lines: string[]; more: number; hint?: string };
  let notices = $state<Notice[]>([]);
  const notice = $derived(notices[0] ?? null);
  let about = $state(false);

  const styles = $derived(basicStyles(store.doc));

  onMount(async () => {
    await store.init();
    if (store.info && !store.info.dataDir) downloading = true;
    // The automatic update check: once a day, silent when offline.
    setTimeout(() => checkUpdates(false), 2000);
  });

  async function addData() {
    const path = await pickFile("Add data file", [
      { name: "All supported", extensions: ["csv", "tsv", "txt", "xlsx", "xlsm", "xls", "ods"] },
      { name: "All files", extensions: ["*"] },
    ]);
    if (!path) return;
    try {
      importing = { path, preview: await api.inspectTable(path, null, null) };
    } catch (e) {
      store.fail(e);
    }
  }

  /** Messages after an import, shown one after another. */
  function showImportNotes(far: string[], skipped: string[]) {
    const next: Notice[] = [];
    if (skipped.length)
      next.push({
        title: "Some rows skipped",
        lines: skipped.slice(0, 12),
        more: Math.max(0, skipped.length - 12),
        hint: "These rows had no usable coordinates. The rest were added.",
      });
    if (far.length)
      next.push({
        title: "Points far from the rest",
        lines: far.slice(0, 12),
        more: Math.max(0, far.length - 12),
        hint: "A point far from all the others is often a coordinate missing its minus sign or hemisphere letter. The points are on the map; check them in your file.",
      });
    notices = [...notices, ...next];
  }

  async function chooseDataDir() {
    const dir = await pickFolder("Folder with the map data (holding 'shapes')");
    if (!dir) return;
    try {
      await api.setDataDir(dir);
      await store.init();
      store.view = null;
      downloading = false;
      store.setStatus("Using the map data in " + dir);
    } catch (e) {
      store.fail(e);
    }
  }

  async function checkUpdates(force: boolean) {
    try {
      const r = await api.checkUpdates(force);
      if (r.checked && r.newer && r.url) {
        if (await confirmDialog(`RustyMappr ${r.latest} is available (you have ${store.info?.version}). Open the download page?`)) openUrl(r.url);
      } else if (force && r.checked) {
        store.setStatus(`RustyMappr is up to date (${store.info?.version}).`);
      }
    } catch (e) {
      if (force) store.fail(e);
    }
  }

  async function removeDataset(index: number) {
    const ds = store.doc.datasets[index];
    if (ds && (await confirmDialog(`Remove "${ds.name}" from the map?`))) store.removeDataset(index);
  }

  const soon = (what: string) => () => store.setStatus(`${what} is not ready yet in this build.`);

  const menus: Menu[] = $derived([
    {
      label: "File",
      items: [
        { label: "New project", shortcut: "Ctrl+N", action: soon("New project") },
        { label: "Projects…", shortcut: "Ctrl+P", action: soon("The projects manager") },
        { label: "Save project", shortcut: "Ctrl+S", action: soon("Saving projects") },
        { label: "Save project as…", action: soon("Saving projects") },
        { separator: true },
        { label: "Import project…", action: soon("Importing projects") },
        { label: "Export project…", action: soon("Exporting projects") },
        { label: "Set projects folder…", action: soon("The projects folder") },
        { separator: true },
        { label: "Add data file…", shortcut: "Ctrl+O", action: addData },
        { label: "Manual entry…", shortcut: "Ctrl+M", action: soon("Manual entry") },
        { separator: true },
        { label: "Save map as…", shortcut: "Ctrl+E", action: () => (saving = true), disabled: !store.svgEl },
        { label: "Export map as code (Python/R)…", action: soon("Code export") },
        { separator: true },
        { label: "Download map data…", action: () => (downloading = true) },
      ],
    },
    {
      label: "View",
      items: [
        { label: "Light theme", checked: store.theme === "light", action: () => store.setTheme("light") },
        { label: "Dark theme", checked: store.theme === "dark", action: () => store.setTheme("dark") },
        { separator: true },
        { label: "Show advanced options", checked: store.advanced, action: () => store.setAdvanced(!store.advanced) },
        { separator: true },
        { label: "Zoom in", shortcut: "Ctrl +", action: () => store.zoomBy(1.3) },
        { label: "Zoom out", shortcut: "Ctrl −", action: () => store.zoomBy(1 / 1.3) },
        { label: "Zoom to data", action: () => store.zoomToData() },
        { label: "Home", action: () => store.home() },
      ],
    },
    {
      label: "Help",
      items: [
        { label: "About RustyMappr", action: () => (about = true) },
        { label: "Check for updates…", action: () => checkUpdates(true) },
        { label: "Support me on Ko-fi", action: () => openUrl(KOFI) },
      ],
    },
  ]);

  function onKey(e: KeyboardEvent) {
    const target = e.target as HTMLElement;
    if (target.closest("input, textarea, select, dialog")) return;
    if (!e.ctrlKey && !e.metaKey) return;
    const key = e.key.toLowerCase();
    const actions: Record<string, () => void> = {
      o: addData,
      e: () => store.svgEl && (saving = true),
      "=": () => store.zoomBy(1.3),
      "+": () => store.zoomBy(1.3),
      "-": () => store.zoomBy(1 / 1.3),
      n: soon("New project"),
      p: soon("The projects manager"),
      s: soon("Saving projects"),
      m: soon("Manual entry"),
    };
    if (actions[key]) {
      e.preventDefault();
      actions[key]();
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="grid h-screen grid-cols-[320px_1fr] grid-rows-[auto_auto_1fr_auto]">
  <div class="col-span-2"><MenuBar {menus} /></div>
  <div class="col-span-2"><Toolbar onAddData={addData} onSaveMap={() => (saving = true)} /></div>

  <Sidebar onKofi={() => openUrl(KOFI)} onCheckUpdates={() => checkUpdates(true)}>
    {#snippet data()}
      <DataTab
        onAddData={addData}
        onManualEntry={soon("Manual entry")}
        onEditManual={soon("Editing typed-in data")}
        onRemove={removeDataset}
        onCombine={soon("Combining columns")}
      />
    {/snippet}
    {#snippet legend()}<LegendTab onCustomize={soon("The legend rows editor")} />{/snippet}
    {#snippet map()}<MapTab onSaveMap={() => (saving = true)} onExportCode={soon("Code export")} />{/snippet}
    {#snippet layers()}<LayersTab onChooseDataDir={chooseDataDir} onDownloadData={() => (downloading = true)} />{/snippet}
    {#snippet labels()}<LabelsTab />{/snippet}
  </Sidebar>

  <main class="relative min-w-0 bg-paper">
    <MapView {styles} />
    {#if store.info?.dataDir && !store.doc.datasets.length}
      <div class="pointer-events-none absolute inset-x-0 top-4 flex justify-center">
        <div class="pointer-events-auto flex items-center gap-3 rounded-lg border border-line bg-panel/95 px-4 py-2 shadow-sm">
          <span class="text-muted">Add a CSV or spreadsheet of localities to plot it.</span>
          <button class="btn-primary" onclick={addData}>Add data</button>
        </div>
      </div>
    {/if}
  </main>

  <div class="col-span-2"><StatusBar /></div>
</div>

{#if importing}
  <ColumnMapper path={importing.path} initial={importing.preview} onClose={() => (importing = null)} onFarPoints={showImportNotes} />
{/if}

{#if saving}
  <ExportDialog {styles} onClose={() => (saving = false)} />
{/if}

{#if downloading}
  <DataDownload required={!store.info?.dataDir} onClose={() => (downloading = false)} onChooseFolder={chooseDataDir} />
{/if}

{#if notice}
  <Modal title={notice.title} onClose={() => (notices = notices.slice(1))}>
    <ul class="max-w-2xl list-disc space-y-1 pl-5">
      {#each notice.lines as line, i (i)}<li>{line}</li>{/each}
    </ul>
    {#if notice.more}<p class="mt-2 text-muted">…and {notice.more} more.</p>{/if}
    {#if notice.hint}<p class="mt-3 text-muted">{notice.hint}</p>{/if}
    {#snippet actions()}
      <button class="btn-primary" onclick={() => (notices = notices.slice(1))}>OK</button>
    {/snippet}
  </Modal>
{/if}

{#if about}
  <Modal title="About RustyMappr" onClose={() => (about = false)}>
    <div class="max-w-lg space-y-2">
      <p>RustyMappr {store.info?.version}: distribution maps from locality tables, a Rust port of PyMappr.</p>
      <p class="text-muted">
        Base maps from Natural Earth (public domain). Optional overlays: RESOLVE Ecoregions 2017, Conservation International
        Biodiversity Hotspots, WWF/TNC Marine Ecoregions (CC-BY). District boundaries outside the US from geoBoundaries (each
        country under its own open licence).
      </p>
      <button class="btn border border-line" onclick={() => openUrl(KOFI)}>Support me on Ko-fi</button>
    </div>
    {#snippet actions()}<button class="btn-primary" onclick={() => (about = false)}>Close</button>{/snippet}
  </Modal>
{/if}
