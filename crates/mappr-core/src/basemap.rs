//! Natural Earth layers, read from the shapefiles PyMappr downloads
//! (`data/shapes/<dir>/<dir>.shp`) with the attributes PyMappr reads, plus
//! the layers derived from them, all kept in memory once loaded.
//! `Basemap` is given the `data` folder.

use std::any::Any;
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use shapefile::dbase::FieldValue;
use shapefile::{PolygonRing, Shape};

pub use crate::catalog::Geometry;
use crate::catalog::{self, BATHYMETRY_STEPS, MARITIME_200NM, layer_spec};

#[derive(Debug, thiserror::Error)]
pub enum BasemapError {
    #[error("no map data for '{layer}' in {dir}")]
    Missing { layer: String, dir: String },
    #[error("could not read {path}: {message}")]
    Read { path: String, message: String },
    #[error("unknown layer '{0}'")]
    UnknownLayer(String),
}

/// One ring, line or point, in longitude/latitude, with its bounding box.
#[derive(Debug, Clone)]
pub struct Part {
    pub points: Vec<[f64; 2]>,
    pub bbox: [f64; 4], // min lon, min lat, max lon, max lat
    /// A polygon hole (an inner ring).
    pub hole: bool,
}

impl Part {
    pub fn new(points: Vec<[f64; 2]>, hole: bool) -> Part {
        Part { bbox: bbox_of(&points), points, hole }
    }
}

pub fn bbox_of(points: &[[f64; 2]]) -> [f64; 4] {
    let mut b = [f64::MAX, f64::MAX, f64::MIN, f64::MIN];
    for p in points {
        b = [b[0].min(p[0]), b[1].min(p[1]), b[2].max(p[0]), b[3].max(p[1])];
    }
    b
}

/// The attribute columns PyMappr keeps (`_KEEP_COLUMNS`), plus the ISO
/// codes the districts need.
#[derive(Debug, Clone, Default)]
pub struct Attrs {
    pub name: Option<String>,
    pub featurecla: Option<String>,
    pub kind: Option<String>,
    pub continent: Option<String>,
    pub time_zone: Option<String>,
    pub adm0_a3: Option<String>,
    pub iso_a3: Option<String>,
    pub adm0cap: Option<f64>,
    pub min_zoom: Option<f64>,
    pub min_label: Option<f64>,
    pub scalerank: Option<f64>,
}

impl Attrs {
    /// A text column by its (lower-case) name.
    pub fn text(&self, column: &str) -> Option<&str> {
        match column {
            "name" => self.name.as_deref(),
            "time_zone" => self.time_zone.as_deref(),
            "featurecla" => self.featurecla.as_deref(),
            "continent" => self.continent.as_deref(),
            _ => None,
        }
    }

    /// The country's ISO3 code: `iso_a3` when it is one, else `adm0_a3`.
    pub fn iso3(&self) -> Option<&str> {
        let valid = |s: &&str| s.len() == 3 && s.bytes().all(|b| b.is_ascii_alphabetic());
        self.iso_a3.as_deref().filter(valid).or(self.adm0_a3.as_deref().filter(valid))
    }
}

#[derive(Debug, Clone)]
pub struct Feature {
    pub parts: Vec<Part>,
    pub bbox: [f64; 4],
    pub attrs: Attrs,
}

impl Feature {
    pub fn new(parts: Vec<Part>, attrs: Attrs) -> Feature {
        let mut bbox = [f64::MAX, f64::MAX, f64::MIN, f64::MIN];
        for p in &parts {
            bbox = [bbox[0].min(p.bbox[0]), bbox[1].min(p.bbox[1]), bbox[2].max(p.bbox[2]), bbox[3].max(p.bbox[3])];
        }
        Feature { parts, bbox, attrs }
    }

    /// The polygons of a polygon feature: each an outer ring followed by
    /// its holes, as the shapefile stores them.
    pub fn polygons(&self) -> Vec<Vec<&Part>> {
        let mut out: Vec<Vec<&Part>> = Vec::new();
        for part in &self.parts {
            match out.last_mut() {
                Some(poly) if part.hole => poly.push(part),
                _ => out.push(vec![part]),
            }
        }
        out
    }
}

#[derive(Debug)]
pub struct Layer {
    pub geometry: Geometry,
    pub features: Vec<Feature>,
    /// Where it came from (a directory, or a derived layer's key): the key
    /// projected copies are cached under.
    pub source: String,
}

