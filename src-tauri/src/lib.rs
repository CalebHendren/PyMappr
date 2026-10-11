//! Tauri commands: thin wrappers over `mappr-core`.

use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};

use mappr_core::basemap::Basemap;
use mappr_core::export::{self, Format};
use mappr_core::projection::{ProjectionSpec, projection_names};
use mappr_core::render::{self, RenderRequest, RenderedMap};
use mappr_core::table::{self, ColumnMapping, Dataset, Table};
use serde::{Deserialize, Serialize};
use tauri::{Manager, State};

type CmdResult<T> = Result<T, String>;

fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}

struct AppState {
    basemap: RwLock<Option<Arc<Basemap>>>,
    settings_file: PathBuf,
}

#[derive(Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Settings {
    data_dir: Option<PathBuf>,
}

impl AppState {
    fn basemap(&self) -> CmdResult<Arc<Basemap>> {
        self.basemap
            .read()
            .unwrap()
            .clone()
            .ok_or_else(|| "Choose the folder holding the Natural Earth shapefiles first.".to_string())
    }
}

/// Where to look for map data when none is saved: `RUSTYMAPPR_DATA`, then a
/// PyMappr checkout beside this one (which has already downloaded it).
fn default_data_dirs() -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    if let Ok(dir) = std::env::var("RUSTYMAPPR_DATA") {
        dirs.push(PathBuf::from(dir));
    }
    dirs.push(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../PyMappr/data/shapes"));
    dirs
}

/// Accept either the `data/shapes` folder itself or a folder above it.
fn resolve_data_dir(dir: &Path) -> Option<PathBuf> {
    [dir.to_path_buf(), dir.join("shapes"), dir.join("data").join("shapes")]
        .into_iter()
        .find(|d| Basemap::looks_valid(d))
        .map(|d| d.canonicalize().unwrap_or(d))
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AppInfo {
    version: &'static str,
    data_dir: Option<String>,
    projections: Vec<&'static str>,
}

#[tauri::command]
fn app_info(state: State<AppState>) -> AppInfo {
    AppInfo {
        version: env!("CARGO_PKG_VERSION"),
        data_dir: state.basemap.read().unwrap().as_ref().map(|b| b.data_dir().display().to_string()),
        projections: projection_names(),
    }
}

#[tauri::command]
fn set_data_dir(state: State<AppState>, path: String) -> CmdResult<String> {
    let dir = resolve_data_dir(Path::new(&path)).ok_or_else(|| {
        format!("No Natural Earth shapefiles in {path}. Pick PyMappr's data\\shapes folder.")
    })?;
    let settings = Settings { data_dir: Some(dir.clone()) };
    if let Some(parent) = state.settings_file.parent() {
        std::fs::create_dir_all(parent).map_err(err)?;
    }
    std::fs::write(&state.settings_file, serde_json::to_string_pretty(&settings).map_err(err)?).map_err(err)?;
    *state.basemap.write().unwrap() = Some(Arc::new(Basemap::new(&dir)));
    Ok(dir.display().to_string())
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct TablePreview {
    file_name: String,
    sheets: Vec<String>,
    header_row: bool,
    headers: Vec<String>,
    preview: Vec<Vec<String>>,
    row_count: usize,
    mapping: Option<ColumnMapping>,
    mapping_error: Option<String>,
}

fn file_name(path: &Path) -> String {
    path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default()
}

/// Read a table for the column mapper. With `header_row` unset, the first
/// row is taken as headers unless it looks like data.
#[tauri::command]
async fn inspect_table(path: String, header_row: Option<bool>, sheet: Option<String>) -> CmdResult<TablePreview> {
    tauri::async_runtime::spawn_blocking(move || {
        let path = PathBuf::from(path);
        let sheets = table::list_sheets(&path).map_err(err)?;
        let mut headers = header_row.unwrap_or(true);
        let mut t: Table = table::read_table(&path, headers, sheet.as_deref()).map_err(err)?;
        if header_row.is_none() && table::headers_look_like_data(&t) {
            headers = false;
            t = table::read_table(&path, false, sheet.as_deref()).map_err(err)?;
        }
        let (mapping, mapping_error) = match table::guess_mapping(&t) {
            Ok(mut m) => {
                m.header_row = headers;
                m.use_headers = headers;
                (Some(m), None)
            }
            Err(e) => (None, Some(e.to_string())),
        };
        Ok(TablePreview {
            file_name: file_name(&path),
            sheets,
            header_row: headers,
            preview: t.rows.iter().take(8).cloned().collect(),
            row_count: t.rows.len(),
            headers: t.headers,
            mapping,
            mapping_error,
        })
    })
    .await
    .map_err(err)?
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct LoadedDataset {
    file_name: String,
    #[serde(flatten)]
    dataset: Dataset,
}

#[tauri::command]
async fn load_dataset(path: String, sheet: Option<String>, mapping: ColumnMapping) -> CmdResult<LoadedDataset> {
    tauri::async_runtime::spawn_blocking(move || {
        let path = PathBuf::from(path);
        let t = table::read_table(&path, mapping.header_row, sheet.as_deref()).map_err(err)?;
        let dataset = table::build_dataset(&t, &mapping).map_err(err)?;
        Ok(LoadedDataset { file_name: file_name(&path), dataset })
    })
    .await
    .map_err(err)?
}

#[tauri::command]
async fn render_map(state: State<'_, AppState>, request: RenderRequest) -> CmdResult<RenderedMap> {
    let basemap = state.basemap()?;
    tauri::async_runtime::spawn_blocking(move || render::render(&basemap, &request).map_err(err))
        .await
        .map_err(err)?
}

#[tauri::command]
fn project_points(projection: ProjectionSpec, points: Vec<[f64; 2]>) -> CmdResult<Vec<Option<[f64; 2]>>> {
    render::project_points(&projection, &points).map_err(err)
}

#[tauri::command]
fn unproject(projection: ProjectionSpec, x: f64, y: f64) -> CmdResult<Option<[f64; 2]>> {
    render::unproject(&projection, x, y).map_err(err)
}

#[tauri::command]
async fn export_map(svg: String, format: Format, width_px: u32, dpi: f64, path: String) -> CmdResult<()> {
    tauri::async_runtime::spawn_blocking(move || {
        export::export(&svg, format, width_px, dpi, Path::new(&path)).map_err(err)
    })
    .await
    .map_err(err)?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let settings_file = app.path().app_config_dir()?.join("settings.json");
            let saved: Settings = std::fs::read_to_string(&settings_file)
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok())
                .unwrap_or_default();
            let dir = saved
                .data_dir
                .into_iter()
                .chain(default_data_dirs())
                .find_map(|d| resolve_data_dir(&d));
            app.manage(AppState {
                basemap: RwLock::new(dir.map(|d| Arc::new(Basemap::new(d)))),
                settings_file,
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            app_info,
            set_data_dir,
            inspect_table,
            load_dataset,
            render_map,
            project_points,
            unproject,
            export_map
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
