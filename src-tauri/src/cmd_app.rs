//! App-level commands: settings, map data folder, table import, image
//! export, background jobs.

use std::path::{Path, PathBuf};
use std::sync::Arc;

use mappr_core::basemap::Basemap;
use mappr_core::export::{self, Format};
use mappr_core::projection::projection_names;
use mappr_core::table::{self, ColumnMapping, Dataset, Table};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::core::{CmdResult, Core, err, ok, parse};

pub fn dispatch(core: &Arc<Core>, cmd: &str, args: &Value) -> Option<CmdResult> {
    Some(match cmd {
        "app_info" => app_info(core),
        "settings_get" => ok(core.settings()),
        "settings_set" => settings_set(core, args),
        "set_data_dir" => set_data_dir(core, args),
        "inspect_table" => inspect_table(args),
        "load_dataset" => load_dataset(args),
        "export_map" => export_map(args),
        "data_status" => data_status(core, args),
        "data_download" => data_download(core, args),
        "check_updates" => check_updates(core, args),
        #[cfg(feature = "devbridge")]
        "parity_write" => parity_write(args),
        "job_status" => job_status(core, args),
        "job_cancel" => job_cancel(core, args),
        _ => return None,
    })
}

/// Pick the map data folder at startup: the saved one, `RUSTYMAPPR_DATA`,
/// RustyMappr's own download folder, then a PyMappr checkout beside this one.
pub fn init(core: &Core) {
    let saved = core.settings().get("dataDir").and_then(|v| v.as_str()).map(PathBuf::from);
    let mut candidates: Vec<PathBuf> = saved.into_iter().collect();
    if let Ok(dir) = std::env::var("RUSTYMAPPR_DATA") {
        candidates.push(PathBuf::from(dir));
    }
    candidates.push(core.default_data_dir.clone());
    candidates.push(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../PyMappr/data"));
    if let Some(dir) = candidates.iter().find_map(|d| resolve_data_dir(d)) {
        *core.basemap.write().unwrap() = Some(Arc::new(Basemap::new(dir)));
    }
}

/// Accept the `data` folder, its `shapes` folder, or a folder above `data`.
/// Returns the `data` folder (the one holding `shapes`).
pub fn resolve_data_dir(dir: &Path) -> Option<PathBuf> {
    let candidates = [dir.to_path_buf(), dir.join("data")];
    let shapes_parent = dir.parent().filter(|_| dir.file_name().is_some_and(|n| n == "shapes"));
    candidates
        .into_iter()
        .chain(shapes_parent.map(Path::to_path_buf))
        .find(|d| Basemap::looks_valid(&d.join("shapes")))
        .map(|d| d.canonicalize().unwrap_or(d))
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AppInfo {
    version: &'static str,
    data_dir: Option<String>,
    default_data_dir: String,
    config_dir: String,
    projections: Vec<&'static str>,
}

fn app_info(core: &Arc<Core>) -> CmdResult {
    ok(AppInfo {
        version: env!("CARGO_PKG_VERSION"),
        data_dir: core.basemap.read().unwrap().as_ref().map(|b| b.data_dir().display().to_string()),
        default_data_dir: core.default_data_dir.display().to_string(),
        config_dir: core.config_dir.display().to_string(),
        projections: projection_names(),
    })
}

fn settings_set(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        patch: Map<String, Value>,
    }
    let a: A = parse(args)?;
    ok(core.update_settings(&a.patch)?)
}

fn set_data_dir(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        path: String,
    }
    let a: A = parse(args)?;
    let dir = resolve_data_dir(Path::new(&a.path)).ok_or_else(|| {
        format!("No Natural Earth shapefiles in {}. Pick a data folder with a 'shapes' folder inside.", a.path)
    })?;
    use_data_dir(core, &dir);
    ok(dir.display().to_string())
}

/// Switch to a data folder and remember it.
pub fn use_data_dir(core: &Core, dir: &Path) {
    let _ = core.update_settings(&Map::from_iter([("dataDir".to_string(), json!(dir.display().to_string()))]));
    *core.basemap.write().unwrap() = Some(Arc::new(Basemap::new(dir)));
}

#[derive(Deserialize)]
struct DirArg {
    /// The data folder; RustyMappr's own download folder when absent.
    dir: Option<String>,
}

fn data_status(core: &Arc<Core>, args: &Value) -> CmdResult {
    let a: DirArg = parse(args)?;
    let dir = a.dir.map(PathBuf::from).unwrap_or_else(|| core.default_data_dir.clone());
    ok(crate::downloader::status(&dir))
}

