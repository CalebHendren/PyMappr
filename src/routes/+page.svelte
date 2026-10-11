<script lang="ts">
  import { onMount } from "svelte";
  import { api, confirmDialog, inTauri, openUrl, pickFile, pickFolder, type TablePreview } from "$lib/api";
  import type { ManualParse } from "$lib/api-docs";
  import { applyCombine, editManualEntry, manualEntry, manualStyle, type ManualResult } from "$lib/datasets";
  import { documents } from "$lib/documents.svelte";
  import { exportFigure, mapPng } from "$lib/exporting.svelte";
  import { editorPaletteOffset, editorRows, paletteFor, symbology } from "$lib/symbology";
  import { store } from "$lib/store.svelte";
  import CodeExport from "$lib/components/code/CodeExport.svelte";
  import CombineColumns from "$lib/components/dialogs/CombineColumns.svelte";
  import FilterBar from "$lib/components/dialogs/FilterBar.svelte";
  import LegendEditor from "$lib/components/dialogs/LegendEditor.svelte";
  import ManualEntry from "$lib/components/dialogs/ManualEntry.svelte";
  import Presets from "$lib/components/dialogs/Presets.svelte";
  import ProjectsDialog from "$lib/components/dialogs/ProjectsDialog.svelte";
  import NameDialog from "$lib/components/NameDialog.svelte";
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

  let projectsOpen = $state(false);
  let manual = $state<{ index: number | null } | null>(null);
  let combining = $state(false);
  let editingRows = $state(false);
  let codeOpen = $state(false);
  let asking = $state<{ title: string; initial: string; resolve: (name: string | null) => void } | null>(null);

  // PyMappr's symbology: point styles, legend rows, warnings.
  const sym = $derived(symbology(store.doc, store.filter));
  $effect(() => {
    if (sym.warning) store.status = sym.warning;
  });

  documents.askName = (title, initial) => new Promise((resolve) => (asking = { title, initial, resolve }));

  onMount(async () => {
    await store.init();
    await documents.restoreSession();
    if (store.info && !store.info.dataDir) downloading = true;
    // The automatic update check: once a day, silent when offline.
    setTimeout(() => checkUpdates(false), 2000);
    // Save the session on the way out, as PyMappr does.
    if (inTauri) {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const win = getCurrentWindow();
      win.onCloseRequested(async (e) => {
        e.preventDefault();
        await documents.saveSession();
        await win.destroy();
      });
    } else {
      addEventListener("beforeunload", () => documents.saveSession());
    }
  });

  async function exit() {
    await documents.saveSession();
    if (inTauri) {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().destroy();
    }
  }

  function acceptManual(result: ManualResult, parsed: ManualParse) {
    const index = manual?.index ?? null;
    manual = null;
    if (index !== null) {
      store.doc.datasets[index] = editManualEntry(store.doc.datasets[index], result, parsed);
      store.projected[index] = { key: "", xy: [] };
      store.setStatus(`Updated ${result.legend}.`);
    } else {
      store.addEntry(manualEntry(result, parsed));
      store.setStatus(`Added ${parsed.rows.length} typed-in points.`);
    }
    if (parsed.skipped.length)
      notices = [...notices, { title: "Some lines skipped", lines: parsed.skipped.slice(0, 12), more: Math.max(0, parsed.skipped.length - 12) }];
  }

  function acceptCombine(labels: string[], separator: string) {
    combining = false;
    const i = store.doc.active;
    if (i === null) return;
    const r = applyCombine(store.doc.datasets[i], labels, separator);
    store.doc.datasets[i] = r.entry;
    store.filter = null;
    store.setStatus(r.status);
  }

  /** The map as the AI check may see it: a PNG of the current figure. */
  const mapImage = () => mapPng(sym);

  function codeInput() {
    store.syncViewToDoc();
    const fig = exportFigure(parseFloat(store.doc.map.export_width) || null);
    return {
      state: $state.snapshot(store.doc),
      figureSize: fig ? ([fig.w / 72, fig.h / 72] as [number, number]) : null,
      renderer: null,
      projectName: store.projectName,
    };
  }

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

  const menus: Menu[] = $derived([
    {
      label: "File",
      items: [
        { label: "New project", shortcut: "Ctrl+N", action: () => documents.newProject() },
        { label: "Projects…", shortcut: "Ctrl+P", action: () => (projectsOpen = true) },
        { label: "Save project", shortcut: "Ctrl+S", action: () => documents.save() },
        { label: "Save project as…", action: () => documents.saveAs() },
        { separator: true },
        { label: "Import project…", action: () => documents.importProject() },
        { label: "Export project…", action: () => documents.exportProject() },
        { label: "Set projects folder…", action: () => documents.setProjectsFolder() },
        { separator: true },
        { label: "Add data file…", shortcut: "Ctrl+O", action: addData },
        { label: "Manual entry…", shortcut: "Ctrl+M", action: () => (manual = { index: null }) },
        { separator: true },
        { label: "Save map as…", shortcut: "Ctrl+E", action: () => (saving = true), disabled: !store.svgEl },
        { label: "Export map as code (Python/R)…", action: () => (codeOpen = true), disabled: !store.doc.datasets.length },
        { separator: true },
        { label: "Download map data…", action: () => (downloading = true) },
        { separator: true },
        { label: "Exit", action: exit },
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
      n: () => documents.newProject(),
      p: () => (projectsOpen = true),
      s: () => documents.save(),
      m: () => (manual = { index: null }),
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
        onManualEntry={() => (manual = { index: null })}
        onEditManual={(i) => (manual = { index: i })}
        onRemove={removeDataset}
        onCombine={() => (combining = true)}
      >
        {#snippet presets()}
          <Presets
            project={store.doc}
            appVersion={store.info?.version ?? "0.0.0"}
            onapply={(r) => {
              store.doc = r.state;
              if (!r.keepView) store.zoomToData();
              store.setStatus(r.status);
            }}
            onstatus={(m) => store.setStatus(m)}
          />
        {/snippet}
      </DataTab>
    {/snippet}
    {#snippet legend()}<LegendTab onCustomize={() => (editingRows = true)} />{/snippet}
    {#snippet map()}<MapTab onSaveMap={() => (saving = true)} onExportCode={() => (codeOpen = true)} />{/snippet}
    {#snippet layers()}<LayersTab onChooseDataDir={chooseDataDir} onDownloadData={() => (downloading = true)} />{/snippet}
    {#snippet labels()}<LabelsTab />{/snippet}
  </Sidebar>

  <main class="relative flex min-w-0 flex-col bg-paper">
    <div class="relative min-h-0 flex-1"><MapView {sym} /></div>
    {#if store.active}
      <FilterBar entry={store.active} datasetIndex={store.doc.active} onchange={(f) => (store.filter = f)} />
    {/if}
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
  <ExportDialog {sym} onClose={() => (saving = false)} />
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

{#if projectsOpen}
  <ProjectsDialog
    onopen={(path, changes) => {
      projectsOpen = false;
      documents.followChanges(changes);
      documents.open(path);
    }}
    onClose={(changes) => {
      projectsOpen = false;
      documents.followChanges(changes);
    }}
  />
{/if}

{#if manual}
  {@const editing = manual.index !== null ? store.doc.datasets[manual.index] : null}
  <ManualEntry
    legend={editing?.manual ? editing.name : ""}
    text={editing?.manual?.text ?? ""}
    order={(editing?.manual?.order as "lat,lon" | "lon,lat") ?? "lat,lon"}
    style={editing ? manualStyle(editing) : undefined}
    onaccept={acceptManual}
    onClose={() => (manual = null)}
  />
{/if}

{#if combining && store.active}
  <CombineColumns entry={store.active} onaccept={acceptCombine} onClose={() => (combining = false)} />
{/if}

{#if editingRows && store.active && store.doc.active !== null}
  {@const i = store.doc.active}
  <LegendEditor
    rows={editorRows(store.active, sym.options, paletteFor(store.doc.map.palette), editorPaletteOffset(store.doc, i))}
    overrides={store.active.legend_overrides}
    onchange={(o) => (store.doc.datasets[i].legend_overrides = o)}
    onreorder={(o) => {
      store.doc.legend.order = "manual";
      store.doc.datasets[i].legend_overrides = o;
    }}
    onClose={() => (editingRows = false)}
  />
{/if}

{#if codeOpen}
  <CodeExport input={codeInput()} getMapImage={mapImage} onClose={() => (codeOpen = false)} />
{/if}

{#if asking}
  <NameDialog
    title={asking.title}
    initial={asking.initial}
    onDone={(name) => {
      asking?.resolve(name);
      asking = null;
    }}
  />
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
