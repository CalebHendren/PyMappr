//! The AI check of an exported script: OpenRouter (bring your own key),
//! modelled on CoordRippr's LLM Assist (src/llm.js). Everything but
//! [`send`], [`fetch_models`] and the key store is pure and tested here.

use std::time::Duration;

use mappr_codegen::config::{DataMode, ExportOptions, build_config};
use mappr_codegen::{InlineData, Language, placeholder};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const CHAT_URL: &str = "https://openrouter.ai/api/v1/chat/completions";
pub const MODELS_URL: &str = "https://openrouter.ai/api/v1/models";
pub const KEY_URL: &str = "https://openrouter.ai/settings/keys";
pub const TIMEOUT: Duration = Duration::from_secs(180);

/// CoordRippr's OpenRouter presets (October 2026).
pub const PRESET_MODELS: [&str; 11] = [
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-opus-5.5",
    "openai/gpt-6.1-sol",
    "openai/gpt-6-astra",
    "google/gemini-3.8-flash",
    "google/gemini-3.1-pro-preview",
    "deepseek/deepseek-v4-pro",
    "qwen/qwen3.8-max",
    "moonshotai/kimi-k3",
    "z-ai/glm-5.3",
    "openrouter/auto",
];
pub const DEFAULT_MODEL: &str = "anthropic/claude-sonnet-5.5";

const KEY_SERVICE: &str = "RustyMappr";
const KEY_USER: &str = "openrouter";

// ------------------------------------------------------------------ models

/// One model of OpenRouter's catalog.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelInfo {
    pub id: String,
    /// The part before the "/", for grouping.
    pub author: String,
    pub name: Option<String>,
    /// `architecture.input_modalities`; empty when the catalog does not say.
    pub input_modalities: Vec<String>,
}

impl ModelInfo {
    pub fn accepts_images(&self) -> bool {
        self.input_modalities.iter().any(|m| m == "image")
    }
}

pub fn author_of(id: &str) -> String {
    id.split_once('/').map_or("other", |(a, _)| a).to_string()
}

/// Port of CoordRippr's `parseModelList`: the text-producing models of a
/// model-list response, de-duplicated and sorted, keeping each one's input
/// modalities so the UI knows which take an image.
pub fn parse_model_list(body: &str) -> Result<Vec<ModelInfo>, String> {
    let data: Value = serde_json::from_str(body).map_err(|_| {
        format!("Model list is not JSON: {}", body.chars().take(200).collect::<String>())
    })?;
    if let Some(error) = data.get("error").filter(|e| !e.is_null()) {
        return Err(error_text(error));
    }
    let list = data.get("data").and_then(Value::as_array).ok_or("Response contains no model list")?;
    let mut models: Vec<ModelInfo> = Vec::new();
    for m in list {
        let Some(id) = m.get("id").and_then(Value::as_str).map(str::trim).filter(|id| !id.is_empty()) else {
            continue;
        };
        let arch = m.get("architecture");
        let modalities = |key: &str| -> Option<Vec<String>> {
            arch?.get(key)?.as_array().map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
        };
        if modalities("output_modalities").is_some_and(|out| !out.iter().any(|o| o == "text")) {
            continue;
        }
        if models.iter().any(|existing| existing.id == id) {
            continue;
        }
        models.push(ModelInfo {
            id: id.to_string(),
            author: author_of(id),
            name: m.get("name").and_then(Value::as_str).map(String::from),
            input_modalities: modalities("input_modalities").unwrap_or_default(),
        });
    }
    models.sort_by(|a, b| a.id.to_lowercase().cmp(&b.id.to_lowercase()).then(a.id.cmp(&b.id)));
    Ok(models)
}

fn error_text(error: &Value) -> String {
    error
        .get("message")
        .and_then(Value::as_str)
        .map(String::from)
        .unwrap_or_else(|| error.to_string().chars().take(200).collect())
}

// ------------------------------------------------------------ what is sent

