//! Commands for projects, presets and session files, and manual point
//! entry. The file handling follows PyMappr's pymappr/files/projects.py and
//! presets.py; the documents themselves are read and written by the front
//! end (src/lib/project.ts, presets.ts), which owns the format.

use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::UNIX_EPOCH;

use mappr_core::coords::{parse_latitude, parse_longitude};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::core::{CmdResult, Core, err, ok, parse, write_text};

pub const PROJECT_EXTENSION: &str = ".pymappr";
pub const PRESET_EXTENSION: &str = ".pymappr-preset";
const PROJECT_FORMAT: &str = "pymappr-project";
const PRESET_FORMAT: &str = "pymappr-preset";
const FORMAT_VERSION: i64 = 1;
/// In the presets folder once the user deleted the built-in preset.
const BUILT_IN_DELETED: &str = ".built-in-deleted";
/// The settings key for a chosen projects folder.
const PROJECTS_DIR_KEY: &str = "projectsDir";

pub fn dispatch(core: &Arc<Core>, cmd: &str, args: &Value) -> Option<CmdResult> {
    Some(match cmd {
        "projects_dir" => ok(projects_dir(core).display().to_string()),
        "projects_dir_set" => projects_dir_set(core, args),
        "projects_list" => projects_list(core, args),
        "project_path" => named_path(&projects_dir(core), args, PROJECT_EXTENSION),
        "project_read" => read_file(args),
        "project_write" => write_file(args),
        "project_rename" => project_rename(args),
        "project_delete" => delete_file(args),
        "project_import" => project_import(core, args),
        "session_path" => ok(session_path(&core.config_dir).display().to_string()),
        "session_read" => session_read(core),
        "session_write" => session_write(core, args),
        "presets_dir" => ok(presets_dir(&core.config_dir).display().to_string()),
        "presets_list" => ok(list_presets(&presets_dir(&core.config_dir))),
        "preset_path" => named_path(&presets_dir(&core.config_dir), args, PRESET_EXTENSION),
        "preset_read" => preset_read(args),
        "preset_write" => write_file(args),
        "preset_delete" => delete_file(args),
        "presets_builtin_deleted" => ok(presets_dir(&core.config_dir).join(BUILT_IN_DELETED).exists()),
        "presets_delete_builtin" => delete_built_in(&presets_dir(&core.config_dir)),
        "path_exists" => path_exists(args),
        "parse_manual" => parse_manual(args),
        _ => return None,
    })
}

// ------------------------------------------------------------------ names

const RESERVED: [&str; 22] = [
    "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9", "lpt1", "lpt2",
    "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
];

/// A filesystem-safe version of a typed name (PyMappr's `safe_filename`).
pub fn safe_filename(name: &str) -> String {
    let cleaned: String =
        name.trim().chars().map(|c| if "<>:\"/\\|?*".contains(c) || (c as u32) < 32 { '_' } else { c }).collect();
    let cleaned = cleaned.trim_matches(|c| c == '.' || c == ' ');
    let cleaned = if cleaned.is_empty() { "Untitled" } else { cleaned };
    let (first, rest) = match cleaned.find('.') {
        Some(i) => (&cleaned[..i], &cleaned[i..]),
        None => (cleaned, ""),
    };
    if RESERVED.contains(&first.trim().to_lowercase().as_str()) {
        format!("{}_{rest}", first.trim_end())
    } else {
        cleaned.to_string()
    }
}

/// Python's `repr` of a string, for messages that quote a name as PyMappr's do.
pub fn py_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') { '"' } else { '\'' };
    let mut out = String::from(quote);
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 32 || c as u32 == 127 => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

fn file_name(path: &Path) -> String {
    path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default()
}

fn file_stem(path: &Path) -> String {
    let name = file_name(path);
    for ext in [PRESET_EXTENSION, PROJECT_EXTENSION] {
        if let Some(stem) = name.strip_suffix(ext) {
            return stem.to_string();
        }
    }
    path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default()
}

