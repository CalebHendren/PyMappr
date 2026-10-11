//! The Tauri app. Every UI request goes through the one `core` command into
//! `Core::dispatch`; the dev bridge (src/bin/devbridge.rs) uses the same.

pub mod cmd_app;
pub mod cmd_code;
pub mod cmd_docs;
pub mod cmd_map;
pub mod core;
pub mod jobs;
pub mod llm;

use std::sync::Arc;

use serde_json::Value;
use tauri::State;

#[tauri::command]
async fn core(state: State<'_, Arc<core::Core>>, cmd: String, args: Value) -> Result<Value, String> {
    let core = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || core.dispatch(&cmd, args))
        .await
        .map_err(|e| e.to_string())?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(core::Core::new())
        .invoke_handler(tauri::generate_handler![core])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