/// What the user chose to send besides the script.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct SendOptions {
    /// The datasets' column names in the description.
    pub columns: bool,
    /// The header and first `rows` rows of each dataset, in the script.
    pub first_rows: bool,
    pub rows: Option<usize>,
    /// A PNG of the map (only for models that take images).
    pub map_image: bool,
    /// Every row, in the script.
    pub full_data: bool,
}

impl SendOptions {
    pub fn row_count(&self) -> usize {
        self.rows.unwrap_or(5).max(1)
    }

    /// The script is sent with placeholders unless data was asked for.
    pub fn data_mode(&self) -> InlineData {
        if self.full_data {
            InlineData::Embedded
        } else if self.first_rows {
            InlineData::Head(self.row_count())
        } else {
            InlineData::Placeholder
        }
    }
}

pub const SYSTEM_PROMPT: &str = "You review scripts that recreate a distribution map made in RustyMappr, \
a desktop mapping app (a port of PyMappr). The script has a configuration block written by the app \
followed by pre-made functions that draw the map with Natural Earth layers; the user runs it as is.

Check the script for bugs: anything that would stop it running, or would draw a map different from \
the one described (projection, view, layers, styles, legend). Prefer small, targeted fixes; do not \
restyle, reorganise or modernise working code, and keep every comment and the configuration values \
unless one is wrong.

Point data may be replaced by a placeholder such as __RUSTYMAPPR_DATA_0__ or cut to its first rows. \
That is deliberate: leave those strings exactly as they are and do not report them as bugs.

Reply with ONE fenced code block containing the full corrected script, then a bullet list of the \
changes you made, one bullet per change. If nothing needs changing, reply with just: No changes needed.";

fn on_off(on: bool) -> &'static str {
    if on { "on" } else { "off" }
}

/// A short description of the intended map, saying only what the user
/// allowed: column names only with `columns`.
pub fn describe_map(state: &Value, language: Language, send: &SendOptions, opts: &ExportOptions) -> Result<String, String> {
    let config = build_config(state, DataMode::Inline(send.data_mode()), opts)?;
    let mut lines = vec![
        format!("Language: {}.", if language == Language::Python { "Python (pandas, geopandas, matplotlib)" } else { "R (sf, ggplot2)" }),
        format!("Projection: {}.", config.projection),
        format!(
            "View (x0, x1, y0, y1 in map coordinates): {:.6}, {:.6}, {:.6}, {:.6}.",
            config.view[0], config.view[1], config.view[2], config.view[3]
        ),
    ];
    let layers: Vec<String> = config.layers.iter().map(|l| format!("{} ({})", l.key, l.kind)).collect();
    lines.push(format!("Base layers: {}.", if layers.is_empty() { "none".into() } else { layers.join(", ") }));
    let labels: Vec<String> = config
        .label_layers
        .iter()
        .filter_map(|l| match l {
            mappr_codegen::lit::Lit::Dict(pairs) => pairs.first().and_then(|(_, v)| v.as_str()).map(String::from),
            _ => None,
        })
        .collect();
    if !labels.is_empty() {
        lines.push(format!("Map labels: {}.", labels.join(", ")));
    }
    lines.push(format!(
        "Graticule: {}. Compass: {}. Scale bar: {}. Inset map: {}. Raster basemap: {}.",
        config.graticule.map_or("off".into(), |g| format!("every {g} degrees")),
        on_off(config.compass),
        on_off(config.scale_bar.bool("show")),
        on_off(config.inset.is_some()),
        config.basemap
    ));
    lines.push(format!(
        "Legend: {}{}.",
        on_off(config.legend.bool("show")),
        if config.legend_sections.is_some() { ", sectioned (colour and symbol columns)" } else { "" }
    ));
    let entries = mappr_codegen::data::entries(state);
    let drawn: Vec<_> = entries.iter().filter(|e| e.visible && !e.is_empty()).collect();
    lines.push(format!("Datasets drawn: {}.", drawn.len()));
    for (i, (entry, spec)) in drawn.iter().zip(&config.datasets).enumerate() {
        let mut line = format!("- Dataset {}: {} points", i + 1, entry.len());
        if send.columns {
            let mut columns = entry.name_labels.clone();
            columns.extend(["Longitude".to_string(), "Latitude".to_string()]);
            line.push_str(&format!("; columns: {}", columns.join(", ")));
            for (what, col) in [("grouped by", &spec.group_col), ("coloured by", &spec.color_col), ("symbols by", &spec.symbol_col)] {
                if let Some(col) = col {
                    line.push_str(&format!("; {what} {col}"));
                }
            }
        }
        line.push_str(&match send.data_mode() {
            InlineData::Placeholder => format!(
                "; its CSV data is replaced in the script by the placeholder {}",
                placeholder(i)
            ),
            InlineData::Head(n) => format!("; the script holds only its first {n} rows"),
            InlineData::Embedded => "; the script holds all its rows".into(),
        });
        lines.push(line + ".");
    }
    if send.map_image {
        lines.push("The attached image is the map as the app draws it.".into());
    }
    Ok(lines.join("\n"))
}