/// Natural Earth scales, coarsest first.
pub const RESOLUTIONS: [&str; 3] = ["110m", "50m", "10m"];

/// The scale named in a Natural Earth directory ("ne_50m_land" -> "50m").
pub fn scale_of(directory: &str) -> Option<&'static str> {
    RESOLUTIONS.iter().copied().find(|r| directory.starts_with(&format!("ne_{r}_")))
}

/// Entries kept in the bounded caches (projected layers and the like): a
/// few projections' worth, as a globe spin makes a new one every step.
const LRU_SIZE: usize = 64;

type Shared = Arc<dyn Any + Send + Sync>;

pub struct Basemap {
    data_dir: PathBuf,
    layers: Mutex<HashMap<String, Arc<Layer>>>,
    cache: Mutex<HashMap<String, Shared>>,
    lru: Mutex<VecDeque<(String, Shared)>>,
}

impl Basemap {
    pub fn new(data_dir: impl Into<PathBuf>) -> Self {
        Basemap {
            data_dir: data_dir.into(),
            layers: Mutex::default(),
            cache: Mutex::default(),
            lru: Mutex::default(),
        }
    }

    /// The data folder: `shapes/` (Natural Earth), `basemap/` (rasters),
    /// `districts/`, laid out as PyMappr's `data` folder is.
    pub fn data_dir(&self) -> &Path {
        &self.data_dir
    }

    pub fn shapes_dir(&self) -> PathBuf {
        self.data_dir.join("shapes")
    }

    /// Whether the folder looks like PyMappr's `data/shapes`.
    pub fn looks_valid(dir: &Path) -> bool {
        dir.join("ne_110m_land").join("ne_110m_land.shp").is_file()
            || dir.join("ne_10m_land").join("ne_10m_land.shp").is_file()
    }

    fn shapefile_path(&self, directory: &str, member: Option<&str>) -> PathBuf {
        let name = member.unwrap_or(directory);
        self.shapes_dir().join(directory).join(format!("{name}.shp"))
    }

    /// Whether the shapefile behind a layer key is on disk (any scale).
    pub fn has_layer_data(&self, key: &str) -> bool {
        match layer_spec(key) {
            Some(spec) => spec.directories().iter().any(|d| self.shapefile_path(d, spec.shapefile).is_file()),
            None => true,
        }
    }

