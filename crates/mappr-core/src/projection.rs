//! Map projections, written out by hand so the app needs no C PROJ library.
//!
//! The set and the parameters follow PyMappr's `pymappr/geo/projections.py`;
//! the formulas follow PROJ (WGS84, metres), so coordinates match what
//! pyproj gives PyMappr. Equirectangular is plain longitude/latitude degrees,
//! as in PyMappr.

use std::f64::consts::{FRAC_PI_2, FRAC_PI_4, PI};

use serde::{Deserialize, Serialize};

const A: f64 = 6_378_137.0;
const F: f64 = 1.0 / 298.257_223_563;
const ES: f64 = F * (2.0 - F);

/// Vector layers on the globe are clipped to a cap just inside the visible
/// hemisphere, so no point sits where the transform blows up.
pub const CAP_CLIP_RADIUS: f64 = 88.0;
/// The drawn globe outline sits just inside the exact horizon.
pub const HORIZON_RADIUS: f64 = 89.9;

pub const GLOBE: &str = "Globe (Orthographic)";

struct LambertDef {
    name: &'static str,
    conic: bool,
    lon_0: f64,
    lat_0: f64,
    lat_1: f64,
    lat_2: f64,
    lon_halfspan: f64,
    lat_min: f64,
    lat_max: f64,
}

const fn lambert(
    name: &'static str,
    conic: bool,
    origin: (f64, f64),
    parallels: (f64, f64),
    lon_halfspan: f64,
    lats: (f64, f64),
) -> LambertDef {
    LambertDef {
        name,
        conic,
        lon_0: origin.0,
        lat_0: origin.1,
        lat_1: parallels.0,
        lat_2: parallels.1,
        lon_halfspan,
        lat_min: lats.0,
        lat_max: lats.1,
    }
}

const LAMBERT_DEFS: &[LambertDef] = &[
    lambert("Lambert: N. America", true, (-96.0, 40.0), (20.0, 60.0), 90.0, (7.0, 84.0)),
    lambert("Lambert: Europe", true, (10.0, 52.0), (35.0, 65.0), 55.0, (30.0, 72.0)),
    lambert("Lambert: Asia", true, (95.0, 30.0), (15.0, 65.0), 90.0, (-12.0, 78.0)),
    lambert("Lambert: S. America", true, (-60.0, -32.0), (-5.0, -42.0), 55.0, (-58.0, 14.0)),
    lambert("Lambert: Africa", false, (20.0, 5.0), (0.0, 0.0), 60.0, (-38.0, 40.0)),
    lambert("Lambert Azimuthal (custom)", false, (0.0, 0.0), (0.0, 0.0), 120.0, (-88.0, 88.0)),
];

const WORLD: &[&str] =
    &["Equirectangular", "Mercator", "Robinson", "Mollweide", "Natural Earth", "Winkel Tripel"];

/// Every projection name, in the order the UI lists them.
pub fn projection_names() -> Vec<&'static str> {
    WORLD.iter().copied().chain([GLOBE]).chain(LAMBERT_DEFS.iter().map(|d| d.name)).collect()
}

/// The projection choice as the frontend sends it. `lon_0`/`lat_0` override
/// the centre of the globe and the Lambert presets.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectionSpec {
    pub name: String,
    pub lon_0: Option<f64>,
    pub lat_0: Option<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum Kind {
    Equirectangular,
    Mercator,
    Robinson,
    Mollweide,
    NaturalEarth,
    WinkelTripel,
    Orthographic { sin0: f64, cos0: f64, nu0: f64 },
    Lcc { n: f64, af: f64, rho0: f64 },
    Laea { sinb1: f64, cosb1: f64, rq: f64, d: f64, qp: f64 },
}

#[derive(Debug, Clone, PartialEq)]
pub struct Projection {
    kind: Kind,
    pub name: String,
    pub lon_0: f64,
    pub lat_0: f64,
    pub min_lat: f64,
    pub max_lat: f64,
    /// ± degrees of longitude around `lon_0` that are drawn (180 = world).
    pub lon_halfspan: f64,
}

#[derive(Debug, thiserror::Error)]
#[error("unknown projection '{0}'")]
pub struct UnknownProjection(String);

fn wrap_lon(mut v: f64) -> f64 {
    while v > 180.0 {
        v -= 360.0;
    }
    while v < -180.0 {
        v += 360.0;
    }
    v
}

