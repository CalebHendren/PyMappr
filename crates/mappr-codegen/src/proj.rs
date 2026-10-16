//! What the scripts need to know about a projection (PyMappr's
//! `get_projection`): its proj4 string, usable latitude band, centre and
//! projected world bounds.
//!
//! At a projection's default centre the bounds are pyproj's own, from
//! tables.json, so the scripts match PyMappr's to the last digit. A custom
//! globe or Lambert centre is projected here with mappr-core's formulas,
//! which agree with PROJ to well under a metre but not always in the sixth
//! decimal place the scripts print.

use mappr_core::projection::{Projection as CoreProjection, ProjectionSpec};

use crate::lit::float_repr;
use crate::tables::tables;

pub const GLOBE: &str = "Globe (Orthographic)";
const HORIZON_RADIUS: f64 = 89.9;

#[derive(Debug, Clone)]
pub struct ProjInfo {
    pub name: String,
    pub crs: Option<String>,
    pub bounds: [f64; 4],
    pub max_lat: f64,
    pub min_lat: f64,
    pub lon_0: f64,
    pub lat_0: f64,
    pub lon_halfspan: f64,
    pub hemisphere: bool,
}

/// The Lambert presets' parameters: (lcc?, default lon_0, lat_0, lat_1,
/// lat_2, lon half-span, lat min, lat max), as in PyMappr.
/// (lcc?, lon_0, lat_0, lat_1, lat_2, lon half-span, lat min, lat max).
type LambertDef = (bool, f64, f64, f64, f64, f64, f64, f64);

fn lambert_def(name: &str) -> Option<LambertDef> {
    Some(match name {
        "Lambert: N. America" => (true, -96.0, 40.0, 20.0, 60.0, 90.0, 7.0, 84.0),
        "Lambert: Europe" => (true, 10.0, 52.0, 35.0, 65.0, 55.0, 30.0, 72.0),
        "Lambert: Asia" => (true, 95.0, 30.0, 15.0, 65.0, 90.0, -12.0, 78.0),
        "Lambert: S. America" => (true, -60.0, -32.0, -5.0, -42.0, 55.0, -58.0, 14.0),
        "Lambert: Africa" => (false, 20.0, 5.0, 0.0, 0.0, 60.0, -38.0, 40.0),
        "Lambert Azimuthal (custom)" => (false, 0.0, 0.0, 0.0, 0.0, 120.0, -88.0, 88.0),
        _ => return None,
    })
}

fn normalize_origin(lon: f64, lat: f64) -> (f64, f64) {
    let lon = if (-180.0..=180.0).contains(&lon) { lon } else { (lon + 180.0).rem_euclid(360.0) - 180.0 };
    (lon, lat.clamp(-90.0, 90.0))
}

fn or_default(value: Option<f64>, default: f64) -> f64 {
    value.filter(|v| v.is_finite()).unwrap_or(default)
}

fn core(name: &str, lon_0: f64, lat_0: f64) -> Option<CoreProjection> {
    CoreProjection::new(&ProjectionSpec { name: name.into(), lon_0: Some(lon_0), lat_0: Some(lat_0) }).ok()
}

fn linspace(a: f64, b: f64, n: usize) -> impl Iterator<Item = f64> {
    (0..n).map(move |i| if i + 1 == n { b } else { a + (b - a) * i as f64 / (n - 1) as f64 })
}

fn bbox(points: impl Iterator<Item = Option<(f64, f64)>>) -> Option<[f64; 4]> {
    let mut b = [f64::INFINITY, f64::NEG_INFINITY, f64::INFINITY, f64::NEG_INFINITY];
    let mut any = false;
    for (x, y) in points.flatten().filter(|(x, y)| x.is_finite() && y.is_finite()) {
        any = true;
        b = [b[0].min(x), b[1].max(x), b[2].min(y), b[3].max(y)];
    }
    any.then_some(b)
}

/// The densified edges of a lon/lat box, as PyMappr samples them.
fn box_edges(lon0: f64, lon1: f64, lat0: f64, lat1: f64, n: usize) -> Vec<(f64, f64)> {
    let mut points = Vec::with_capacity(4 * n);
    points.extend(linspace(lon0, lon1, n).map(|lon| (lon, lat0)));
    points.extend(linspace(lon0, lon1, n).map(|lon| (lon, lat1)));
    points.extend(linspace(lat0, lat1, n).map(|lat| (lon0, lat)));
    points.extend(linspace(lat0, lat1, n).map(|lat| (lon1, lat)));
    points
}

fn cap_ring(lon_0: f64, lat_0: f64, radius: f64, n: usize) -> Vec<(f64, f64)> {
    let phi0 = lat_0.to_radians();
    let r = radius.to_radians();
    linspace(0.0, 2.0 * std::f64::consts::PI, n)
        .map(|az| {
            let lat = (phi0.sin() * r.cos() + phi0.cos() * r.sin() * az.cos()).asin();
            let dlon = (az.sin() * r.sin() * phi0.cos()).atan2(r.cos() - phi0.sin() * lat.sin());
            (lon_0 + dlon.to_degrees(), lat.to_degrees())
        })
        .collect()
}

/// Python's `str(float)` inside a proj4 string.
fn pf(v: f64) -> String {
    float_repr(v)
}