/// Whether the file has exactly this extension (".pymappr" is not a
/// ".pymappr-preset", nor the other way round).
fn has_extension(path: &Path, ext: &str) -> bool {
    path.extension().map(|e| format!(".{}", e.to_string_lossy())) == Some(ext.to_string())
}

// -------------------------------------------------------------- directories

/// `Documents\RustyMappr Projects` (the home folder when there is no
/// Documents folder).
pub fn default_projects_dir() -> PathBuf {
    let base = dirs::document_dir().filter(|d| d.is_dir()).or_else(dirs::home_dir).unwrap_or_else(std::env::temp_dir);
    base.join("RustyMappr Projects")
}

/// The projects folder: the chosen one, else the default; created on use,
/// falling back to the default when the chosen one cannot be made.
pub fn projects_dir(core: &Core) -> PathBuf {
    let stored = core.settings().get(PROJECTS_DIR_KEY).and_then(|v| v.as_str()).map(PathBuf::from);
    let folder = stored.filter(|p| !p.as_os_str().is_empty()).unwrap_or_else(default_projects_dir);
    if std::fs::create_dir_all(&folder).is_ok() {
        return folder;
    }
    let fallback = default_projects_dir();
    let _ = std::fs::create_dir_all(&fallback);
    fallback
}

fn projects_dir_set(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        path: String,
    }
    let a: A = parse(args)?;
    let mut patch = Map::new();
    patch.insert(PROJECTS_DIR_KEY.into(), Value::String(a.path));
    core.update_settings(&patch)?;
    ok(projects_dir(core).display().to_string())
}

pub fn presets_dir(config_dir: &Path) -> PathBuf {
    let folder = config_dir.join("Presets");
    let _ = std::fs::create_dir_all(&folder);
    folder
}

pub fn session_path(config_dir: &Path) -> PathBuf {
    config_dir.join(format!("session{PROJECT_EXTENSION}"))
}

// ------------------------------------------------------------------ projects

#[derive(Serialize, Debug, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct ProjectListing {
    /// The file name without `.pymappr`, which is what the dialog shows.
    pub name: String,
    pub path: String,
    /// Last modified, in milliseconds since 1970 (PyMappr's "Last saved").
    pub modified: f64,
}

/// Project files in `folder`, most recently saved first.
pub fn list_projects(folder: &Path) -> Vec<ProjectListing> {
    let Ok(entries) = std::fs::read_dir(folder) else {
        return Vec::new();
    };
    let mut found: Vec<ProjectListing> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_file() && has_extension(p, PROJECT_EXTENSION))
        .map(|p| {
            let modified = std::fs::metadata(&p)
                .and_then(|m| m.modified())
                .ok()
                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                .map(|d| d.as_secs_f64() * 1000.0)
                .unwrap_or(0.0);
            ProjectListing { name: file_stem(&p), path: p.display().to_string(), modified }
        })
        .collect();
    found.sort_by(|a, b| b.modified.total_cmp(&a.modified));
    found
}

fn projects_list(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        folder: Option<String>,
    }
    let a: A = parse(args)?;
    let folder = a.folder.filter(|f| !f.is_empty()).map(PathBuf::from).unwrap_or_else(|| projects_dir(core));
    ok(list_projects(&folder))
}

fn named_path(folder: &Path, args: &Value, ext: &str) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        name: String,
    }
    let a: A = parse(args)?;
    let path = folder.join(format!("{}{ext}", safe_filename(&a.name)));
    ok(json!({ "path": path.display().to_string(), "exists": path.exists() }))
}

#[derive(Deserialize)]
struct PathArg {
    path: String,
}

fn read_file(args: &Value) -> CmdResult {
    let a: PathArg = parse(args)?;
    ok(std::fs::read_to_string(&a.path).map_err(err)?)
}

fn write_file(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        path: String,
        text: String,
    }
    let a: A = parse(args)?;
    write_text(Path::new(&a.path), &a.text)?;
    ok(())
}

fn delete_file(args: &Value) -> CmdResult {
    let a: PathArg = parse(args)?;
    std::fs::remove_file(&a.path).map_err(err)?;
    ok(())
}

