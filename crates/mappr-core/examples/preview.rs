//! Render the base map in every projection to PNGs, for eyeballing, and
//! print how long each render took.
//!
//! cargo run -p mappr-core --example preview --release -- <data dir> <out dir> [basemap]
//!
//! `<data dir>` is PyMappr's `data` folder (holding `shapes/`); `basemap`
//! is "simple" (default) or a raster mode such as "relief".

use std::time::Instant;

use mappr_core::basemap::Basemap;
use mappr_core::export::render_png;
use mappr_core::projection::{Projection, ProjectionSpec, projection_names};
use mappr_core::render::{LayerSettings, Rect, RenderRequest, RenderedMap, render};
use mappr_core::view::extent_view;

const WIDTH: f64 = 900.0;

fn settings(basemap: &str) -> LayerSettings {
    let on = |keys: &[&str]| keys.iter().map(|k| (k.to_string(), true)).collect();
    LayerSettings {
        lines: on(&["countries", "rivers", "lakes_outline"]),
        fills: on(&["land"]),
        points: on(&["cities"]),
        labels: on(&["countries", "cities"]),
        ocean: "blue".into(),
        lake_fill: "blue".into(),
        basemap: basemap.into(),
        graticule: "10°".into(),
        ..Default::default()
    }
}

fn style(id: &str) -> (&'static str, f64) {
    match id {
        "land" => ("fill:#f0ece1;stroke:none", 0.0),
        "lakes" => ("fill:#a6cae0;stroke:none", 0.0),
        "lakes_outline" => ("fill:none;stroke:#2d5f8a", 0.6),
        "rivers" => ("fill:none;stroke:#4a90c4", 0.5),
        "countries" | "continents" => ("fill:none;stroke:#000", 0.8),
        "states" => ("fill:none;stroke:#5a5a5a", 0.5),
        _ => ("fill:none;stroke:#888", 0.4),
    }
}

fn to_svg(map: &RenderedMap, view: Rect) -> String {
    let k = view.w / WIDTH; // map units per pixel
    let height = (WIDTH * view.h / view.w).round();
    let mut svg = format!(
        r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="{} {} {} {}" width="{WIDTH}" height="{height}"><rect x="{}" y="{}" width="{}" height="{}" fill="#fff"/><path d="{}" fill="#d4e6f4"/>"##,
        view.x, view.y, view.w, view.h, view.x, view.y, view.w, view.h, map.outline
    );
    if let Some(r) = &map.raster {
        svg += &format!(
            r#"<image href="{}" x="{}" y="{}" width="{}" height="{}" preserveAspectRatio="none"/>"#,
            r.href, r.x, r.y, r.w, r.h
        );
    }
    for l in &map.layers {
        let (s, w) = style(&l.id);
        svg += &format!(r#"<path d="{}" style="{s}" stroke-width="{}"/>"#, l.d, k * w);
    }
    if let Some(g) = &map.graticule {
        svg += &format!(r##"<path d="{}" fill="none" stroke="#787878" stroke-opacity="0.7" stroke-width="{}"/>"##, g.d, k * 0.4);
        if let Some(h) = &g.horizon {
            svg += &format!(r##"<path d="{h}" fill="none" stroke="#787878" stroke-width="{}"/>"##, k * 0.8);
        }
        let font = 7.0 * k;
        for t in &g.x_ticks {
            svg += &format!(
                r#"<text x="{}" y="{}" font-size="{font}" text-anchor="middle" font-family="sans-serif">{}</text>"#,
                t.pos,
                view.y + view.h - font * 0.3,
                t.text
            );
        }
        for t in &g.y_ticks {
            svg += &format!(
                r#"<text x="{}" y="{}" font-size="{font}" font-family="sans-serif">{}</text>"#,
                view.x + font * 0.3,
                t.pos,
                t.text
            );
        }
    }
    for m in &map.markers {
        svg += &format!(r##"<circle cx="{}" cy="{}" r="{}" fill="#333"/>"##, m.x, m.y, k * 1.5);
    }
    for l in &map.labels {
        let size = if l.layer == "countries" { 9.0 } else { 7.5 } * l.font_scale * k;
        let dy = if l.va == "bottom" { -size * 0.3 } else { size * 0.35 };
        svg += &format!(
            r##"<text x="{}" y="{}" font-size="{size}" text-anchor="middle" font-family="sans-serif" stroke="#fff" stroke-width="{}" paint-order="stroke">{}</text>"##,
            l.x,
            l.y + dy,
            size * 0.2,
            l.text.replace('&', "&amp;").replace('<', "&lt;")
        );
    }
    svg + &format!(r##"<path d="{}" fill="none" stroke="#333" stroke-width="{k}"/></svg>"##, map.outline)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let basemap = Basemap::new(&args[1]);
    let out = std::path::Path::new(&args[2]);
    let mode = args.get(3).map(String::as_str).unwrap_or("simple");
    let spec = |n: &str| ProjectionSpec { name: n.into(), lon_0: None, lat_0: None };
    let mut views: Vec<(String, ProjectionSpec, Option<[f64; 4]>, f64)> =
        projection_names().into_iter().map(|n| (n.to_string(), spec(n), None, 0.0)).collect();
    // A world map at 50m and 10m detail, as an export at more pixels draws it.
    views.push(("world 50m Robinson".into(), spec("Robinson"), None, 1.5));
    views.push(("world 10m Robinson".into(), spec("Robinson"), None, 4.0));
    views.push(("zoom Alps".into(), spec("Equirectangular"), Some([5.0, 12.0, 44.0, 48.5]), 0.0));
    views.push(("zoom Madagascar Robinson".into(), spec("Robinson"), Some([42.0, 51.0, -26.5, -11.5]), 0.0));
    views.push(("zoom Fiji Mercator".into(), spec("Mercator"), Some([175.0, 191.0, -23.5, -11.0]), 0.0));
    for (name, spec, lonlat, detail_boost) in views {
        let proj = Projection::new(&spec).unwrap();
        let view = extent_view(&proj, lonlat.unwrap_or([-180.0, 180.0, -90.0, 90.0]), 0.6);
        let mut layers = settings(mode);
        if lonlat.is_some() {
            layers.lines.insert("states".into(), true);
            layers.labels.insert("states".into(), true);
        }
        let req = RenderRequest {
            projection: spec,
            view: Some(view),
            px_width: WIDTH,
            px_height: None,
            px_per_pt: 96.0 / 72.0,
            detail_boost,
            layers,
            districts: Vec::new(),
        };
        let t = Instant::now();
        let map = render(&basemap, &req).unwrap();
        let cold = t.elapsed();
        let t = Instant::now();
        let warm_map = render(&basemap, &req).unwrap();
        let warm = t.elapsed();
        let size: usize = warm_map.layers.iter().map(|l| l.d.len()).sum();
        let png = render_png(&to_svg(&map, view), WIDTH as u32, 96.0).unwrap();
        let file = out.join(format!("{}.png", name.replace([':', ' ', '(', ')', '.'], "_")));
        std::fs::write(&file, png).unwrap();
        println!(
            "{name:28} {size:>9} bytes {:>4} {cold:>10.1?} cold {warm:>9.1?} warm, {} labels {:?}",
            map.resolution,
            map.labels.len(),
            map.missing
        );
    }
}
