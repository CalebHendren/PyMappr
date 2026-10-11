//! Python and R scripts that recreate a map outside the app: a port of
//! PyMappr's code export (`pymappr/export/`), byte for byte.
//!
//! The input is the project state exactly as PyMappr saves it (the
//! `state` of a `.pymappr` file), plus what only the renderer knows - the
//! exported figure size and the resolved inset - passed in
//! [`ExportOptions`]. The configuration block written above the templates
//! is PyMappr's; the templates in `templates/` are PyMappr's, verbatim.

pub mod config;
pub mod data;
pub mod layout;
pub mod lit;
pub mod options;
pub mod proj;
pub mod python;
pub mod r_script;
pub mod styling;
pub mod tables;

use serde_json::Value;

pub use config::{Branding, DataMode, ExportOptions, InlineData, placeholder};
use config::{build_config, export_filename};
use lit::safe_name;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Language {
    Python,
    R,
}

impl Language {
    pub fn parse(text: &str) -> Result<Language, String> {
        match text {
            "Python" => Ok(Language::Python),
            "R" => Ok(Language::R),
            other => Err(format!("Unknown language: {other:?}")),
        }
    }

    pub fn extension(self) -> &'static str {
        match self {
            Language::Python => ".py",
            Language::R => ".R",
        }
    }

    pub fn script_name(self) -> String {
        format!("recreate_map{}", self.extension())
    }
}

impl InlineData {
    /// "embedded", "placeholder" or "head:N".
    pub fn parse(text: &str) -> Result<InlineData, String> {
        match text {
            "embedded" | "" => Ok(InlineData::Embedded),
            "placeholder" => Ok(InlineData::Placeholder),
            other => other
                .strip_prefix("head:")
                .and_then(|n| n.trim().parse().ok())
                .map(InlineData::Head)
                .ok_or_else(|| format!("Unknown data mode: {other:?}")),
        }
    }
}

/// A generated single-file script.
#[derive(Debug, Clone)]
pub struct Generated {
    pub code: String,
    /// What the map shows that the script cannot reproduce.
    pub notes: Vec<String>,
}

/// The complete script recreating the map (`generate_code`).
pub fn generate_code(state: &Value, language: Language, data: InlineData, opts: &ExportOptions) -> Result<Generated, String> {
    let config = build_config(state, DataMode::Inline(data), opts)?;
    let code = match language {
        Language::Python => python::script(&config),
        Language::R => r_script::script(&config),
    };
    Ok(Generated { code, notes: config.notes })
}

/// A ready-to-run project folder as (relative path, text) pairs
/// (`generate_working_directory`): the script, the data as CSV, a
/// dependency manifest, a README, a .gitignore and, for R, an .Rproj.
pub fn generate_working_directory(state: &Value, language: Language, opts: &ExportOptions) -> Result<Vec<(String, String)>, String> {
    let config = build_config(state, DataMode::Files, opts)?;
    let project = safe_name(&opts.project_name);
    let mut files: Vec<(String, String)> = match language {
        Language::Python => vec![
            ("recreate_map.py".into(), python::script(&config)),
            ("requirements.txt".into(), python::REQUIREMENTS.into()),
            ("README.md".into(), python::readme(&project)),
            (".gitignore".into(), python::GITIGNORE.into()),
        ],
        Language::R => {
            let rproj = export_filename(&project, ".Rproj", &mut Vec::new(), "map");
            vec![
                ("recreate_map.R".into(), r_script::script(&config)),
                ("install.R".into(), r_script::INSTALL.into()),
                (rproj.clone(), r_script::RPROJ.into()),
                ("README.md".into(), r_script::readme(&project, &rproj)),
                (".gitignore".into(), r_script::GITIGNORE.into()),
            ]
        }
    };
    files.extend(config.file_contents);
    Ok(files)
}

/// What [`restore_data`] did.
#[derive(Debug, Clone, PartialEq)]
pub struct Restored {
    pub code: String,
    /// Datasets whose data went back in.
    pub restored: Vec<usize>,
    /// Datasets whose placeholder or sample could not be found.
    pub missing: Vec<usize>,
}

fn literal(language: Language, text: &str) -> String {
    match language {
        Language::Python => lit::py(&lit::Lit::str(text)),
        Language::R => lit::r_str(text),
    }
}

/// Put the real point data back into a script generated with
/// [`InlineData::Placeholder`] or [`InlineData::Head`] (and perhaps edited
/// since): each dataset's placeholder literal - in any quotes - or its
/// sample literal is replaced by the full embedded data.
pub fn restore_data(script: &str, state: &Value, language: Language, data: InlineData, csv_newline: &str) -> Restored {
    let entries = data::entries(state);
    let drawn: Vec<&data::Entry> = entries.iter().filter(|e| e.visible && !e.is_empty()).collect();
    let mut code = script.to_string();
    let (mut restored, mut missing) = (Vec::new(), Vec::new());
    for (index, entry) in drawn.iter().enumerate() {
        let full = literal(language, &entry.csv(csv_newline, None));
        let candidates: Vec<String> = match data {
            InlineData::Embedded => continue,
            InlineData::Placeholder => {
                let token = placeholder(index);
                ["\"\"\"", "'''", "\"", "'"].iter().map(|q| format!("{q}{token}{q}")).collect()
            }
            InlineData::Head(n) => vec![literal(language, &entry.csv(csv_newline, Some(n)))],
        };
        match candidates.iter().find(|c| code.contains(c.as_str())) {
            Some(found) => {
                code = code.replace(found.as_str(), &full);
                restored.push(index);
            }
            None => missing.push(index),
        }
    }
    Restored { code, restored, missing }
}
