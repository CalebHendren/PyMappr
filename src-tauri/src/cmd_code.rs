//! Commands for Python/R code export and the AI check.
//!
//! Every export command takes the project state as PyMappr saves it, plus
//! what only the renderer knows (see [`Renderer`]).

use std::path::PathBuf;
use std::sync::Arc;

use mappr_codegen::{ExportOptions, InlineData, Language, generate_code, generate_working_directory};
use serde::Deserialize;
use serde_json::{Map, Value, json};

use crate::core::{CmdResult, Core, err, ok, parse, write_text};
use crate::llm::{self, SendOptions};

pub fn dispatch(core: &Arc<Core>, cmd: &str, args: &Value) -> Option<CmdResult> {
    Some(match cmd {
        "code_generate" => code_generate(core, args),
        "code_save" => code_save(args),
        "code_workdir" => code_workdir(core, args),
        "code_restore" => code_restore(args),
        "llm_key_set" => llm_key_set(args),
        "llm_key_status" => llm_key_status(),
        "llm_key_clear" => llm::key_clear().and_then(|()| ok(())),
        "llm_prefs" => llm_prefs(core),
        "llm_prefs_set" => llm_prefs_set(core, args),
        "llm_models_refresh" => llm_models_refresh(core),
        "llm_preview" => llm_preview(args),
        "llm_check" => llm_check(core, args),
        _ => return None,
    })
}

/// What the renderer contributes to an export. `insetExport` is PyMappr's
/// `MapRenderer.inset_export()` dict, or null without an inset (which is
/// what PyMappr writes when the inset is off).
#[derive(Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
struct Renderer {
    inset_export: Option<Value>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ExportArgs {
    state: Value,
    language: String,
    /// [width, height] in inches, or null for PyMappr's default canvas.
    #[serde(default)]
    figure_size: Option<[f64; 2]>,
    #[serde(default)]
    renderer: Option<Renderer>,
    #[serde(default)]
    project_name: Option<String>,
}

impl ExportArgs {
    fn language(&self) -> Result<Language, String> {
        Language::parse(&self.language)
    }

    fn options(&self) -> ExportOptions {
        ExportOptions {
            project_name: self
                .project_name
                .clone()
                .filter(|n| !n.trim().is_empty())
                .unwrap_or_else(|| "Untitled".into()),
            figure_size: self.figure_size.map(|[w, h]| (w, h)),
            inset_export: self.renderer.as_ref().and_then(|r| r.inset_export.clone()).filter(|v| !v.is_null()),
            ..Default::default()
        }
    }
}

fn remember_language(core: &Core, language: &str) {
    let mut patch = Map::new();
    patch.insert("codeExportLanguage".into(), Value::String(language.into()));
    // Settings are a convenience; never fail an export over them.
    let _ = core.update_settings(&patch);
}

fn code_generate(core: &Core, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct A {
        #[serde(flatten)]
        export: ExportArgs,
        #[serde(default)]
        data_mode: Option<String>,
    }
    let a: A = parse(args)?;
    let language = a.export.language()?;
    let mode = InlineData::parse(a.data_mode.as_deref().unwrap_or("embedded"))?;
    remember_language(core, &a.export.language);
    let generated = generate_code(&a.export.state, language, mode, &a.export.options())?;
    ok(json!({
        "code": generated.code,
        "lines": generated.code.lines().count(),
        "notes": generated.notes,
    }))
}

fn code_save(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        path: PathBuf,
        code: String,
    }
    let a: A = parse(args)?;
    let mut code = a.code;
    if !code.ends_with('\n') {
        code.push('\n');
    }
    write_text(&a.path, &code)?;
    ok(())
}