    /// The directory a layer is drawn from at `zoom` (None = its default
    /// scale): the one the zoom calls for, else the nearest scale on disk,
    /// finer first.
    pub fn directory(&self, key: &str, zoom: Option<f64>) -> Option<&'static str> {
        let spec = layer_spec(key)?;
        let wanted = spec.directory_for_zoom(zoom);
        let dirs = spec.directories();
        let at = dirs.iter().position(|d| *d == wanted).unwrap_or(0);
        let mut order: Vec<usize> = vec![at];
        for step in 1..dirs.len() {
            if at + step < dirs.len() {
                order.push(at + step);
            }
            if step <= at {
                order.push(at - step);
            }
        }
        order.into_iter().map(|i| dirs[i]).find(|d| self.shapefile_path(d, spec.shapefile).is_file())
    }

    /// A layer by key: a Natural Earth layer at the scale for `zoom`, a
    /// derived layer (continents, capitals, ...), `bathymetry:<depth>` or
    /// `districts:<ISO3>`.
    pub fn layer(&self, key: &str, zoom: Option<f64>) -> Result<Arc<Layer>, BasemapError> {
        if let Some(depth) = key.strip_prefix("bathymetry:") {
            return self.bathymetry(depth);
        }
        if let Some(iso3) = key.strip_prefix("districts:") {
            return self.districts(iso3);
        }
        if catalog::derived_source(key).is_some() {
            return self.derived(key);
        }
        let spec = layer_spec(key).ok_or_else(|| BasemapError::UnknownLayer(key.into()))?;
        let directory = self.directory(key, zoom).ok_or_else(|| self.missing(key))?;
        self.load(directory, spec.shapefile, spec.geometry)
    }

    fn missing(&self, key: &str) -> BasemapError {
        BasemapError::Missing { layer: key.into(), dir: self.data_dir.display().to_string() }
    }

    fn memo(&self, id: &str, make: impl FnOnce() -> Result<Layer, BasemapError>) -> Result<Arc<Layer>, BasemapError> {
        if let Some(layer) = self.layers.lock().unwrap().get(id) {
            return Ok(layer.clone());
        }
        let layer = Arc::new(make()?);
        self.layers.lock().unwrap().insert(id.to_string(), layer.clone());
        Ok(layer)
    }

    fn load(&self, directory: &str, member: Option<&str>, geometry: Geometry) -> Result<Arc<Layer>, BasemapError> {
        let path = self.shapefile_path(directory, member);
        self.memo(directory, || {
            if !path.is_file() {
                return Err(self.missing(directory));
            }
            Ok(Layer { geometry, features: read_features(&path)?, source: directory.into() })
        })
    }

    fn bathymetry(&self, depth: &str) -> Result<Arc<Layer>, BasemapError> {
        let (letter, depth) = BATHYMETRY_STEPS
            .iter()
            .find(|s| s.1.to_string() == depth)
            .ok_or_else(|| BasemapError::UnknownLayer(format!("bathymetry:{depth}")))?;
        let stem = format!("ne_10m_bathymetry_{letter}_{depth}");
        let path = self.shapes_dir().join("ne_10m_bathymetry_all").join(format!("{stem}.shp"));
        self.memo(&stem, || {
            if !path.is_file() {
                return Err(self.missing("bathymetry"));
            }
            Ok(Layer { geometry: Geometry::Polygon, features: read_features(&path)?, source: stem.clone() })
        })
    }

    fn districts(&self, iso3: &str) -> Result<Arc<Layer>, BasemapError> {
        let path = crate::districts::geojson_path(&self.data_dir, iso3);
        let stamp = std::fs::metadata(&path)
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_millis())
            .ok_or_else(|| self.missing(&format!("districts:{iso3}")))?;
        let id = format!("districts:{}@{stamp}", iso3.to_ascii_uppercase());
        self.memo(&id, || {
            let districts = crate::districts::load(&path)
                .map_err(|e| BasemapError::Read { path: path.display().to_string(), message: e.to_string() })?;
            let features = districts
                .into_iter()
                .map(|d| {
                    let parts = d
                        .polygons
                        .into_iter()
                        .flat_map(|rings| rings.into_iter().enumerate().map(|(i, r)| Part::new(r, i > 0)))
                        .collect();
                    Feature::new(parts, Attrs { name: Some(d.name), ..Default::default() })
                })
                .collect();
            Ok(Layer { geometry: Geometry::Polygon, features, source: id.clone() })
        })
    }

    fn derived(&self, key: &str) -> Result<Arc<Layer>, BasemapError> {
        self.memo(key, || {
            let source = catalog::derived_source(key).unwrap();
            if key == "continents" {
                let countries = self.layer(source, None)?;
                return Ok(Layer {
                    geometry: Geometry::Polygon,
                    features: crate::geom::dissolve_by_continent(&countries.features),
                    source: key.into(),
                });
            }
            // Filters need attribute detail: the source's finest scale
            // (10m rivers carry the intermittent flag, and so on).
            let spec = layer_spec(source).unwrap();
            let finest = *spec.directories().last().unwrap();
            let directory = if self.shapefile_path(finest, spec.shapefile).is_file() {
                finest
            } else {
                self.directory(source, None).ok_or_else(|| self.missing(source))?
            };
            let layer = self.load(directory, spec.shapefile, spec.geometry)?;
            let keep = |a: &Attrs| -> bool {
                let cla = a.featurecla.as_deref().unwrap_or("");
                match key {
                    "dependencies" => matches!(a.kind.as_deref(), Some("Dependency" | "Lease")),
                    "deserts" => cla.eq_ignore_ascii_case("desert"),
                    "wadis" => cla == "River (Intermittent)",
                    "capitals" => a.adm0cap == Some(1.0),
                    "maritime" => cla != MARITIME_200NM,
                    "eez" => cla == MARITIME_200NM,
                    _ => false,
                }
            };
            Ok(Layer {
                geometry: spec.geometry,
                features: layer.features.iter().filter(|f| keep(&f.attrs)).cloned().collect(),
                source: key.into(),
            })
        })
    }

    /// A value computed once per key and kept (label anchors, rasters).
    pub fn cached<T: Any + Send + Sync>(&self, key: &str, make: impl FnOnce() -> T) -> Arc<T> {
        if let Some(v) = self.cache.lock().unwrap().get(key).cloned().and_then(|v| v.downcast::<T>().ok()) {
            return v;
        }
        let value = Arc::new(make());
        self.cache.lock().unwrap().insert(key.to_string(), value.clone());
        value
    }

    /// Like [`Self::cached`], but only the most recently used entries are
    /// kept: for values per projection.
    pub fn cached_lru<T: Any + Send + Sync>(&self, key: &str, make: impl FnOnce() -> T) -> Arc<T> {
        {
            let mut lru = self.lru.lock().unwrap();
            if let Some(i) = lru.iter().position(|(k, _)| k == key) {
                let entry = lru.remove(i).unwrap();
                lru.push_back(entry.clone());
                if let Ok(v) = entry.1.downcast::<T>() {
                    return v;
                }
            }
        }
        let value = Arc::new(make());
        let mut lru = self.lru.lock().unwrap();
        lru.retain(|(k, _)| k != key);
        lru.push_back((key.to_string(), value.clone()));
        while lru.len() > LRU_SIZE {
            lru.pop_front();
        }
        value
    }
}