/// The chat messages: the system prompt, then the description and the
/// script (and the map image, when sent).
pub fn build_messages(code: &str, language: Language, description: &str, image: Option<&str>) -> Value {
    let fence = if language == Language::Python { "python" } else { "r" };
    let text = format!(
        "The intended map:\n{description}\n\nThe script:\n```{fence}\n{}\n```",
        code.trim_end_matches('\n')
    );
    let user = match image {
        Some(url) => json!([
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": url}},
        ]),
        None => Value::String(text),
    };
    json!([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])
}

pub fn build_payload(model: &str, messages: Value) -> Value {
    json!({"model": model, "messages": messages})
}

/// Rough size of a payload: its characters, and tokens at ~4 per character
/// (images counted by their encoded size, which overstates them).
pub fn payload_size(payload: &Value) -> (usize, usize) {
    let chars = payload.to_string().chars().count();
    (chars, chars.div_ceil(4))
}

// ----------------------------------------------------------------- replies

/// The model's reply, parsed.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Reply {
    /// The suggested script, or None when the reply holds none.
    pub code: Option<String>,
    pub changes: Vec<String>,
    pub no_changes: bool,
    /// The reply text around the code, for showing when parsing fails.
    pub notes: String,
}

/// The assistant text and finish reason from a chat completions body.
pub fn extract_text(body: &str) -> Result<(String, Option<String>), String> {
    let data: Value = serde_json::from_str(body).map_err(|_| {
        format!("The provider sent a reply that is not JSON: {}", body.chars().take(200).collect::<String>())
    })?;
    if let Some(error) = data.get("error").filter(|e| !e.is_null()) {
        return Err(error_text(error));
    }
    let choice = data.get("choices").and_then(|c| c.get(0)).ok_or("The provider returned no reply.")?;
    let text = match choice.pointer("/message/content") {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Array(parts)) => parts.iter().filter_map(|p| p.get("text").and_then(Value::as_str)).collect::<Vec<_>>().join(""),
        _ => String::new(),
    };
    let finish = choice.get("finish_reason").and_then(Value::as_str).map(String::from);
    Ok((text, finish))
}

/// Fenced blocks as (start of fence line, end after closing fence, body).
fn fenced_blocks(text: &str) -> Vec<(usize, usize, String)> {
    let mut blocks = Vec::new();
    let mut pos = 0;
    while let Some(found) = text[pos..].find("```") {
        let open = pos + found;
        let Some(eol) = text[open..].find('\n').map(|e| open + e + 1) else { break };
        // The closing fence: "```" at the start of a line.
        let mut search = eol;
        let close = loop {
            match text[search..].find("```") {
                Some(i) => {
                    let at = search + i;
                    if at == eol || text[..at].ends_with('\n') {
                        break Some(at);
                    }
                    search = at + 3;
                }
                None => break None,
            }
        };
        match close {
            Some(close) => {
                let end = text[close..].find('\n').map_or(text.len(), |e| close + e + 1);
                blocks.push((open, end, text[eol..close].to_string()));
                pos = end;
            }
            None => {
                // An unclosed fence (a reply cut short): the rest is code.
                blocks.push((open, text.len(), text[eol..].to_string()));
                break;
            }
        }
    }
    blocks
}

