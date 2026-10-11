//! Long-running background jobs (downloads) that the UI polls for progress,
//! which works the same through Tauri and the dev bridge.

use std::collections::HashMap;
use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};

use serde::Serialize;

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct JobStatus {
    pub id: u64,
    pub label: String,
    /// What it is doing now, in words.
    pub step: String,
    /// 0..1, or `None` when unknown.
    pub progress: Option<f64>,
    pub done: bool,
    pub error: Option<String>,
    /// Set when the job asks to stop.
    pub cancelled: bool,
    /// What a finished job produced, for jobs that produce something.
    pub result: Option<serde_json::Value>,
}

#[derive(Default)]
pub struct Jobs {
    next: AtomicU64,
    table: Mutex<HashMap<u64, JobStatus>>,
}

impl Jobs {
    pub fn start(&self, label: &str) -> u64 {
        let id = self.next.fetch_add(1, Ordering::Relaxed) + 1;
        let status = JobStatus { id, label: label.into(), ..Default::default() };
        self.table.lock().unwrap().insert(id, status);
        id
    }

    pub fn update(&self, id: u64, step: &str, progress: Option<f64>) {
        if let Some(s) = self.table.lock().unwrap().get_mut(&id) {
            s.step = step.into();
            s.progress = progress;
        }
    }

    pub fn finish(&self, id: u64, error: Option<String>) {
        if let Some(s) = self.table.lock().unwrap().get_mut(&id) {
            s.done = true;
            s.error = error;
            s.progress = Some(1.0);
        }
    }

    /// Finish successfully with a result the UI reads from `job_status`.
    pub fn finish_with(&self, id: u64, result: serde_json::Value) {
        if let Some(s) = self.table.lock().unwrap().get_mut(&id) {
            s.done = true;
            s.error = None;
            s.progress = Some(1.0);
            s.result = Some(result);
        }
    }

    pub fn cancel(&self, id: u64) {
        if let Some(s) = self.table.lock().unwrap().get_mut(&id) {
            s.cancelled = true;
        }
    }

    pub fn is_cancelled(&self, id: u64) -> bool {
        self.table.lock().unwrap().get(&id).is_some_and(|s| s.cancelled)
    }

    pub fn status(&self, id: u64) -> Option<JobStatus> {
        self.table.lock().unwrap().get(&id).cloned()
    }
}