fn read_features(path: &Path) -> Result<Vec<Feature>, BasemapError> {
    let fail = |e: shapefile::Error| BasemapError::Read { path: path.display().to_string(), message: e.to_string() };
    let mut reader = shapefile::Reader::from_path(path).map_err(fail)?;
    let mut features = Vec::new();
    for item in reader.iter_shapes_and_records() {
        let (shape, record) = item.map_err(fail)?;
        let mut parts = Vec::new();
        let xy = |pts: &[shapefile::Point]| pts.iter().map(|p| [p.x, p.y]).collect::<Vec<_>>();
        let xyz = |pts: &[shapefile::PointZ]| pts.iter().map(|p| [p.x, p.y]).collect::<Vec<_>>();
        match shape {
            Shape::Polygon(poly) => {
                for ring in poly.rings() {
                    let hole = matches!(ring, PolygonRing::Inner(_));
                    parts.push(Part::new(xy(ring.points()), hole));
                }
            }
            Shape::PolygonZ(poly) => {
                for ring in poly.rings() {
                    let hole = matches!(ring, PolygonRing::Inner(_));
                    parts.push(Part::new(xyz(ring.points()), hole));
                }
            }
            Shape::Polyline(line) => parts.extend(line.parts().iter().map(|p| Part::new(xy(p), false))),
            Shape::PolylineZ(line) => parts.extend(line.parts().iter().map(|p| Part::new(xyz(p), false))),
            Shape::Point(p) => parts.push(Part::new(vec![[p.x, p.y]], false)),
            Shape::PointZ(p) => parts.push(Part::new(vec![[p.x, p.y]], false)),
            Shape::Multipoint(mp) => parts.extend(mp.points().iter().map(|p| Part::new(vec![[p.x, p.y]], false))),
            _ => {}
        }
        if parts.is_empty() {
            continue;
        }
        let mut attrs = Attrs::default();
        for (field, value) in record {
            let text = || match &value {
                FieldValue::Character(Some(s)) => Some(s.trim().to_string()),
                FieldValue::Memo(s) => Some(s.trim().to_string()),
                _ => None,
            };
            let number = || match &value {
                FieldValue::Numeric(v) => *v,
                FieldValue::Float(v) => v.map(f64::from),
                FieldValue::Double(v) => Some(*v),
                FieldValue::Integer(v) => Some(f64::from(*v)),
                FieldValue::Character(Some(s)) => s.trim().parse().ok(),
                _ => None,
            };
            match field.to_ascii_lowercase().as_str() {
                "name" => attrs.name = text(),
                "featurecla" => attrs.featurecla = text(),
                "type" => attrs.kind = text(),
                "continent" => attrs.continent = text(),
                "time_zone" => attrs.time_zone = text(),
                "adm0_a3" => attrs.adm0_a3 = text(),
                "iso_a3" => attrs.iso_a3 = text(),
                "adm0cap" => attrs.adm0cap = number(),
                "min_zoom" => attrs.min_zoom = number(),
                "min_label" => attrs.min_label = number(),
                "scalerank" => attrs.scalerank = number(),
                _ => {}
            }
        }
        features.push(Feature::new(parts, attrs));
    }
    Ok(features)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn data() -> Option<Basemap> {
        let dir = crate::pymappr_dir().join("data");
        Basemap::looks_valid(&dir.join("shapes")).then(|| Basemap::new(dir))
    }

    #[test]
    fn resolution_falls_back_to_the_nearest_scale_on_disk() {
        let Some(b) = data() else { return };
        assert_eq!(b.directory("countries", Some(0.0)), Some("ne_110m_admin_0_countries"));
        assert_eq!(b.directory("countries", Some(5.0)), Some("ne_10m_admin_0_countries"));
        let empty = Basemap::new(std::env::temp_dir().join("no-such-natural-earth"));
        assert_eq!(empty.directory("countries", Some(5.0)), None);
        assert!(matches!(empty.layer("land", None), Err(BasemapError::Missing { .. })));
    }

    #[test]
    fn attributes_are_read() {
        let Some(b) = data() else { return };
        let countries = b.layer("countries", None).unwrap();
        let france = countries.features.iter().find(|f| f.attrs.name.as_deref() == Some("France")).unwrap();
        assert_eq!(france.attrs.continent.as_deref(), Some("Europe"));
        assert_eq!(france.attrs.iso3(), Some("FRA"));
        assert!(france.attrs.min_label.is_some());
    }

    #[test]
    fn derived_layers_filter_their_source() {
        let Some(b) = data() else { return };
        let capitals = b.layer("capitals", None).unwrap();
        assert!(capitals.features.len() > 150 && capitals.features.len() < 300, "{}", capitals.features.len());
        assert!(capitals.features.iter().any(|f| f.attrs.name.as_deref() == Some("Paris")));
        let deps = b.layer("dependencies", None).unwrap();
        assert!(deps.features.iter().all(|f| matches!(f.attrs.kind.as_deref(), Some("Dependency" | "Lease"))));
        assert!(!deps.features.is_empty());
        let wadis = b.layer("wadis", None).unwrap();
        assert!(!wadis.features.is_empty());
        let deserts = b.layer("deserts", None).unwrap();
        assert!(!deserts.features.is_empty());
        let eez = b.layer("eez", None).unwrap();
        let maritime = b.layer("maritime", None).unwrap();
        let all = b.layer("maritime_all", None).unwrap();
        assert_eq!(eez.features.len() + maritime.features.len(), all.features.len());
        assert!(!eez.features.is_empty());
    }

    #[test]
    fn continents_dissolve_the_countries() {
        let Some(b) = data() else { return };
        let continents = b.layer("continents", None).unwrap();
        let names: Vec<_> = continents.features.iter().filter_map(|f| f.attrs.name.clone()).collect();
        for want in ["Africa", "Europe", "South America", "Oceania"] {
            assert!(names.iter().any(|n| n == want), "{names:?}");
        }
        // Africa as one outline: far fewer rings than its countries have.
        let africa = continents.features.iter().find(|f| f.attrs.name.as_deref() == Some("Africa")).unwrap();
        let countries = b.layer("countries", None).unwrap();
        let rings: usize = countries
            .features
            .iter()
            .filter(|f| f.attrs.continent.as_deref() == Some("Africa"))
            .map(|f| f.parts.len())
            .sum();
        assert!(africa.parts.len() < rings / 2, "{} vs {rings}", africa.parts.len());
    }

    #[test]
    fn bathymetry_and_optional_layers() {
        let Some(b) = data() else { return };
        for (_, depth) in BATHYMETRY_STEPS {
            assert!(!b.layer(&format!("bathymetry:{depth}"), None).unwrap().features.is_empty());
        }
        assert!(b.has_layer_data("biodiversity"));
        assert!(!b.has_layer_data("marine_ecoregions"));
    }

    #[test]
    fn lru_cache_forgets_the_least_recently_used_entry() {
        let b = Basemap::new(".");
        for i in 0..LRU_SIZE + 5 {
            b.cached_lru(&format!("k{i}"), || i);
        }
        let mut made = false;
        b.cached_lru("k0", || {
            made = true;
            0usize
        });
        assert!(made);
        let mut made = false;
        b.cached_lru(&format!("k{}", LRU_SIZE + 4), || {
            made = true;
            0usize
        });
        assert!(!made);
    }
}