fn bullet(line: &str) -> Option<String> {
    let t = line.trim();
    for prefix in ["- ", "* ", "\u{2022} ", "+ "] {
        if let Some(rest) = t.strip_prefix(prefix) {
            return Some(rest.trim().to_string());
        }
    }
    let digits = t.chars().take_while(char::is_ascii_digit).count();
    if digits > 0 {
        let rest = &t[digits..];
        if let Some(rest) = rest.strip_prefix(". ").or_else(|| rest.strip_prefix(") ")) {
            return Some(rest.trim().to_string());
        }
    }
    None
}

fn looks_like_script(text: &str, language: Language) -> bool {
    let t = text.trim_start();
    let markers: &[&str] = match language {
        Language::Python => &["#!/usr/bin/env python", "# Made with", "import ", "from "],
        Language::R => &["# Made with", "library(", "ensure_packages"],
    };
    markers.iter().any(|m| t.starts_with(m)) && text.lines().count() > 20
}

/// Parse a reply: the longest fenced block is the script, bullets after
/// it the changes. Copes with prose around the block, no fence at all and
/// "No changes needed".
pub fn parse_reply(text: &str, language: Language) -> Reply {
    let no_changes_said = text.to_lowercase().contains("no changes needed");
    let blocks = fenced_blocks(text);
    let longest = blocks.iter().max_by_key(|b| b.2.len()).filter(|b| b.2.lines().count() > 1 || b.2.len() > 80);
    let (code, before, after) = match longest {
        Some((start, end, body)) => (Some(body.trim_end_matches('\n').to_string() + "\n"), &text[..*start], &text[*end..]),
        None if looks_like_script(text, language) => {
            // No fence: the script, perhaps followed by a bullet list.
            let lines: Vec<&str> = text.lines().collect();
            let mut cut = lines.len();
            while cut > 0 && (lines[cut - 1].trim().is_empty() || bullet(lines[cut - 1]).is_some()) {
                cut -= 1;
            }
            let script = lines[..cut].join("\n").trim_end().to_string() + "\n";
            let tail_start = text.len() - lines[cut..].join("\n").len();
            (Some(script), "", &text[tail_start.min(text.len())..])
        }
        None => (None, text, ""),
    };
    let mut changes: Vec<String> = after.lines().filter_map(bullet).filter(|b| !b.is_empty()).collect();
    if changes.is_empty() && code.is_some() {
        changes = before.lines().filter_map(bullet).filter(|b| !b.is_empty()).collect();
    }
    let notes = format!("{}\n{}", before.trim(), if code.is_some() { after.trim() } else { "" }).trim().to_string();
    let no_changes =
        no_changes_said && (code.is_none() || changes.iter().all(|c| c.to_lowercase().contains("no changes")));
    Reply { code, changes, no_changes, notes }
}

// ------------------------------------------------------------------ errors