/// Write the working directory, or - when files exist and `overwrite` is
/// false - write nothing and list them so the UI can ask.
fn code_workdir(core: &Core, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct A {
        folder: PathBuf,
        #[serde(flatten)]
        export: ExportArgs,
        #[serde(default)]
        overwrite: bool,
    }
    let a: A = parse(args)?;
    let language = a.export.language()?;
    remember_language(core, &a.export.language);
    let files = generate_working_directory(&a.export.state, language, &a.export.options())?;
    let existing: Vec<String> =
        files.iter().filter(|(rel, _)| a.folder.join(rel).exists()).map(|(rel, _)| rel.clone()).collect();
    if !existing.is_empty() && !a.overwrite {
        return ok(json!({"written": [], "existing": existing}));
    }
    let mut written = Vec::new();
    for (rel, content) in &files {
        write_text(&a.folder.join(rel), content)?;
        written.push(rel.clone());
    }
    ok(json!({"written": written, "existing": existing}))
}

fn code_restore(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct A {
        code: String,
        state: Value,
        language: String,
        data_mode: String,
    }
    let a: A = parse(args)?;
    let language = Language::parse(&a.language)?;
    let mode = InlineData::parse(&a.data_mode)?;
    let r = mappr_codegen::restore_data(&a.code, &a.state, language, mode, &ExportOptions::default().csv_newline);
    ok(json!({"code": r.code, "restored": r.restored, "missing": r.missing}))
}

// ---------------------------------------------------------------- AI check

fn llm_key_set(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        key: String,
    }
    let a: A = parse(args)?;
    llm::key_set(&a.key)?;
    llm_key_status()
}

/// Whether a key is stored, and a hint of it; never the key itself.
fn llm_key_status() -> CmdResult {
    let key = llm::key_get()?;
    ok(json!({"set": key.is_some(), "hint": key.as_deref().map(llm::key_hint)}))
}

fn llm_prefs(core: &Core) -> CmdResult {
    let settings = core.settings();
    ok(json!({
        "model": settings.get("llmModel").and_then(Value::as_str).unwrap_or(llm::DEFAULT_MODEL),
        "send": settings.get("llmSend").cloned().unwrap_or_else(|| json!(SendOptions::default())),
        "presets": llm::PRESET_MODELS,
        "defaultModel": llm::DEFAULT_MODEL,
        "models": settings.get("llmModelList").cloned().unwrap_or(Value::Null),
        "keyUrl": llm::KEY_URL,
    }))
}

fn llm_prefs_set(core: &Core, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        #[serde(default)]
        model: Option<String>,
        #[serde(default)]
        send: Option<SendOptions>,
    }
    let a: A = parse(args)?;
    let mut patch = Map::new();
    if let Some(model) = a.model.map(|m| m.trim().to_string()).filter(|m| !m.is_empty()) {
        patch.insert("llmModel".into(), Value::String(model));
    }
    if let Some(send) = a.send {
        patch.insert("llmSend".into(), serde_json::to_value(send).map_err(err)?);
    }
    core.update_settings(&patch)?;
    llm_prefs(core)
}