// Ellipsoid helpers (Snyder's m, t and q).
fn msfn(sinp: f64, cosp: f64) -> f64 {
    cosp / (1.0 - ES * sinp * sinp).sqrt()
}
fn tsfn(phi: f64) -> f64 {
    let e = ES.sqrt();
    let s = e * phi.sin();
    (FRAC_PI_4 - phi / 2.0).tan() / ((1.0 - s) / (1.0 + s)).powf(e / 2.0)
}
fn qsfn(sinp: f64) -> f64 {
    let e = ES.sqrt();
    let con = e * sinp;
    (1.0 - ES) * (sinp / (1.0 - con * con) - (0.5 / e) * ((1.0 - con) / (1.0 + con)).ln())
}

impl Projection {
    pub fn new(spec: &ProjectionSpec) -> Result<Self, UnknownProjection> {
        let world = |kind: Kind, max_lat: f64| Projection {
            kind,
            name: spec.name.clone(),
            lon_0: 0.0,
            lat_0: 0.0,
            min_lat: -max_lat,
            max_lat,
            lon_halfspan: 180.0,
        };
        Ok(match spec.name.as_str() {
            "Equirectangular" => world(Kind::Equirectangular, 90.0),
            "Mercator" => world(Kind::Mercator, 85.05),
            "Robinson" => world(Kind::Robinson, 90.0),
            "Mollweide" => world(Kind::Mollweide, 90.0),
            "Natural Earth" => world(Kind::NaturalEarth, 90.0),
            "Winkel Tripel" => world(Kind::WinkelTripel, 90.0),
            GLOBE => {
                let lon_0 = spec.lon_0.unwrap_or(0.0);
                let lat_0 = spec.lat_0.unwrap_or(0.0).clamp(-90.0, 90.0);
                let p0 = lat_0.to_radians();
                Projection {
                    kind: Kind::Orthographic {
                        sin0: p0.sin(),
                        cos0: p0.cos(),
                        nu0: 1.0 / (1.0 - ES * p0.sin().powi(2)).sqrt(),
                    },
                    name: spec.name.clone(),
                    lon_0,
                    lat_0,
                    min_lat: -90.0,
                    max_lat: 90.0,
                    lon_halfspan: 180.0,
                }
            }
            other => {
                let d = LAMBERT_DEFS
                    .iter()
                    .find(|d| d.name == other)
                    .ok_or_else(|| UnknownProjection(other.to_string()))?;
                let lon_0 = spec.lon_0.unwrap_or(d.lon_0);
                // The ellipsoidal LAEA is singular exactly at a pole.
                let lat_0 = spec.lat_0.unwrap_or(d.lat_0).clamp(-89.999, 89.999);
                let kind = if d.conic { lcc(d, lat_0) } else { laea(lat_0) };
                Projection {
                    kind,
                    name: spec.name.clone(),
                    lon_0,
                    lat_0,
                    min_lat: d.lat_min,
                    max_lat: d.lat_max,
                    lon_halfspan: d.lon_halfspan,
                }
            }
        })
    }

    pub fn is_globe(&self) -> bool {
        matches!(self.kind, Kind::Orthographic { .. })
    }

    pub fn is_regional(&self) -> bool {
        matches!(self.kind, Kind::Lcc { .. } | Kind::Laea { .. })
    }

    /// Longitude relative to the central meridian, in [-180, 180].
    pub fn relative_lon(&self, lon: f64) -> f64 {
        if self.lon_0 == 0.0 { lon } else { wrap_lon(lon - self.lon_0) }
    }

    /// Projected (x, y), or `None` where the projection is undefined.
    pub fn forward(&self, lon: f64, lat: f64) -> Option<(f64, f64)> {
        let lam = self.relative_lon(lon).to_radians();
        let phi = lat.to_radians();
        let (x, y) = match self.kind {
            Kind::Equirectangular => return Some((lon, lat)),
            Kind::Mercator => {
                if lat.abs() >= 90.0 {
                    return None;
                }
                let e = ES.sqrt();
                let s = e * phi.sin();
                let y = ((FRAC_PI_4 + phi / 2.0).tan() * ((1.0 - s) / (1.0 + s)).powf(e / 2.0)).ln();
                (lam, y)
            }
            Kind::Robinson => robinson(lam, phi),
            Kind::Mollweide => mollweide(lam, phi),
            Kind::NaturalEarth => natural_earth(lam, phi),
            Kind::WinkelTripel => winkel_tripel(lam, phi),
            Kind::Orthographic { sin0, cos0, nu0 } => {
                let (sinp, cosp) = phi.sin_cos();
                let (sinl, cosl) = lam.sin_cos();
                if sin0 * sinp + cos0 * cosp * cosl < -1e-12 {
                    return None;
                }
                let nu = 1.0 / (1.0 - ES * sinp * sinp).sqrt();
                (
                    nu * cosp * sinl,
                    nu * (sinp * cos0 - cosp * sin0 * cosl) + ES * (nu0 * sin0 - nu * sinp) * cos0,
                )
            }
            Kind::Lcc { n, af, rho0 } => {
                if (lat.abs() - 90.0).abs() < 1e-10 && lat.signum() != n.signum() {
                    return None;
                }
                let rho = af * tsfn(phi).powf(n);
                let theta = n * lam;
                return Some((rho * theta.sin(), rho0 - rho * theta.cos()));
            }
            Kind::Laea { sinb1, cosb1, rq, d, qp } => {
                let q = qsfn(phi.sin());
                let beta = (q / qp).clamp(-1.0, 1.0).asin();
                let (sinb, cosb) = beta.sin_cos();
                let denom = 1.0 + sinb1 * sinb + cosb1 * cosb * lam.cos();
                if denom <= 1e-12 {
                    return None;
                }
                let b = rq * (2.0 / denom).sqrt();
                return Some((b * d * cosb * lam.sin(), (b / d) * (cosb1 * sinb - sinb1 * cosb * lam.cos())));
            }
        };
        Some((A * x, A * y))
    }

