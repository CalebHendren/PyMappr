//! Natural Earth base layers, read from the shapefiles PyMappr downloads
//! (`data/shapes/<stem>/<stem>.shp`) and kept in memory once loaded.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use shapefile::Shape;

#[derive(Debug, thiserror::Error)]
pub enum BasemapError {
    #[error("no Natural Earth data for '{layer}' in {dir}")]
    Missing { layer: String, dir: String },
    #[error("could not read {path}: {message}")]
    Read { path: String, message: String },
    #[error("unknown layer '{0}'")]
    UnknownLayer(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Geometry {
    Polygon,
    Line,
}

/// One ring or line, in longitude/latitude, with its bounding box.
#[derive(Debug, Clone)]
pub struct Part {
    pub points: Vec<[f64; 2]>,
    pub bbox: [f64; 4], // min lon, min lat, max lon, max lat
}

#[derive(Debug)]
pub struct Layer {
    pub geometry: Geometry,
    pub parts: Vec<Part>,
}

/// Natural Earth scales, coarsest first.
pub const RESOLUTIONS: [&str; 3] = ["110m", "50m", "10m"];

struct LayerSpec {
    id: &'static str,
    geometry: Geometry,
    /// Shapefile stem without the "ne_<res>_" prefix.
    stem: &'static str,
    /// Scales Natural Earth publishes this layer at.
    scales: &'static [&'static str],
}

const LAYERS: &[LayerSpec] = &[
    LayerSpec { id: "land", geometry: Geometry::Polygon, stem: "land", scales: &RESOLUTIONS },
    LayerSpec { id: "lakes", geometry: Geometry::Polygon, stem: "lakes", scales: &RESOLUTIONS },
    LayerSpec {
        id: "rivers",
        geometry: Geometry::Line,
        stem: "rivers_lake_centerlines",
        scales: &RESOLUTIONS,
    },
    LayerSpec {
        id: "countries",
        geometry: Geometry::Polygon,
        stem: "admin_0_countries",
        scales: &RESOLUTIONS,
    },
    LayerSpec {
        id: "states",
        geometry: Geometry::Polygon,
        stem: "admin_1_states_provinces",
        scales: &["10m"],
    },
];

pub fn layer_ids() -> Vec<&'static str> {
    LAYERS.iter().map(|l| l.id).collect()
}

/// The Natural Earth scale for a zoom level (1 = whole map in view), with
/// PyMappr's thresholds.
pub fn resolution_for_zoom(zoom: f64) -> &'static str {
    if zoom < 1.0 {
        "110m"
    } else if zoom < 3.5 {
        "50m"
    } else {
        "10m"
    }
}

pub struct Basemap {
    data_dir: PathBuf,
    cache: Mutex<HashMap<String, Arc<Layer>>>,
}

impl Basemap {
    pub fn new(data_dir: impl Into<PathBuf>) -> Self {
        Basemap { data_dir: data_dir.into(), cache: Mutex::new(HashMap::new()) }
    }

    pub fn data_dir(&self) -> &Path {
        &self.data_dir
    }

    fn shapefile(&self, stem: &str) -> PathBuf {
        self.data_dir.join(stem).join(format!("{stem}.shp"))
    }

    /// Whether the folder looks like PyMappr's `data/shapes`.
    pub fn looks_valid(dir: &Path) -> bool {
        dir.join("ne_110m_land").join("ne_110m_land.shp").is_file()
            || dir.join("ne_10m_land").join("ne_10m_land.shp").is_file()
    }

    /// Load a layer at the wanted scale, falling back to the nearest scale
    /// that is on disk (finer first). Returns the layer and the scale used.
    pub fn layer(&self, id: &str, wanted: &str) -> Result<(Arc<Layer>, &'static str), BasemapError> {
        let spec = LAYERS.iter().find(|l| l.id == id).ok_or_else(|| BasemapError::UnknownLayer(id.into()))?;
        let want = RESOLUTIONS.iter().position(|r| *r == wanted).unwrap_or(1);
        let mut order: Vec<usize> = (want..RESOLUTIONS.len()).collect();
        order.extend((0..want).rev());
        for i in order {
            let res = RESOLUTIONS[i];
            if !spec.scales.contains(&res) {
                continue;
            }
            let stem = format!("ne_{res}_{}", spec.stem);
            if let Some(layer) = self.cache.lock().unwrap().get(&stem) {
                return Ok((layer.clone(), res));
            }
            let path = self.shapefile(&stem);
            if !path.is_file() {
                continue;
            }
            let layer = Arc::new(read_layer(&path, spec.geometry)?);
            self.cache.lock().unwrap().insert(stem, layer.clone());
            return Ok((layer, res));
        }
        Err(BasemapError::Missing { layer: id.into(), dir: self.data_dir.display().to_string() })
    }
}

fn part(points: Vec<[f64; 2]>) -> Part {
    let mut bbox = [f64::MAX, f64::MAX, f64::MIN, f64::MIN];
    for p in &points {
        bbox[0] = bbox[0].min(p[0]);
        bbox[1] = bbox[1].min(p[1]);
        bbox[2] = bbox[2].max(p[0]);
        bbox[3] = bbox[3].max(p[1]);
    }
    Part { points, bbox }
}

fn read_layer(path: &Path, geometry: Geometry) -> Result<Layer, BasemapError> {
    let shapes = shapefile::read_shapes(path).map_err(|e| BasemapError::Read {
        path: path.display().to_string(),
        message: e.to_string(),
    })?;
    let mut parts = Vec::new();
    let xy = |pts: &[shapefile::Point]| pts.iter().map(|p| [p.x, p.y]).collect::<Vec<_>>();
    for shape in shapes {
        match shape {
            Shape::Polygon(poly) => {
                parts.extend(poly.rings().iter().map(|r| part(xy(r.points()))));
            }
            Shape::Polyline(line) => {
                parts.extend(line.parts().iter().map(|p| part(xy(p))));
            }
            Shape::PolygonZ(poly) => parts.extend(
                poly.rings().iter().map(|r| part(r.points().iter().map(|p| [p.x, p.y]).collect())),
            ),
            Shape::PolylineZ(line) => parts.extend(
                line.parts().iter().map(|p| part(p.iter().map(|p| [p.x, p.y]).collect())),
            ),
            _ => {}
        }
    }
    parts.retain(|p| p.points.len() >= 2);
    Ok(Layer { geometry, parts })
}