/// Fetch OpenRouter's catalog and cache it in settings (`llmModelList`).
fn llm_models_refresh(core: &Core) -> CmdResult {
    let models = llm::fetch_models()?;
    let mut patch = Map::new();
    patch.insert("llmModelList".into(), serde_json::to_value(&models).map_err(err)?);
    core.update_settings(&patch)?;
    ok(models)
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CheckArgs {
    /// The script as it stands in the export dialog, data embedded.
    code: String,
    #[serde(flatten)]
    export: ExportArgs,
    model: String,
    #[serde(default)]
    send: SendOptions,
    /// A PNG data URL of the map, sent only with `send.mapImage`.
    #[serde(default)]
    map_image: Option<String>,
}

struct Prepared {
    payload: Value,
    language: Language,
    mode: InlineData,
    /// Datasets whose data could not be swapped out of the script.
    unmatched: Vec<usize>,
}

fn prepare(a: &CheckArgs) -> Result<Prepared, String> {
    let language = a.export.language()?;
    if a.code.trim().is_empty() {
        return Err("There is no script to check.".into());
    }
    let model = a.model.trim();
    if model.is_empty() {
        return Err("Pick a model first.".into());
    }
    let opts = a.export.options();
    let mode = a.send.data_mode();
    let stripped = mappr_codegen::strip_data(&a.code, &a.export.state, language, mode, &opts.csv_newline);
    let description = llm::describe_map(&a.export.state, language, &a.send, &opts)?;
    let image = if a.send.map_image { a.map_image.as_deref().filter(|u| u.starts_with("data:image/")) } else { None };
    let payload = llm::build_payload(model, llm::build_messages(&stripped.code, language, &description, image));
    let unmatched = if mode == InlineData::Embedded { Vec::new() } else { stripped.missing };
    Ok(Prepared { payload, language, mode, unmatched })
}

fn data_mode_name(mode: InlineData) -> String {
    match mode {
        InlineData::Embedded => "embedded".into(),
        InlineData::Placeholder => "placeholder".into(),
        InlineData::Head(n) => format!("head:{n}"),
    }
}

/// The exact request body, and its size, before anything is sent.
fn llm_preview(args: &Value) -> CmdResult {
    let a: CheckArgs = parse(args)?;
    let p = prepare(&a)?;
    let (chars, tokens) = llm::payload_size(&p.payload);
    ok(json!({
        "url": llm::CHAT_URL,
        "payload": p.payload,
        "chars": chars,
        "approxTokens": tokens,
        "dataMode": data_mode_name(p.mode),
        "unmatched": p.unmatched,
    }))
}

/// Send the script for checking as a background job; poll `job_status`.
/// The finished job's `result` is `{model, code, changes, noChanges, notes,
/// finishReason, restored, missing}`, `code` (or null) being the suggested
/// script with the real data put back.
fn llm_check(core: &Arc<Core>, args: &Value) -> CmdResult {
    let a: CheckArgs = parse(args)?;
    let p = prepare(&a)?;
    if !p.unmatched.is_empty() {
        // Sending would leak data the user chose to hold back.
        return Err("Some of the script's data is no longer where the export put it, so it cannot be held back. \
                    Regenerate the script and try again."
            .into());
    }
    let key = llm::key_get()?.ok_or("Set your OpenRouter API key first.")?;
    let model = a.model.trim().to_string();
    let id = core.jobs.start("Checking the script with AI");
    core.jobs.update(id, &format!("Waiting for {model}..."), None);
    let core = core.clone();
    let state = a.export.state;
    std::thread::spawn(move || {
        let outcome = (|| -> Result<Value, String> {
            let body = llm::send(&key, &p.payload)?;
            let (text, finish) = llm::extract_text(&body)?;
            let reply = llm::parse_reply(&text, p.language);
            if reply.code.is_none() && !reply.no_changes && finish.as_deref() == Some("length") {
                return Err("The reply was cut off before the script ended. Try a model with a longer output limit.".into());
            }
            let newline = ExportOptions::default().csv_newline;
            let (code, restored, missing) = match &reply.code {
                Some(code) => {
                    let r = mappr_codegen::restore_data(code, &state, p.language, p.mode, &newline);
                    (Some(r.code), r.restored, r.missing)
                }
                None => (None, Vec::new(), Vec::new()),
            };
            Ok(json!({
                "model": model,
                "code": code,
                "changes": reply.changes,
                "noChanges": reply.no_changes,
                "notes": reply.notes,
                "finishReason": finish,
                "restored": restored,
                "missing": if p.mode == InlineData::Embedded { Vec::new() } else { missing },
            }))
        })();
        if core.jobs.is_cancelled(id) {
            core.jobs.finish(id, Some("Cancelled.".into()));
            return;
        }
        match outcome {
            Ok(result) => core.jobs.finish_with(id, result),
            Err(e) => core.jobs.finish(id, Some(e)),
        }
    });
    ok(id)
}
