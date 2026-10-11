//! Commands for Python/R code export and the AI check.

use std::sync::Arc;

use serde_json::Value;

use crate::core::{CmdResult, Core};

pub fn dispatch(_core: &Arc<Core>, cmd: &str, _args: &Value) -> Option<CmdResult> {
    match cmd {
        _ => None,
    }
}