impl ProjInfo {
    /// PyMappr's `get_projection(name, lon_0, lat_0)`.
    pub fn get(name: &str, lon_0: Option<f64>, lat_0: Option<f64>) -> Result<ProjInfo, String> {
        let t = tables();
        let def = t.projections.get(name).ok_or_else(|| format!("Unknown projection: {name:?}"))?;
        let from_table = || ProjInfo {
            name: name.into(),
            crs: def.crs.clone(),
            bounds: def.bounds,
            max_lat: def.max_lat,
            min_lat: def.min_lat,
            lon_0: def.lon_0,
            lat_0: def.lat_0,
            lon_halfspan: def.lon_halfspan,
            hemisphere: def.hemisphere,
        };
        if name == GLOBE {
            let (lon0, lat0) = normalize_origin(or_default(lon_0, 0.0), or_default(lat_0, 0.0));
            if lon0 == def.lon_0 && lat0 == def.lat_0 {
                return Ok(from_table());
            }
            let crs = format!("+proj=ortho +lat_0={} +lon_0={} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs", pf(lat0), pf(lon0));
            let p = core(name, lon0, lat0).ok_or("globe")?;
            let bounds = bbox(cap_ring(lon0, lat0, HORIZON_RADIUS, 361).into_iter().map(|(x, y)| p.forward(x, y)))
                .unwrap_or(def.bounds);
            return Ok(ProjInfo {
                name: name.into(),
                crs: Some(crs),
                bounds,
                max_lat: 90.0,
                min_lat: -90.0,
                lon_0: lon0,
                lat_0: lat0,
                lon_halfspan: 180.0,
                hemisphere: true,
            });
        }
        if let Some((lcc, dlon, dlat, lat1, lat2, half, lat_min, lat_max)) = lambert_def(name) {
            let (lon0, lat0) = normalize_origin(or_default(lon_0, dlon), or_default(lat_0, dlat));
            if lon0 == def.lon_0 && lat0 == dlat {
                return Ok(from_table());
            }
            let crs = if lcc {
                format!(
                    "+proj=lcc +lat_1={} +lat_2={} +lat_0={} +lon_0={} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs",
                    pf(lat1),
                    pf(lat2),
                    pf(lat0),
                    pf(lon0)
                )
            } else {
                format!("+proj=laea +lat_0={} +lon_0={} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs", pf(lat0), pf(lon0))
            };
            let p = core(name, lon0, lat0).ok_or("lambert")?;
            let bounds = bbox(
                box_edges(lon0 - half, lon0 + half, lat_min, lat_max, 60).into_iter().map(|(x, y)| p.forward(x, y)),
            )
            .unwrap_or(def.bounds);
            return Ok(ProjInfo {
                name: name.into(),
                crs: Some(crs),
                bounds,
                max_lat: lat_max,
                min_lat: lat_min,
                lon_0: lon0,
                lat_0: 0.0,
                lon_halfspan: half,
                hemisphere: false,
            });
        }
        Ok(from_table())
    }

    pub fn world_width(&self) -> f64 {
        self.bounds[1] - self.bounds[0]
    }

    fn forward_clamped(&self, p: &CoreProjection, lon: f64, lat: f64) -> Option<(f64, f64)> {
        if self.crs.is_none() {
            return Some((lon, lat));
        }
        let mut lon = lon;
        let regional = self.lon_halfspan < 180.0;
        if regional {
            lon = self.lon_0 + (lon - self.lon_0 + 180.0).rem_euclid(360.0) - 180.0;
            lon = lon.clamp(self.lon_0 - self.lon_halfspan, self.lon_0 + self.lon_halfspan);
        }
        let lat = lat.clamp(self.min_lat, self.max_lat);
        p.forward(lon, lat)
    }

    /// `Projection.project_extent`: a lon/lat box's projected bbox.
    pub fn project_extent(&self, extent: [f64; 4]) -> [f64; 4] {
        let [x0, x1, y0, y1] = extent;
        if self.crs.is_none() {
            return extent;
        }
        let seam = self.lon_0 + 180.0;
        if !self.hemisphere && self.lon_halfspan >= 180.0 && x1 > seam {
            let west = self.project_extent([x0, seam - 1e-9, y0, y1]);
            let east = self.project_extent([seam - 360.0 + 1e-9, x1 - 360.0, y0, y1]);
            return [west[0], east[1] + self.world_width(), west[2].min(east[2]), west[3].max(east[3])];
        }
        let Some(p) = core(&self.name, self.lon_0, if self.hemisphere { self.lat_0 } else { self.lat_0_for_core() })
        else {
            return self.bounds;
        };
        let (y0, y1) = (y0.max(self.min_lat), y1.min(self.max_lat));
        let n = 40;
        let points: Vec<(f64, f64)> = if self.hemisphere {
            let lats: Vec<f64> = linspace(y0, y1, n).collect();
            lats.iter().flat_map(|lat| linspace(x0, x1, n).map(move |lon| (lon, *lat))).collect()
        } else {
            box_edges(x0, x1, y0, y1, n)
        };
        bbox(points.into_iter().map(|(lon, lat)| self.forward_clamped(&p, lon, lat))).unwrap_or(self.bounds)
    }

    /// mappr-core's Lambert takes the latitude of origin; the Lambert
    /// ProjInfo keeps PyMappr's `lat_0` (0) so recover it from the crs.
    fn lat_0_for_core(&self) -> f64 {
        self.crs
            .as_deref()
            .and_then(|crs| crs.split_whitespace().find_map(|p| p.strip_prefix("+lat_0=")))
            .and_then(|v| v.parse().ok())
            .unwrap_or(self.lat_0)
    }
}
