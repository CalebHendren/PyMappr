//! Map drawing commands: the base map, point projection, cursor read-out,
//! scale bar, inset, framing, and the geoBoundaries districts.

use std::sync::Arc;

use mappr_core::districts;
use mappr_core::inset::{InsetRequest, render_inset};
use mappr_core::overlays::{ScaleBarOptions, scale_bar};
use mappr_core::projection::{Projection, ProjectionSpec};
use mappr_core::regions::countries_in_view;
use mappr_core::render::{self, Rect, RenderRequest};
use mappr_core::view::extent_view;
use serde::Deserialize;
use serde_json::Value;

use crate::core::{CmdResult, Core, err, ok, parse};

pub fn dispatch(core: &Arc<Core>, cmd: &str, args: &Value) -> Option<CmdResult> {
    Some(match cmd {
        "render_map" => render_map(core, args),
        "project_points" => project_points(args),
        "unproject" => unproject(args),
        "scale_bar" => scale_bar_cmd(args),
        "render_inset" => render_inset_cmd(core, args),
        "extent_view" => extent_view_cmd(args),
        "districts_list" => districts_list(core),
        "districts_fetch" => districts_fetch(core, args),
        "districts_remove" => districts_remove(core, args),
        "countries_in_view" => countries_in_view_cmd(core, args),
        _ => return None,
    })
}

fn projection(spec: &ProjectionSpec) -> Result<Projection, String> {
    Projection::new(spec).map_err(err)
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

fn scale_bar_cmd(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct Req {
        projection: ProjectionSpec,
        view: Rect,
        /// The map box in points: the bar is laid out in axes fractions,
        /// so it is not needed for the layout itself.
        #[allow(dead_code)]
        box_pt: Option<Value>,
        options: ScaleBarOptions,
    }
    #[derive(Deserialize)]
    struct A {
        request: Req,
    }
    let a: A = parse(args)?;
    let proj = projection(&a.request.projection)?;
    ok(scale_bar(&proj, a.request.view, &a.request.options))
}

fn render_inset_cmd(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        request: InsetRequest,
    }
    let a: A = parse(args)?;
    let basemap = core.basemap()?;
    ok(render_inset(&basemap, &a.request).map_err(err)?)
}

fn extent_view_cmd(args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        projection: ProjectionSpec,
        /// lon_min, lon_max, lat_min, lat_max
        lonlat: [f64; 4],
        /// Height / width of the map box.
        aspect: f64,
    }
    let a: A = parse(args)?;
    ok(extent_view(&projection(&a.projection)?, a.lonlat, a.aspect))
}

fn districts_list(core: &Arc<Core>) -> CmdResult {
    let basemap = core.basemap()?;
    ok(districts::list(basemap.data_dir()))
}

fn districts_remove(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        iso3: String,
    }
    let a: A = parse(args)?;
    let basemap = core.basemap()?;
    districts::remove(basemap.data_dir(), &a.iso3).map_err(err)?;
    ok(())
}

/// Download districts for several countries in the background; returns
/// the job id the UI polls.
fn districts_fetch(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        iso3: Vec<String>,
    }
    let a: A = parse(args)?;
    let basemap = core.basemap()?;
    let data_dir = basemap.data_dir().to_path_buf();
    let label = format!("Districts for {}", a.iso3.join(", "));
    let id = core.jobs.start(&label);
    let core = core.clone();
    std::thread::spawn(move || {
        let total = a.iso3.len().max(1) as f64;
        let mut failures = Vec::new();
        for (i, code) in a.iso3.iter().enumerate() {
            if core.jobs.is_cancelled(id) {
                failures.push("Cancelled.".to_string());
                break;
            }
            let base = i as f64 / total;
            core.jobs.update(id, &format!("Districts for {code}"), Some(base));
            let mut progress = |step: &str| core.jobs.update(id, step, Some(base));
            if let Err(e) = districts::fetch(&data_dir, code, &mut progress) {
                failures.push(e.to_string());
            }
        }
        core.jobs.finish(id, (!failures.is_empty()).then(|| failures.join("\n")));
    });
    ok(id)
}

fn countries_in_view_cmd(core: &Arc<Core>, args: &Value) -> CmdResult {
    #[derive(Deserialize)]
    struct A {
        projection: ProjectionSpec,
        view: Rect,
    }
    let a: A = parse(args)?;
    let basemap = core.basemap()?;
    ok(countries_in_view(&basemap, &projection(&a.projection)?, a.view))
}
