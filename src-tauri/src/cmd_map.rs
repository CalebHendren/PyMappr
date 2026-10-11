//! Map drawing commands: base layers, point projection, cursor read-out.

use std::sync::Arc;

use mappr_core::projection::ProjectionSpec;
use mappr_core::render::{self, RenderRequest};
use serde::Deserialize;
use serde_json::Value;

use crate::core::{CmdResult, Core, err, ok, parse};

pub fn dispatch(core: &Arc<Core>, cmd: &str, args: &Value) -> Option<CmdResult> {
    Some(match cmd {
        "render_map" => render_map(core, args),
        "project_points" => project_points(args),
        "unproject" => unproject(args),
        _ => return None,
    })
}

fn render_map(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        request: RenderRequest,
    }
    let a: A = parse(args)?;
    let basemap = core.basemap()?;
    ok(render::render(&basemap, &a.request).map_err(err)?)
}

fn project_points(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        projection: ProjectionSpec,
        points: Vec<[f64; 2]>,
    }
    let a: A = parse(args)?;
    ok(render::project_points(&a.projection, &a.points).map_err(err)?)
}

fn unproject(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        projection: ProjectionSpec,
        x: f64,
        y: f64,
    }
    let a: A = parse(args)?;
    ok(render::unproject(&a.projection, a.x, a.y).map_err(err)?)
}