/// A failed request's HTTP status (and body) as a plain message.
pub fn status_message(status: u16, body: &str) -> String {
    let detail = serde_json::from_str::<Value>(body)
        .ok()
        .and_then(|v| v.get("error").map(error_text))
        .unwrap_or_default();
    let lower = detail.to_lowercase();
    match status {
        401 | 403 => "OpenRouter did not accept the API key. Check it, or set a new one.".into(),
        402 => "Your OpenRouter account is out of credit. Add credit at openrouter.ai, or pick a free model.".into(),
        429 => "Rate limited: too many requests for now. Wait a minute and try again, or pick another model.".into(),
        404 => "That model does not exist on OpenRouter. Check the model ID, or load the model list again.".into(),
        400 if lower.contains("model") && (lower.contains("not a valid") || lower.contains("not found") || lower.contains("does not exist") || lower.contains("no endpoints")) => {
            "That model does not exist on OpenRouter. Check the model ID, or load the model list again.".into()
        }
        408 => "The request timed out at the provider. Try again, or pick a faster model.".into(),
        500..=599 => format!(
            "The model's provider had an error (HTTP {status}). Try again later, or pick another model.{}",
            if detail.is_empty() { String::new() } else { format!(" ({detail})") }
        ),
        _ => format!(
            "The request failed (HTTP {status}){}",
            if detail.is_empty() { ".".to_string() } else { format!(": {detail}") }
        ),
    }
}

pub fn timeout_message() -> String {
    format!(
        "No reply within {} seconds. Large scripts take a while; try again, or pick a faster model.",
        TIMEOUT.as_secs()
    )
}

// ------------------------------------------------------------------- HTTP

fn client(timeout: Duration) -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(timeout)
        .user_agent(concat!("RustyMappr/", env!("CARGO_PKG_VERSION")))
        .build()
        .map_err(|e| e.to_string())
}

fn transport_error(e: reqwest::Error) -> String {
    if e.is_timeout() {
        timeout_message()
    } else if e.is_connect() {
        "Could not reach OpenRouter. Check the internet connection.".into()
    } else {
        format!("The request failed: {e}")
    }
}

/// POST a chat completion; the reply body on success.
pub fn send(key: &str, payload: &Value) -> Result<String, String> {
    let response = client(TIMEOUT)?
        .post(CHAT_URL)
        .bearer_auth(key)
        .header("HTTP-Referer", "https://github.com/CalebHendren/RustyMappr")
        .header("X-Title", "RustyMappr")
        .json(payload)
        .send()
        .map_err(transport_error)?;
    let status = response.status().as_u16();
    let body = response.text().map_err(transport_error)?;
    if !(200..300).contains(&status) {
        return Err(status_message(status, &body));
    }
    Ok(body)
}

pub fn fetch_models() -> Result<Vec<ModelInfo>, String> {
    let response = client(Duration::from_secs(30))?.get(MODELS_URL).send().map_err(transport_error)?;
    let status = response.status().as_u16();
    let body = response.text().map_err(transport_error)?;
    if !(200..300).contains(&status) {
        return Err(status_message(status, &body));
    }
    parse_model_list(&body)
}

// --------------------------------------------------------------- the key

fn entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEY_SERVICE, KEY_USER).map_err(|e| format!("The credential store is unavailable: {e}"))
}

pub fn key_set(key: &str) -> Result<(), String> {
    let key = key.trim();
    if key.is_empty() {
        return Err("Paste an OpenRouter API key first.".into());
    }
    entry()?.set_password(key).map_err(|e| format!("Could not save the key: {e}"))
}

pub fn key_get() -> Result<Option<String>, String> {
    match entry()?.get_password() {
        Ok(key) => Ok(Some(key)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(format!("Could not read the key: {e}")),
    }
}

pub fn key_clear() -> Result<(), String> {
    match entry()?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(format!("Could not remove the key: {e}")),
    }
}