    /// Longitude/latitude of a projected point, by Newton iteration on
    /// `forward` (good enough for a cursor read-out).
    pub fn inverse(&self, x: f64, y: f64) -> Option<(f64, f64)> {
        if self.kind == Kind::Equirectangular {
            return ((-180.0..=180.0).contains(&x) && (-90.0..=90.0).contains(&y)).then_some((x, y));
        }
        let scale = A;
        let mut best: Option<(f64, f64, f64)> = None;
        for start in [(0.0, self.lat_0), (0.0, 0.0), (60.0, 45.0), (-60.0, -45.0)] {
            let (mut lam, mut lat) = start;
            for _ in 0..40 {
                let lon = lam + self.lon_0;
                let Some((fx, fy)) = self.forward(lon, lat) else { break };
                let (ex, ey) = (fx - x, fy - y);
                let err = ex.hypot(ey);
                if best.is_none_or(|b| err < b.2) {
                    best = Some((wrap_lon(lon), lat, err));
                }
                if err < 1e-3 {
                    break;
                }
                let h = 1e-6;
                let (Some((ax, ay)), Some((bx, by))) =
                    (self.forward(lon + h, lat), self.forward(lon, lat + h))
                else {
                    break;
                };
                let (j11, j21, j12, j22) = ((ax - fx) / h, (ay - fy) / h, (bx - fx) / h, (by - fy) / h);
                let det = j11 * j22 - j12 * j21;
                if det.abs() < 1e-12 {
                    break;
                }
                let dl = (j22 * ex - j12 * ey) / det;
                let dp = (-j21 * ex + j11 * ey) / det;
                lam = (lam - dl.clamp(-30.0, 30.0)).clamp(-180.0, 180.0);
                lat = (lat - dp.clamp(-30.0, 30.0)).clamp(-89.9999, 89.9999);
            }
        }
        let (lon, lat, err) = best?;
        (err < scale * 1e-6 && self.in_domain(lon, lat)).then_some((lon, lat))
    }

    /// Whether a point falls in the part of the world this projection draws.
    pub fn in_domain(&self, lon: f64, lat: f64) -> bool {
        if self.is_globe() {
            return self.cap_distance(lon, lat) <= HORIZON_RADIUS;
        }
        lat >= self.min_lat
            && lat <= self.max_lat
            && self.relative_lon(lon).abs() <= self.lon_halfspan
    }

    /// Great-circle distance in degrees from the globe's centre.
    pub fn cap_distance(&self, lon: f64, lat: f64) -> f64 {
        let (p, p0) = (lat.to_radians(), self.lat_0.to_radians());
        let dl = (lon - self.lon_0).to_radians();
        (p.sin() * p0.sin() + p.cos() * p0.cos() * dl.cos()).clamp(-1.0, 1.0).acos().to_degrees()
    }
}

fn lcc(d: &LambertDef, lat_0: f64) -> Kind {
    let (p1, p2, p0) = (d.lat_1.to_radians(), d.lat_2.to_radians(), lat_0.to_radians());
    let m1 = msfn(p1.sin(), p1.cos());
    let m2 = msfn(p2.sin(), p2.cos());
    let (t1, t2) = (tsfn(p1), tsfn(p2));
    let n = if (p1 - p2).abs() > 1e-10 { (m1 / m2).ln() / (t1 / t2).ln() } else { p1.sin() };
    let af = A * m1 / (n * t1.powf(n));
    let rho0 = af * tsfn(p0).powf(n);
    Kind::Lcc { n, af, rho0 }
}

