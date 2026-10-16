//! The app's backend: shared state plus one `dispatch` that every front
//! door calls — the Tauri `core` command and the dev HTTP bridge. Each area
//! keeps its commands in its own `cmd_*` module.

use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};

use mappr_core::basemap::Basemap;
use serde::de::DeserializeOwned;
use serde_json::{Map, Value};

use crate::{cmd_app, cmd_code, cmd_docs, cmd_map};

pub type CmdResult = Result<Value, String>;

pub struct Core {
    pub basemap: RwLock<Option<Arc<Basemap>>>,
    /// `%APPDATA%\RustyMappr` (or the platform's equivalent).
    pub config_dir: PathBuf,
    /// Where downloaded map data goes by default.
    pub default_data_dir: PathBuf,
    /// Background jobs (downloads) report here; the UI polls `job_status`.
    pub jobs: crate::jobs::Jobs,
}

impl Core {
    pub fn new() -> Arc<Self> {
        let config_dir = dirs::config_dir().unwrap_or_else(std::env::temp_dir).join("RustyMappr");
        let default_data_dir =
            dirs::data_local_dir().unwrap_or_else(std::env::temp_dir).join("RustyMappr").join("data");
        let core = Core {
            basemap: RwLock::new(None),
            config_dir,
            default_data_dir,
            jobs: Default::default(),
        };
        cmd_app::init(&core);
        Arc::new(core)
    }

    pub fn basemap(&self) -> Result<Arc<Basemap>, String> {
        self.basemap
            .read()
            .unwrap()
            .clone()
            .ok_or_else(|| "The map data is not set up yet. Download it or choose its folder.".to_string())
    }

    pub fn settings_file(&self) -> PathBuf {
        self.config_dir.join("settings.json")
    }

    /// The saved settings, as a JSON object (empty when none are saved).
    pub fn settings(&self) -> Map<String, Value> {
        std::fs::read_to_string(self.settings_file())
            .ok()
            .and_then(|s| serde_json::from_str::<Value>(&s).ok())
            .and_then(|v| v.as_object().cloned())
            .unwrap_or_default()
    }

    /// Merge `patch` into the saved settings (a null value removes a key).
    pub fn update_settings(&self, patch: &Map<String, Value>) -> Result<Map<String, Value>, String> {
        let mut settings = self.settings();
        for (k, v) in patch {
            if v.is_null() {
                settings.remove(k);
            } else {
                settings.insert(k.clone(), v.clone());
            }
        }
        write_text(&self.settings_file(), &serde_json::to_string_pretty(&settings).map_err(err)?)?;
        Ok(settings)
    }

    /// Run one command. Each `cmd_*` module answers the commands it knows.
    pub fn dispatch(self: &Arc<Self>, cmd: &str, args: Value) -> CmdResult {
        let args = if args.is_null() { Value::Object(Map::new()) } else { args };
        cmd_app::dispatch(self, cmd, &args)
            .or_else(|| cmd_map::dispatch(self, cmd, &args))
            .or_else(|| cmd_docs::dispatch(self, cmd, &args))
            .or_else(|| cmd_code::dispatch(self, cmd, &args))
            .unwrap_or_else(|| Err(format!("unknown command '{cmd}'")))
    }
}

pub fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}

/// Deserialize a command's arguments.
pub fn parse<T: DeserializeOwned>(args: &Value) -> Result<T, String> {
    serde_json::from_value(args.clone()).map_err(|e| format!("bad arguments: {e}"))
}

/// Serialize a command's result.
pub fn ok<T: serde::Serialize>(value: T) -> CmdResult {
    serde_json::to_value(value).map_err(err)
}

pub fn write_text(path: &Path, text: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(err)?;
    }
    std::fs::write(path, text).map_err(|e| format!("could not write {}: {e}", path.display()))
}
