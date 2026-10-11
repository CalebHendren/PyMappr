//! Byte-for-byte comparison with PyMappr's own code export. The reference
//! cases under tests/data/ come from scripts/reference_codegen.py.

use std::path::{Path, PathBuf};

use mappr_codegen::{Branding, ExportOptions, InlineData, Language, generate_code, generate_working_directory};
use serde_json::Value;

fn data_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests").join("data")
}

fn cases() -> Vec<PathBuf> {
    let mut cases: Vec<PathBuf> = std::fs::read_dir(data_dir())
        .unwrap()
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.join("input.json").exists())
        .collect();
    cases.sort();
    cases
}

fn options(input: &Value) -> ExportOptions {
    let size = input["figureSize"].as_array().map(|s| (s[0].as_f64().unwrap(), s[1].as_f64().unwrap()));
    ExportOptions {
        project_name: input["projectName"].as_str().unwrap().to_string(),
        figure_size: size,
        inset_export: None,
        branding: Branding::pymappr(),
        csv_newline: "\r\n".into(),
    }
}

fn read(path: &Path) -> String {
    String::from_utf8(std::fs::read(path).unwrap()).unwrap()
}

/// The first differing line, for a readable failure.
fn first_difference(want: &str, got: &str) -> String {
    for (i, (a, b)) in want.split('\n').zip(got.split('\n')).enumerate() {
        if a != b {
            return format!("line {}:\n  want: {a:.400}\n  got:  {b:.400}", i + 1);
        }
    }
    format!("lengths differ: want {} bytes, got {}", want.len(), got.len())
}

fn check(case: &str, label: &str, want: &str, got: &str, failures: &mut Vec<String>) {
    if want != got {
        failures.push(format!("{case} {label}: {}", first_difference(want, got)));
    }
}

#[test]
fn scripts_match_pymappr_byte_for_byte() {
    let mut failures = Vec::new();
    let mut checked = 0;
    for dir in cases() {
        let case = dir.file_name().unwrap().to_string_lossy().to_string();
        let input: Value = serde_json::from_str(&read(&dir.join("input.json"))).unwrap();
        let opts = options(&input);
        let state = &input["state"];
        for (language, ext, template) in [
            (Language::Python, "py", mappr_codegen::python::TEMPLATE),
            (Language::R, "R", mappr_codegen::r_script::TEMPLATE),
        ] {
            let got = generate_code(state, language, InlineData::Embedded, &opts).unwrap().code;
            let full = dir.join(format!("recreate_map.{ext}"));
            if full.exists() {
                check(&case, ext, &read(&full), &got, &mut failures);
            } else {
                let head = read(&dir.join(format!("recreate_map.{ext}.head")));
                check(&case, ext, &(head + template), &got, &mut failures);
            }
            let workdir = dir.join(format!("workdir-{ext}"));
            let files = generate_working_directory(state, language, &opts).unwrap();
            let manifest: Vec<String> = read(&workdir.join("MANIFEST")).lines().map(String::from).collect();
            let names: Vec<String> = files.iter().map(|(n, _)| n.clone()).collect();
            if manifest != names {
                failures.push(format!("{case} workdir-{ext}: files {names:?}, want {manifest:?}"));
                continue;
            }
            for (name, content) in &files {
                let want = if name.starts_with("recreate_map.") {
                    read(&workdir.join(format!("{name}.head"))) + template
                } else {
                    read(&workdir.join(name))
                };
                check(&case, &format!("workdir-{ext}/{name}"), &want, content, &mut failures);
            }
            checked += 1;
        }
    }
    assert!(failures.is_empty(), "{} of {checked} differ:\n{}", failures.len(), failures.join("\n\n"));
    assert!(checked >= 20, "only {checked} reference outputs found");
}