fn data_download(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        dir: Option<String>,
        rasters: bool,
        extras: bool,
    }
    let a: A = parse(args)?;
    let dir = a.dir.map(PathBuf::from).unwrap_or_else(|| core.default_data_dir.clone());
    let opts = crate::downloader::Options { rasters: a.rasters, extras: a.extras };
    ok(crate::downloader::start(core, dir, opts))
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
fn inspect_table(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct A {
        path: String,
        header_row: Option<bool>,
        sheet: Option<String>,
    }
    let a: A = parse(args)?;
    let path = PathBuf::from(a.path);
    let sheets = table::list_sheets(&path).map_err(err)?;
    let mut headers = a.header_row.unwrap_or(true);
    let mut t: Table = table::read_table(&path, headers, a.sheet.as_deref()).map_err(err)?;
    if a.header_row.is_none() && table::headers_look_like_data(&t) {
        headers = false;
        t = table::read_table(&path, false, a.sheet.as_deref()).map_err(err)?;
    }
    let (mapping, mapping_error) = match table::guess_mapping(&t) {
        Ok(mut m) => {
            m.header_row = headers;
            m.use_headers = headers;
            (Some(m), None)
        }
        Err(e) => (None, Some(e.to_string())),
    };
    ok(TablePreview {
        file_name: file_name(&path),
        sheets,
        header_row: headers,
        preview: t.rows.iter().take(8).cloned().collect(),
        row_count: t.rows.len(),
        headers: t.headers,
        mapping,
        mapping_error,
    })
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct LoadedDataset {
    file_name: String,
    #[serde(flatten)]
    dataset: Dataset,
    /// Notes on points far from the rest (likely sign errors).
    far_points: Vec<String>,
}

fn load_dataset(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        path: String,
        sheet: Option<String>,
        mapping: ColumnMapping,
    }
    let a: A = parse(args)?;
    let path = PathBuf::from(a.path);
    let t = table::read_table(&path, a.mapping.header_row, a.sheet.as_deref()).map_err(err)?;
    let dataset = table::build_dataset(&t, &a.mapping).map_err(err)?;
    let far_points = table::far_points(&dataset);
    ok(LoadedDataset { file_name: file_name(&path), dataset, far_points })
}

fn export_map(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct A {
        svg: String,
        format: Format,
        width_px: u32,
        dpi: f64,
        path: String,
    }
    let a: A = parse(args)?;
    export::export(&a.svg, a.format, a.width_px, a.dpi, Path::new(&a.path)).map_err(err)?;
    ok(())
}

fn job_status(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        id: u64,
    }
    let a: A = parse(args)?;
    ok(core.jobs.status(a.id))
}

fn job_cancel(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        id: u64,
    }
    let a: A = parse(args)?;
    core.jobs.cancel(a.id);
    ok(())
}

/// Dev only: write the parity check's files for one rendering (see
/// scripts/parity_compare.py): the SVG, its PNG at the figure's pixel size
/// through the export renderer, and the geometry the page measured.
#[cfg(feature = "devbridge")]
fn parity_write(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct A {
        dir: String,
        svg: String,
        geometry: Value,
        width_px: u32,
    }
    let a: A = parse(args)?;
    let dir = PathBuf::from(&a.dir);
    std::fs::create_dir_all(&dir).map_err(err)?;
    std::fs::write(dir.join("screen.svg"), &a.svg).map_err(err)?;
    std::fs::write(dir.join("geometry.json"), serde_json::to_string_pretty(&a.geometry).map_err(err)?).map_err(err)?;
    export::export(&a.svg, Format::Png, a.width_px, 100.0, &dir.join("screen.png")).map_err(err)?;
    ok(dir.display().to_string())
}

const RELEASES: &str = "https://api.github.com/repos/CalebHendren/RustyMappr/releases/latest";
pub const RELEASES_PAGE: &str = "https://github.com/CalebHendren/RustyMappr/releases";

/// Ask GitHub for the latest release, at most once a day unless `force`.
/// Returns `{checked, latest, newer, url}`; offline failures are an error
/// only when forced (an automatic check stays quiet, as in PyMappr).
fn check_updates(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        force: bool,
    }
    let a: A = parse(args)?;
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let last = core.settings().get("updateCheckedAt").and_then(Value::as_u64).unwrap_or(0);
    if !a.force && now.saturating_sub(last) < 24 * 3600 {
        return ok(json!({ "checked": false }));
    }
    core.update_settings(&Map::from_iter([("updateCheckedAt".to_string(), json!(now))]))?;
    let fetched = reqwest::blocking::Client::builder()
        .user_agent("RustyMappr-update-check")
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .and_then(|c| c.get(RELEASES).send())
        .and_then(|r| r.error_for_status())
        .and_then(|r| r.json::<Value>());
    let release = match fetched {
        Ok(r) => r,
        Err(e) if a.force => return Err(format!("Could not check for updates: {e}")),
        Err(_) => return ok(json!({ "checked": false })),
    };
    let latest = release["tag_name"].as_str().unwrap_or("").trim_start_matches('v').to_string();
    let newer = is_newer(&latest, env!("CARGO_PKG_VERSION"));
    let url = release["html_url"].as_str().unwrap_or(RELEASES_PAGE).to_string();
    ok(json!({ "checked": true, "latest": latest, "newer": newer, "url": url }))
}

/// Whether version `a` (MAJOR.MINOR.PATCH) is newer than `b`.
pub fn is_newer(a: &str, b: &str) -> bool {
    let parts = |v: &str| v.split('.').map(|p| p.parse::<u64>().unwrap_or(0)).collect::<Vec<_>>();
    parts(a) > parts(b)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compares_versions_numerically() {
        assert!(is_newer("0.10.0", "0.9.9"));
        assert!(is_newer("1.0.0", "0.2.0"));
        assert!(!is_newer("0.2.0", "0.2.0"));
        assert!(!is_newer("", "0.2.0"));
    }
}