/// "sk-or-…abcd": enough to recognise a key, not to use it.
pub fn key_hint(key: &str) -> String {
    let chars: Vec<char> = key.chars().collect();
    if chars.len() <= 10 {
        return "…".into();
    }
    let head: String = chars.iter().take(6).collect();
    let tail: String = chars[chars.len() - 4..].iter().collect();
    format!("{head}…{tail}")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> Value {
        let doc: Value = serde_json::from_str(include_str!("../../src/lib/fixtures/hornbills-orchids.pymappr")).unwrap();
        doc["state"].clone()
    }

    fn payload_for(send: &SendOptions, image: Option<&str>) -> String {
        let state = fixture();
        let opts = ExportOptions::default();
        let code = mappr_codegen::generate_code(&state, Language::Python, send.data_mode(), &opts).unwrap().code;
        let description = describe_map(&state, Language::Python, send, &opts).unwrap();
        build_payload(DEFAULT_MODEL, build_messages(&code, Language::Python, &description, image)).to_string()
    }

    /// Values from the fixture's CSV rows.
    const DATA: [&str; 6] = ["94.50885", "26.17346", "1.49385", "46.23929", "bicornis,,94", "Holotype,"];

    #[test]
    fn code_only_sends_no_data() {
        let p = payload_for(&SendOptions::default(), None);
        for value in DATA {
            assert!(!p.contains(value), "{value} leaked");
        }
        assert!(p.contains("'__RUSTYMAPPR_DATA_0__'") && p.contains("'__RUSTYMAPPR_DATA_1__'"));
        assert!(!p.contains("columns: Genus"));
        assert!(!p.contains("image_url"));
    }

    #[test]
    fn column_names_go_in_the_description_only() {
        let p = payload_for(&SendOptions { columns: true, ..Default::default() }, None);
        assert!(p.contains("columns: Genus, Species, Type status, Longitude, Latitude"));
        for value in DATA {
            assert!(!p.contains(value), "{value} leaked");
        }
    }

    #[test]
    fn first_rows_send_a_sample() {
        let p = payload_for(&SendOptions { first_rows: true, rows: Some(2), ..Default::default() }, None);
        assert!(p.contains("94.50885") && p.contains("75.14686"));
        assert!(!p.contains("94.89993"), "third row sent");
        assert!(!p.contains("'__RUSTYMAPPR_DATA_0__'"));
        assert!(p.contains("only its first 2 rows"));
    }

    #[test]
    fn full_data_sends_everything() {
        let p = payload_for(&SendOptions { full_data: true, ..Default::default() }, None);
        assert!(p.contains("98.46463") && p.contains("46.23929"));
    }

    #[test]
    fn map_image_is_an_image_part() {
        let p = payload_for(&SendOptions { map_image: true, ..Default::default() }, Some("data:image/png;base64,AAAA"));
        let v: Value = serde_json::from_str(&p).unwrap();
        let parts = v["messages"][1]["content"].as_array().unwrap();
        assert_eq!(parts[1]["type"], "image_url");
        assert_eq!(parts[1]["image_url"]["url"], "data:image/png;base64,AAAA");
        assert_eq!(v["messages"][0]["role"], "system");
        assert_eq!(v["model"], DEFAULT_MODEL);
    }

    #[test]
    fn size_estimate() {
        let (chars, tokens) = payload_size(&json!({"a": "bcd"}));
        assert_eq!((chars, tokens), (11, 3));
    }

    const SCRIPT: &str = "#!/usr/bin/env python3\nimport os\nprint(1)\n";

    #[test]
    fn parses_a_fenced_reply() {
        let reply = format!(
            "Here is the fixed script:\n\n```python\n{SCRIPT}```\n\nChanges:\n- Fixed the import.\n* Printed 1.\n2. Third\n"
        );
        let r = parse_reply(&reply, Language::Python);
        assert_eq!(r.code.as_deref(), Some(SCRIPT));
        assert_eq!(r.changes, ["Fixed the import.", "Printed 1.", "Third"]);
        assert!(!r.no_changes);
    }

    #[test]
    fn parses_the_longest_of_several_blocks() {
        let reply = format!("Use `x`:\n```\nshort\n```\nFull script:\n```r\n{SCRIPT}```\n- one\n");
        assert_eq!(parse_reply(&reply, Language::R).code.as_deref(), Some(SCRIPT));
    }

    #[test]
    fn parses_an_unfenced_reply() {
        let script: String = std::iter::once("#!/usr/bin/env python3\n".to_string())
            .chain((0..30).map(|i| format!("x{i} = {i}\n")))
            .collect();
        let r = parse_reply(&format!("{script}\n- Changed x3.\n"), Language::Python);
        assert_eq!(r.code.as_deref(), Some(script.as_str()));
        assert_eq!(r.changes, ["Changed x3."]);
    }

    #[test]
    fn parses_an_unclosed_fence() {
        let r = parse_reply(&format!("```python\n{SCRIPT}"), Language::Python);
        assert_eq!(r.code.as_deref(), Some(SCRIPT));
    }

    #[test]
    fn parses_no_change() {
        let r = parse_reply("No changes needed.", Language::Python);
        assert!(r.no_changes && r.code.is_none());
        let r = parse_reply(&format!("```python\n{SCRIPT}```\n- No changes needed\n"), Language::Python);
        assert!(r.no_changes && r.code.is_some());
        let r = parse_reply("I could not read the script.", Language::Python);
        assert!(!r.no_changes && r.code.is_none());
        assert_eq!(r.notes, "I could not read the script.");
    }

    #[test]
    fn extracts_text_and_errors() {
        let body = r#"{"choices":[{"message":{"content":"hi"},"finish_reason":"stop"}]}"#;
        assert_eq!(extract_text(body).unwrap(), ("hi".into(), Some("stop".into())));
        assert_eq!(extract_text(r#"{"error":{"message":"nope"}}"#).unwrap_err(), "nope");
        assert!(extract_text("<html>").unwrap_err().contains("not JSON"));
        assert!(extract_text(r#"{"choices":[]}"#).is_err());
    }

    #[test]
    fn maps_statuses_to_plain_messages() {
        assert!(status_message(401, "").contains("did not accept the API key"));
        assert!(status_message(402, "").contains("out of credit"));
        assert!(status_message(429, "").contains("Rate limited"));
        assert!(status_message(503, r#"{"error":{"message":"overloaded"}}"#).contains("provider had an error (HTTP 503)"));
        assert!(status_message(503, r#"{"error":{"message":"overloaded"}}"#).contains("overloaded"));
        assert!(status_message(404, "").contains("does not exist"));
        assert!(status_message(400, r#"{"error":{"message":"foo/bar is not a valid model ID"}}"#).contains("does not exist"));
        assert!(status_message(400, r#"{"error":{"message":"bad input"}}"#).ends_with(": bad input"));
        assert!(timeout_message().contains("180 seconds"));
    }

    // CoordRippr's parseModelList cases.
    #[test]
    fn parses_an_openrouter_catalog() {
        let body = json!({"data": [
            {"id": "z-ai/glm-5.3", "architecture": {"output_modalities": ["text"], "input_modalities": ["text"]}},
            {"id": "anthropic/claude-sonnet-5.5", "architecture": {"input_modalities": ["text", "image"]}},
            {"id": "google/some-image-model", "architecture": {"output_modalities": ["image"]}},
            {"id": "anthropic/claude-sonnet-5.5"},
            {"id": ""}, null, {"name": "no id"},
        ]})
        .to_string();
        let models = parse_model_list(&body).unwrap();
        let ids: Vec<&str> = models.iter().map(|m| m.id.as_str()).collect();
        assert_eq!(ids, ["anthropic/claude-sonnet-5.5", "z-ai/glm-5.3"]);
        assert!(models[0].accepts_images() && !models[1].accepts_images());
        assert_eq!(models[0].author, "anthropic");
    }

    #[test]
    fn rejects_errors_and_non_lists() {
        assert!(parse_model_list("<html>").unwrap_err().contains("not JSON"));
        assert_eq!(parse_model_list(r#"{"error":{"message":"nope"}}"#).unwrap_err(), "nope");
        assert!(parse_model_list(r#"{"models":[]}"#).unwrap_err().contains("no model list"));
    }

    #[test]
    fn hints_hide_the_key() {
        assert_eq!(key_hint("sk-or-v1-0123456789abcdef"), "sk-or-…cdef");
        assert_eq!(key_hint("short"), "…");
    }
}