fn path_exists(args: &Value) -> CmdResult {
    let a: PathArg = parse(args)?;
    ok(!a.path.is_empty() && Path::new(&a.path).exists())
}

fn same_file_name(a: &Path, b: &Path) -> bool {
    if cfg!(windows) { a.to_string_lossy().to_lowercase() == b.to_string_lossy().to_lowercase() } else { a == b }
}

/// Rename a project file; returns the new path. Refuses a name another
/// project already has (a change of case alone is allowed).
pub fn rename_project(path: &Path, new_name: &str) -> Result<PathBuf, String> {
    let target = path.with_file_name(format!("{}{PROJECT_EXTENSION}", safe_filename(new_name)));
    if target.exists() && !same_file_name(&target, path) {
        return Err(format!("A project named {} already exists.", py_repr(new_name)));
    }
    std::fs::rename(path, &target).map_err(err)?;
    Ok(target)
}

fn project_rename(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct A {
        path: String,
        new_name: String,
    }
    let a: A = parse(args)?;
    ok(rename_project(Path::new(&a.path), &a.new_name)?.display().to_string())
}

/// Check a document's envelope as PyMappr's `load_project` / `load_preset`
/// do; returns the stored name (or the file's) and the body.
fn check_document(
    text: &str,
    path: &Path,
    format: &str,
    body: &str,
    what: &str,
    verb: &str,
) -> Result<(String, Value), String> {
    let document: Value = serde_json::from_str(text).map_err(|e| format!("Not a PyMappr {what} file: {e}"))?;
    let bad = || format!("Not a PyMappr {what} file.");
    let object = document.as_object().ok_or_else(bad)?;
    if object.get("format").and_then(Value::as_str) != Some(format) || !object.get(body).is_some_and(Value::is_object) {
        return Err(bad());
    }
    let version = match object.get("format_version") {
        None => 1,
        Some(Value::Number(n)) => n.as_f64().map(|v| v.trunc() as i64).ok_or_else(bad)?,
        Some(Value::String(s)) => s.trim().parse::<i64>().map_err(|_| bad())?,
        Some(_) => return Err(bad()),
    };
    if version > FORMAT_VERSION {
        let app = match object.get("app_version") {
            Some(Value::String(s)) => s.clone(),
            Some(v) => v.to_string(),
            None => "?".into(),
        };
        return Err(format!("This {what} was saved by a newer PyMappr ({app}). Update PyMappr to {verb} it."));
    }
    let name = match object.get("name") {
        Some(Value::String(s)) if !s.is_empty() => s.clone(),
        _ => file_stem(path),
    };
    Ok((name, object[body].clone()))
}

pub fn check_project(path: &Path) -> Result<(String, Value), String> {
    let text = std::fs::read_to_string(path).map_err(err)?;
    check_document(&text, path, PROJECT_FORMAT, "state", "project", "open")
}

/// Copy a shared project into the projects folder, as "name (2)" etc. when
/// the name is taken; returns the copy's path.
pub fn import_project(source: &Path, folder: &Path) -> Result<PathBuf, String> {
    check_project(source)?;
    let base = safe_filename(&file_stem(source));
    let mut target = folder.join(format!("{base}{PROJECT_EXTENSION}"));
    let mut counter = 2;
    while target.exists() {
        target = folder.join(format!("{base} ({counter}){PROJECT_EXTENSION}"));
        counter += 1;
    }
    std::fs::create_dir_all(folder).map_err(err)?;
    std::fs::copy(source, &target).map_err(err)?;
    Ok(target)
}

fn project_import(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        source: String,
    }
    let a: A = parse(args)?;
    ok(import_project(Path::new(&a.source), &projects_dir(core))?.display().to_string())
}

fn session_read(core: &Arc<Core>) -> CmdResult {
    ok(std::fs::read_to_string(session_path(&core.config_dir)).ok())
}

fn session_write(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        text: String,
    }
    let a: A = parse(args)?;
    write_text(&session_path(&core.config_dir), &a.text)?;
    ok(())
}