fn laea(lat_0: f64) -> Kind {
    let p1 = lat_0.to_radians();
    let qp = qsfn(1.0);
    let rq = A * (qp / 2.0).sqrt();
    let beta1 = (qsfn(p1.sin()) / qp).asin();
    let d = A * msfn(p1.sin(), p1.cos()) / (rq * beta1.cos());
    Kind::Laea { sinb1: beta1.sin(), cosb1: beta1.cos(), rq, d, qp }
}

// Robinson's tabulated coefficients at 5° steps (PROJ's PJ_robin.c).
const ROBIN_X: [[f64; 4]; 19] = [
    [1.0, 2.2199e-17, -7.15515e-05, 3.1103e-06],
    [0.9986, -0.000482243, -2.4897e-05, -1.3309e-06],
    [0.9954, -0.00083103, -4.48605e-05, -9.86701e-07],
    [0.99, -0.00135364, -5.9661e-05, 3.6777e-06],
    [0.9822, -0.00167442, -4.49547e-06, -5.72411e-06],
    [0.973, -0.00214868, -9.03571e-05, 1.8736e-08],
    [0.96, -0.00305085, -9.00761e-05, 1.64917e-06],
    [0.9427, -0.00382792, -6.53386e-05, -2.6154e-06],
    [0.9216, -0.00467746, -0.00010457, 4.81243e-06],
    [0.8962, -0.00536223, -3.23831e-05, -5.43432e-06],
    [0.8679, -0.00609363, -0.000113898, 3.32484e-06],
    [0.835, -0.00698325, -6.40253e-05, 9.34959e-07],
    [0.7986, -0.00755338, -5.00009e-05, 9.35324e-07],
    [0.7597, -0.00798324, -3.5971e-05, -2.27626e-06],
    [0.7186, -0.00851367, -7.01149e-05, -8.6303e-06],
    [0.6732, -0.00986209, -0.000199569, 1.91974e-05],
    [0.6213, -0.010418, 8.83923e-05, 6.24051e-06],
    [0.5722, -0.00906601, 0.000182, 6.24051e-06],
    [0.5322, -0.00677797, 0.000275608, 6.24051e-06],
];
const ROBIN_Y: [[f64; 4]; 19] = [
    [-5.20417e-18, 0.0124, 1.21431e-18, -8.45284e-11],
    [0.062, 0.0124, -1.26793e-09, 4.22642e-10],
    [0.124, 0.0124, 5.07171e-09, -1.60604e-09],
    [0.186, 0.0123999, -1.90189e-08, 6.00152e-09],
    [0.248, 0.0124002, 7.10039e-08, -2.24e-08],
    [0.31, 0.0123992, -2.64997e-07, 8.35986e-08],
    [0.372, 0.0124029, 9.88983e-07, -3.11994e-07],
    [0.434, 0.0123893, -3.69093e-06, -4.35621e-07],
    [0.4958, 0.0123198, -1.02252e-05, -3.45523e-07],
    [0.5571, 0.0121916, -1.54081e-05, -5.82288e-07],
    [0.6176, 0.0119938, -2.41424e-05, -5.25327e-07],
    [0.6769, 0.011713, -3.20223e-05, -5.16405e-07],
    [0.7346, 0.0113541, -3.97684e-05, -6.09052e-07],
    [0.7903, 0.0109107, -4.89042e-05, -1.04739e-06],
    [0.8435, 0.0103431, -6.4615e-05, -1.40374e-09],
    [0.8936, 0.00969686, -6.4636e-05, -8.547e-06],
    [0.9394, 0.00840947, -0.000192841, -4.2106e-06],
    [0.9761, 0.00616527, -0.000256, -4.2106e-06],
    [1.0, 0.00328947, -0.000319159, -4.2106e-06],
];

fn robinson(lam: f64, phi: f64) -> (f64, f64) {
    const FXC: f64 = 0.8487;
    const FYC: f64 = 1.3523;
    let v = |c: [f64; 4], z: f64| c[0] + z * (c[1] + z * (c[2] + z * c[3]));
    let aphi = phi.abs();
    let i = ((aphi * 180.0 / (5.0 * PI) + 1e-15).floor() as usize).min(18);
    let z = (aphi - (5.0f64).to_radians() * i as f64).to_degrees();
    let x = v(ROBIN_X[i], z) * FXC * lam;
    let y = v(ROBIN_Y[i], z) * FYC;
    (x, if phi < 0.0 { -y } else { y })
}

