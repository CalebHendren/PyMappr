//! Render the base map in every projection to PNGs, for eyeballing.
//!
//! cargo run -p mappr-core --example preview --release -- <data/shapes dir> <out dir>

use std::time::Instant;

use mappr_core::basemap::Basemap;
use mappr_core::export::render_png;
use mappr_core::projection::{ProjectionSpec, projection_names};
use mappr_core::render::{RenderRequest, render};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let basemap = Basemap::new(&args[1]);
    let out = std::path::Path::new(&args[2]);
    for name in projection_names() {
        let t = Instant::now();
        let req = RenderRequest {
            projection: ProjectionSpec { name: name.into(), lon_0: None, lat_0: None },
            view: None,
            px_width: 900.0,
            layers: ["land", "lakes", "rivers", "countries", "graticule"].map(String::from).to_vec(),
            graticule: 15.0,
        };
        let map = render(&basemap, &req).unwrap();
        let e = map.extent;
        let size: usize = map.layers.iter().map(|l| l.d.len()).sum();
        let style = |id: &str| match id {
            "land" => "fill:#f0ece1;stroke:none",
            "lakes" => "fill:#a6cae0;stroke:#2d5f8a",
            "rivers" => "fill:none;stroke:#4a90c4",
            "countries" => "fill:none;stroke:#000",
            _ => "fill:none;stroke:#787878;opacity:0.7",
        };
        // Stroke widths are in map units: one pixel is k units.
        let k = e.w / 900.0;
        let width = |id: &str| match id {
            "countries" => 0.8,
            "lakes" => 0.6,
            "rivers" => 0.5,
            "land" => 0.0,
            _ => 0.4,
        };
        let mut svg = format!(
            r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="{} {} {} {}" width="900" height="{}"><path d="{}" style="fill:#d4e6f4;stroke:none"/>"#,
            e.x, e.y, e.w, e.h, (900.0 * e.h / e.w).round(), map.outline
        );
        for l in &map.layers {
            svg += &format!(r#"<path d="{}" style="{}" stroke-width="{}" fill-rule="evenodd"/>"#, l.d, style(&l.id), k * width(&l.id));
        }
        svg += &format!(r#"<path d="{}" style="fill:none;stroke:#333" stroke-width="{}"/></svg>"#, map.outline, k);
        let elapsed = t.elapsed();
        let png = render_png(&svg, 900, 96.0).unwrap();
        let file = out.join(format!("{}.png", name.replace([':', ' ', '(', ')', '.'], "_")));
        std::fs::write(&file, png).unwrap();
        println!("{name:28} {:>8} bytes of paths, {} res, {elapsed:?} {:?}", size, map.resolution, map.missing);
    }
}