// ------------------------------------------------------------------- presets

#[derive(Serialize, Debug, PartialEq)]
pub struct PresetListing {
    pub name: String,
    pub path: String,
}

/// Every readable preset, sorted by name without regard to case; files that
/// are not presets are skipped.
pub fn list_presets(folder: &Path) -> Vec<PresetListing> {
    let Ok(entries) = std::fs::read_dir(folder) else {
        return Vec::new();
    };
    let mut found: Vec<PresetListing> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_file() && has_extension(p, PRESET_EXTENSION))
        .filter_map(|p| {
            let text = std::fs::read_to_string(&p).ok()?;
            let (name, _) = check_document(&text, &p, PRESET_FORMAT, "settings", "preset", "use").ok()?;
            Some(PresetListing { name, path: p.display().to_string() })
        })
        .collect();
    found.sort_by_key(|p| p.name.to_lowercase());
    found
}

fn preset_read(args: &Value) -> CmdResult {
    let a: PathArg = parse(args)?;
    let path = Path::new(&a.path);
    let text = std::fs::read_to_string(path).map_err(err)?;
    let (name, settings) = check_document(&text, path, PRESET_FORMAT, "settings", "preset", "use")?;
    ok(json!({ "name": name, "settings": settings }))
}

fn delete_built_in(folder: &Path) -> CmdResult {
    write_text(&folder.join(BUILT_IN_DELETED), "")?;
    ok(())
}

// --------------------------------------------------------------- manual entry

/// Typed-in points, as PyMappr's `build_manual_dataset` builds them.
#[derive(Serialize, Debug, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct ManualDataset {
    /// `name1` (and `name2` when a line had a label), then lon, lat.
    pub columns: Vec<String>,
    /// `["Legend"]`, or `["Legend", "Label"]`.
    pub name_labels: Vec<String>,
    pub rows: Vec<Vec<Value>>,
    /// One message per line that could not be read.
    pub skipped: Vec<String>,
}