fn mollweide(lam: f64, phi: f64) -> (f64, f64) {
    let cx = 2.0 * std::f64::consts::SQRT_2 / PI;
    let cy = std::f64::consts::SQRT_2;
    let k = PI * phi.sin();
    let mut t = phi;
    let mut converged = false;
    for _ in 0..30 {
        let v = (t + t.sin() - k) / (1.0 + t.cos());
        t -= v;
        if v.abs() < 1e-7 {
            converged = true;
            break;
        }
    }
    let theta = if converged { t * 0.5 } else { FRAC_PI_2.copysign(t) };
    (cx * lam * theta.cos(), cy * theta.sin())
}

fn natural_earth(lam: f64, phi: f64) -> (f64, f64) {
    const A0: f64 = 0.8707;
    const A1: f64 = -0.131979;
    const A2: f64 = -0.013791;
    const A3: f64 = 0.003971;
    const A4: f64 = -0.001529;
    const B0: f64 = 1.007226;
    const B1: f64 = 0.015085;
    const B2: f64 = -0.044475;
    const B3: f64 = 0.028874;
    const B4: f64 = -0.005916;
    let p2 = phi * phi;
    let p4 = p2 * p2;
    let x = lam * (A0 + p2 * (A1 + p2 * (A2 + p4 * p2 * (A3 + p2 * A4))));
    let y = phi * (B0 + p2 * (B1 + p4 * (B2 + B3 * p2 + B4 * p4)));
    (x, y)
}

fn winkel_tripel(lam: f64, phi: f64) -> (f64, f64) {
    // PyMappr's "+proj=wintri" string gives no lat_1, and pyproj then uses
    // the equator as the standard parallel; match it so maps line up.
    let cosphi1 = 1.0;
    let c = 0.5 * lam;
    let d = (phi.cos() * c.cos()).clamp(-1.0, 1.0).acos();
    let (mut x, mut y) = (0.0, 0.0);
    if d != 0.0 {
        let inv = 1.0 / d.sin();
        x = 2.0 * d * phi.cos() * c.sin() * inv;
        y = d * phi.sin() * inv;
    }
    ((x + lam * cosphi1) * 0.5, (y + phi) * 0.5)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn proj(name: &str) -> Projection {
        Projection::new(&ProjectionSpec { name: name.into(), lon_0: None, lat_0: None }).unwrap()
    }

    /// Reference values from pyproj 3.7.2 with PyMappr's PROJ strings (see
    /// tests/data/pyproj_reference.txt and scripts/pyproj_reference.py).
    #[test]
    fn matches_pyproj() {
        let text = include_str!("../tests/data/pyproj_reference.txt");
        let mut checked = 0;
        let mut failures = Vec::new();
        for line in text.lines().filter(|l| !l.trim().is_empty() && !l.starts_with('#')) {
            let cols: Vec<&str> = line.split('\t').collect();
            let p = proj(cols[0]);
            let nums: Vec<f64> = cols[1..].iter().map(|v| v.parse().unwrap()).collect();
            let (x, y) = p.forward(nums[0], nums[1]).expect(line);
            // Robinson: PROJ revised its coefficient table; the old one is < 0.5 m off.
            let tol = 1.0;
            if (x - nums[2]).abs() >= tol || (y - nums[3]).abs() >= tol {
                failures.push(format!(
                    "{}: ({}, {}) gave ({x}, {y}), expected ({}, {})",
                    cols[0], nums[0], nums[1], nums[2], nums[3]
                ));
            }
            checked += 1;
        }
        assert!(failures.is_empty(), "{}", failures.join("
"));
        assert!(checked > 50);
    }

    #[test]
    fn inverse_round_trips() {
        for name in projection_names() {
            let p = proj(name);
            let (lon, lat) = (p.lon_0 + 12.5, (p.lat_0 + 7.25).clamp(p.min_lat, p.max_lat));
            let (x, y) = p.forward(lon, lat).unwrap();
            let (lon2, lat2) = p.inverse(x, y).unwrap_or_else(|| panic!("{name}"));
            assert!((lon - lon2).abs() < 1e-5 && (lat - lat2).abs() < 1e-5, "{name}: {lon2},{lat2}");
        }
    }

    #[test]
    fn globe_back_side_is_hidden() {
        let p = proj(GLOBE);
        assert!(p.forward(180.0, 0.0).is_none());
        assert!(p.forward(10.0, 10.0).is_some());
    }

    #[test]
    fn every_name_builds() {
        assert_eq!(projection_names().len(), 13);
        for name in projection_names() {
            proj(name);
        }
    }
}