/// Python's `str.splitlines()`.
fn split_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        if matches!(c, '\n' | '\r' | '\x0b' | '\x0c' | '\x1c' | '\x1d' | '\x1e' | '\u{85}' | '\u{2028}' | '\u{2029}') {
            lines.push(&text[start..i]);
            let mut end = i + c.len_utf8();
            if c == '\r' && chars.peek().map(|&(_, n)| n) == Some('\n') {
                chars.next();
                end += 1;
            }
            start = end;
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

/// One point per non-empty line: two coordinates separated by a comma,
/// semicolon or tab, in `order` ("lat,lon" or "lon,lat"), and an optional
/// label. Decimal degrees or DMS.
pub fn build_manual_dataset(legend: &str, text: &str, order: &str) -> ManualDataset {
    let lat_first = order.replace(' ', "").to_lowercase().starts_with("lat");
    let mut rows: Vec<(String, f64, f64)> = Vec::new();
    let mut skipped = Vec::new();
    let mut any_labels = false;
    for (index, raw) in split_lines(text).into_iter().enumerate() {
        let number = index + 1;
        let line = raw.trim();
        if line.is_empty() {
            continue;
        }
        let parts: Vec<&str> = line.split([',', ';', '\t']).map(str::trim).filter(|p| !p.is_empty()).collect();
        if parts.len() < 2 {
            skipped.push(format!("line {number}: expected two coordinates, got {}", py_repr(line)));
            continue;
        }
        let label = parts[2..].join(", ");
        let parsed = if lat_first {
            parse_latitude(parts[0]).and_then(|lat| parse_longitude(parts[1]).map(|lon| (lon, lat)))
        } else {
            parse_longitude(parts[0]).and_then(|lon| parse_latitude(parts[1]).map(|lat| (lon, lat)))
        };
        match parsed {
            Ok((lon, lat)) => {
                any_labels |= !label.is_empty();
                rows.push((label, lon, lat));
            }
            Err(e) => skipped.push(format!("line {number}: {e}")),
        }
    }
    let name_labels: Vec<String> = if any_labels { vec!["Legend".into(), "Label".into()] } else { vec!["Legend".into()] };
    let mut columns: Vec<String> = (1..=name_labels.len()).map(|i| format!("name{i}")).collect();
    columns.extend(["lon".into(), "lat".into()]);
    let rows = rows
        .into_iter()
        .map(|(label, lon, lat)| {
            let mut row = vec![json!(legend)];
            if any_labels {
                row.push(json!(label));
            }
            row.extend([json!(lon), json!(lat)]);
            row
        })
        .collect();
    ManualDataset { columns, name_labels, rows, skipped }
}

fn parse_manual(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        legend: String,
        text: String,
        order: Option<String>,
    }
    let a: A = parse(args)?;
    ok(build_manual_dataset(&a.legend, &a.text, a.order.as_deref().unwrap_or("lat,lon")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("rustymappr-docs-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn project_text(name: &str) -> String {
        json!({"format": PROJECT_FORMAT, "format_version": 1, "name": name, "state": {}}).to_string()
    }

    fn core_in(dir: &Path) -> Arc<Core> {
        Arc::new(Core {
            basemap: Default::default(),
            config_dir: dir.join("config"),
            default_data_dir: dir.join("data"),
            jobs: Default::default(),
        })
    }

    #[test]
    fn safe_filenames_match_pymappr() {
        assert_eq!(safe_filename("a<b>:c\"d/e\\f|g?h*"), "a_b__c_d_e_f_g_h_");
        assert_eq!(safe_filename("  ..My map.. "), "My map");
        assert_eq!(safe_filename("   "), "Untitled");
        assert_eq!(safe_filename("NUL.tar"), "NUL_.tar");
        assert_eq!(safe_filename("com1"), "com1_");
        assert_eq!(safe_filename("console"), "console");
        assert_eq!(safe_filename("tab\there"), "tab_here");
    }

    #[test]
    fn repr_quotes_like_python() {
        assert_eq!(py_repr("abc"), "'abc'");
        assert_eq!(py_repr("it's"), "\"it's\"");
        assert_eq!(py_repr("a'b\"c"), "'a\\'b\"c'");
        assert_eq!(py_repr("back\\slash"), "'back\\\\slash'");
    }

    #[test]
    fn projects_list_newest_first_and_skip_presets() {
        let dir = temp_dir("list");
        std::fs::write(dir.join("old.pymappr"), project_text("old")).unwrap();
        std::thread::sleep(std::time::Duration::from_millis(30));
        std::fs::write(dir.join("new.pymappr"), project_text("new")).unwrap();
        std::fs::write(dir.join("x.pymappr-preset"), "{}").unwrap();
        std::fs::write(dir.join("notes.txt"), "").unwrap();
        let names: Vec<String> = list_projects(&dir).into_iter().map(|p| p.name).collect();
        assert_eq!(names, ["new", "old"]);
        assert!(list_projects(&dir.join("missing")).is_empty());
    }

    #[test]
    fn rename_refuses_a_taken_name_but_allows_a_case_change() {
        let dir = temp_dir("rename");
        let a = dir.join("survey.pymappr");
        std::fs::write(&a, project_text("survey")).unwrap();
        std::fs::write(dir.join("other.pymappr"), project_text("other")).unwrap();
        assert_eq!(rename_project(&a, "other").unwrap_err(), "A project named 'other' already exists.");
        let renamed = rename_project(&a, "Survey").unwrap();
        assert_eq!(renamed.file_name().unwrap(), "Survey.pymappr");
        let moved = rename_project(&renamed, "Fig: 1").unwrap();
        assert_eq!(moved.file_name().unwrap(), "Fig_ 1.pymappr");
        assert!(moved.exists());
    }

    #[test]
    fn import_copies_with_a_number_when_the_name_is_taken() {
        let dir = temp_dir("import");
        let source = dir.join("shared.pymappr");
        std::fs::write(&source, project_text("shared")).unwrap();
        let folder = dir.join("Projects");
        let first = import_project(&source, &folder).unwrap();
        let second = import_project(&source, &folder).unwrap();
        let third = import_project(&source, &folder).unwrap();
        assert_eq!(first.file_name().unwrap(), "shared.pymappr");
        assert_eq!(second.file_name().unwrap(), "shared (2).pymappr");
        assert_eq!(third.file_name().unwrap(), "shared (3).pymappr");
        let bad = dir.join("bad.pymappr");
        std::fs::write(&bad, "{\"format\": \"other\", \"state\": {}}").unwrap();
        assert_eq!(import_project(&bad, &folder).unwrap_err(), "Not a PyMappr project file.");
    }

    #[test]
    fn documents_are_checked_with_pymappr_messages() {
        let path = Path::new("C:/x/Survey.pymappr");
        let check = |text: &str| check_document(text, path, PROJECT_FORMAT, "state", "project", "open");
        assert!(check("{").unwrap_err().starts_with("Not a PyMappr project file: "));
        assert_eq!(check("[]").unwrap_err(), "Not a PyMappr project file.");
        assert_eq!(check(r#"{"format": "pymappr-project", "state": []}"#).unwrap_err(), "Not a PyMappr project file.");
        assert_eq!(
            check(r#"{"format": "pymappr-project", "format_version": 2, "app_version": "9.1", "state": {}}"#)
                .unwrap_err(),
            "This project was saved by a newer PyMappr (9.1). Update PyMappr to open it."
        );
        assert_eq!(check(r#"{"format": "pymappr-project", "state": {}}"#).unwrap().0, "Survey");
        assert_eq!(check(r#"{"format": "pymappr-project", "name": "Mine", "state": {}}"#).unwrap().0, "Mine");
    }

    #[test]
    fn presets_list_by_name_and_skip_unreadable_files() {
        let dir = temp_dir("presets");
        let folder = presets_dir(&dir);
        for name in ["beta", "Alpha", "gamma"] {
            let text = json!({"format": PRESET_FORMAT, "name": name, "settings": {}}).to_string();
            std::fs::write(folder.join(format!("{}{PRESET_EXTENSION}", safe_filename(name))), text).unwrap();
        }
        std::fs::write(folder.join(format!("broken{PRESET_EXTENSION}")), "{").unwrap();
        std::fs::write(folder.join(format!("project{PRESET_EXTENSION}")), project_text("p")).unwrap();
        std::fs::write(folder.join("a project.pymappr"), project_text("p")).unwrap();
        let names: Vec<String> = list_presets(&folder).into_iter().map(|p| p.name).collect();
        assert_eq!(names, ["Alpha", "beta", "gamma"]);
        delete_built_in(&folder).unwrap();
        assert!(folder.join(BUILT_IN_DELETED).exists());
        assert_eq!(list_presets(&folder).len(), 3);
    }

    #[test]
    fn commands_cover_the_projects_folder_and_the_session() {
        let dir = temp_dir("commands");
        let core = core_in(&dir);
        let chosen = dir.join("My projects");
        let set = core.dispatch("projects_dir_set", json!({"path": chosen.display().to_string()})).unwrap();
        assert_eq!(set, json!(chosen.display().to_string()));
        assert!(chosen.is_dir());
        assert_eq!(core.settings()["projectsDir"], json!(chosen.display().to_string()));
        let target = core.dispatch("project_path", json!({"name": "Fig: 1"})).unwrap();
        assert_eq!(target["exists"], json!(false));
        let path = target["path"].as_str().unwrap().to_string();
        assert!(path.ends_with("Fig_ 1.pymappr"));
        core.dispatch("project_write", json!({"path": path, "text": project_text("Fig: 1")})).unwrap();
        assert_eq!(core.dispatch("project_read", json!({"path": path})).unwrap(), json!(project_text("Fig: 1")));
        let listed = core.dispatch("projects_list", json!({})).unwrap();
        assert_eq!(listed[0]["name"], json!("Fig_ 1"));
        assert_eq!(core.dispatch("session_read", json!({})).unwrap(), Value::Null);
        core.dispatch("session_write", json!({"text": "abc"})).unwrap();
        assert_eq!(core.dispatch("session_read", json!({})).unwrap(), json!("abc"));
        assert!(session_path(&core.config_dir).ends_with("session.pymappr"));
        assert_eq!(core.dispatch("presets_builtin_deleted", json!({})).unwrap(), json!(false));
        core.dispatch("presets_delete_builtin", json!({})).unwrap();
        assert_eq!(core.dispatch("presets_builtin_deleted", json!({})).unwrap(), json!(true));
        core.dispatch("project_delete", json!({"path": path})).unwrap();
        assert_eq!(core.dispatch("path_exists", json!({"path": path})).unwrap(), json!(false));
    }

    #[test]
    fn preset_read_returns_name_and_settings() {
        let dir = temp_dir("preset-read");
        let path = dir.join(format!("Mine{PRESET_EXTENSION}"));
        let text = json!({"format": PRESET_FORMAT, "name": "Mine", "settings": {"point_alpha": 0.5}}).to_string();
        std::fs::write(&path, text).unwrap();
        let read = preset_read(&json!({"path": path.display().to_string()})).unwrap();
        assert_eq!(read, json!({"name": "Mine", "settings": {"point_alpha": 0.5}}));
        let future = dir.join(format!("Future{PRESET_EXTENSION}"));
        std::fs::write(&future, json!({"format": PRESET_FORMAT, "format_version": 99, "settings": {}}).to_string())
            .unwrap();
        assert_eq!(
            preset_read(&json!({"path": future.display().to_string()})).unwrap_err(),
            "This preset was saved by a newer PyMappr (?). Update PyMappr to use it."
        );
    }

    // PyMappr's tests/test_data_loader.py, manual entry.

    #[test]
    fn manual_lat_lon_lines() {
        let ds = build_manual_dataset("Pardosa distincta", "38,-100\n-25,140\n", "lat,lon");
        assert_eq!(ds.rows.len(), 2);
        assert!(ds.skipped.is_empty());
        assert_eq!(ds.name_labels, ["Legend"]);
        assert_eq!(ds.columns, ["name1", "lon", "lat"]);
        assert!(ds.rows.iter().all(|r| r[0] == json!("Pardosa distincta")));
        assert_eq!(ds.rows[0][2], json!(38.0));
        assert_eq!(ds.rows[0][1], json!(-100.0));
    }

    #[test]
    fn manual_lon_lat_order_and_labels() {
        let ds = build_manual_dataset("Sites", "-100, 38, Site A\n140.0;-25;Site B\n", "lon,lat");
        assert_eq!(ds.rows.len(), 2);
        assert_eq!(ds.name_labels, ["Legend", "Label"]);
        assert_eq!(ds.columns, ["name1", "name2", "lon", "lat"]);
        assert_eq!(ds.rows[0][1], json!("Site A"));
        assert_eq!(ds.rows[1][1], json!("Site B"));
        assert_eq!(ds.rows[0][2], json!(-100.0));
    }

    #[test]
    fn manual_dms_and_errors() {
        let ds = build_manual_dataset("Mixed", "47°36'35\"N, 122°19'59\"W\nnot-a-coordinate\n95, 10\n", "lat,lon");
        assert_eq!(ds.rows.len(), 1);
        assert_eq!(ds.skipped.len(), 2);
        assert_eq!(ds.skipped[0], "line 2: expected two coordinates, got 'not-a-coordinate'");
        assert!(ds.skipped[1].contains("line 3"));
        let lat = ds.rows[0][2].as_f64().unwrap();
        assert!((lat - (47.0 + 36.0 / 60.0 + 35.0 / 3600.0)).abs() < 1e-9);
    }

    #[test]
    fn manual_labels_join_extra_fields_and_blank_lines_keep_numbering() {
        let ds = build_manual_dataset("S", "\r\n1, 2, a, b\r\n\r\nx\n", "lat,lon");
        assert_eq!(ds.rows[0][1], json!("a, b"));
        assert_eq!(ds.skipped, ["line 4: expected two coordinates, got 'x'"]);
    }
}
