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
    /// The projected world: x0, x1, y0, y1 (y up), as PyMappr's `bounds`.
    pub bounds: [f64; 4],
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
        let mut proj = Self::build(spec)?;
        proj.bounds = proj.compute_bounds();
        Ok(proj)
    }

    fn build(spec: &ProjectionSpec) -> Result<Self, UnknownProjection> {
        let world = |kind: Kind, max_lat: f64| Projection {
            kind,
            name: spec.name.clone(),
            lon_0: 0.0,
            lat_0: 0.0,
            min_lat: -max_lat,
            max_lat,
            lon_halfspan: 180.0,
            bounds: [0.0; 4],
        };
        Ok(match spec.name.as_str() {
            "Equirectangular" => world(Kind::Equirectangular, 90.0),
            "Mercator" => world(Kind::Mercator, 85.05),
            "Robinson" => world(Kind::Robinson, 90.0),
            "Mollweide" => world(Kind::Mollweide, 90.0),
            "Natural Earth" => world(Kind::NaturalEarth, 90.0),
            "Winkel Tripel" => world(Kind::WinkelTripel, 90.0),
            GLOBE => {
                let (lon_0, lat_0) = normalize_origin(spec.lon_0, spec.lat_0, (0.0, 0.0));
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
                    bounds: [0.0; 4],
                }
            }
            other => {
                let d = LAMBERT_DEFS
                    .iter()
                    .find(|d| d.name == other)
                    .ok_or_else(|| UnknownProjection(other.to_string()))?;
                let (lon_0, lat_0) = normalize_origin(spec.lon_0, spec.lat_0, (d.lon_0, d.lat_0));
                // The ellipsoidal LAEA is singular exactly at a pole.
                let lat_0 = lat_0.clamp(-89.999, 89.999);
                let kind = if d.conic { lcc(d, lat_0) } else { laea(lat_0) };
                Projection {
                    kind,
                    name: spec.name.clone(),
                    lon_0,
                    lat_0,
                    min_lat: d.lat_min,
                    max_lat: d.lat_max,
                    lon_halfspan: d.lon_halfspan,
                    bounds: [0.0; 4],
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

    /// Cache key: the name plus the origin, which custom origins change.
    pub fn key(&self) -> String {
        format!("{}|{}|{}", self.name, self.lon_0, self.lat_0)
    }

    /// Width of the projected world (PyMappr's `world_width`).
    pub fn world_width(&self) -> f64 {
        self.bounds[1] - self.bounds[0]
    }

    /// Plain longitude/latitude degrees (PyMappr's `is_geographic`).
    pub fn is_geographic(&self) -> bool {
        self.kind == Kind::Equirectangular
    }

    /// PyMappr's `forward(clamp=True)`: latitudes are pulled into the drawn
    /// band and, on a regional map, longitudes onto its edge, so nothing
    /// goes missing. `None` only on the far side of the globe.
    pub fn forward_clamped(&self, lon: f64, lat: f64) -> Option<(f64, f64)> {
        if !(lon.is_finite() && lat.is_finite()) {
            return None;
        }
        let lat = lat.clamp(self.min_lat, self.max_lat);
        let lon = if self.lon_halfspan < 180.0 {
            self.lon_0 + self.relative_lon(lon).clamp(-self.lon_halfspan, self.lon_halfspan)
        } else {
            lon
        };
        self.forward(lon, lat)
    }

    /// PyMappr's `forward(clamp=False)`: `None` outside the drawn band or
    /// region, and on the far side of the globe.
    pub fn forward_unclamped(&self, lon: f64, lat: f64) -> Option<(f64, f64)> {
        if !(lon.is_finite() && lat.is_finite()) || lat < self.min_lat || lat > self.max_lat {
            return None;
        }
        if self.lon_halfspan < 180.0 && self.relative_lon(lon).abs() > self.lon_halfspan {
            return None;
        }
        self.forward(lon, lat)
    }

    /// Longitude/latitude of a projected point inside the drawn part of
    /// the world, for the cursor read-out.
    pub fn inverse(&self, x: f64, y: f64) -> Option<(f64, f64)> {
        let (lon, lat) = self.inverse_on_map(x, y, None)?;
        self.in_domain(lon, lat).then_some((lon, lat))
    }

    /// [`Self::inverse_seeded`], but `None` for points off the world's
    /// outline that PROJ answers with a wrapped longitude.
    pub fn inverse_on_map(&self, x: f64, y: f64, seed: Option<(f64, f64)>) -> Option<(f64, f64)> {
        let (lon, lat) = self.inverse_seeded(x, y, seed)?;
        let on_map = match self.kind {
            Kind::Mercator => x.abs() <= PI * A * (1.0 + 1e-12),
            Kind::NaturalEarth | Kind::WinkelTripel => {
                let back = if x.abs() < 1e-9 { Some((x, y)) } else { self.forward(lon, lat) };
                back.is_some_and(|(fx, fy)| (fx - x).abs() < 1e-3 && (fy - y).abs() < 1e-3)
            }
            _ => true,
        };
        on_map.then_some((lon, lat))
    }

    /// Longitude/latitude of a projected point as PROJ's inverse gives it:
    /// regional (Lambert) maps are not limited to their region, as pyproj
    /// knows of none. `None` off the projection's own domain (outside a
    /// world outline, beyond the globe's horizon).
    pub fn inverse_raw(&self, x: f64, y: f64) -> Option<(f64, f64)> {
        self.inverse_seeded(x, y, None)
    }

    /// [`Self::inverse_raw`], with the iterative projections started from
    /// `seed` (lon, lat in degrees): a neighbouring pixel's answer, when
    /// warping an image.
    pub fn inverse_seeded(&self, x: f64, y: f64, seed: Option<(f64, f64)>) -> Option<(f64, f64)> {
        if !(x.is_finite() && y.is_finite()) {
            return None;
        }
        let world = |lam: f64, phi: f64| {
            (lam.abs() <= PI + 1e-9 && phi.abs() <= FRAC_PI_2 + 1e-9)
                .then(|| (lam.to_degrees().clamp(-180.0, 180.0), phi.to_degrees().clamp(-90.0, 90.0)))
        };
        // PROJ wraps an out-of-range longitude (`adjlon`) rather than refuse
        // it on these, so points past the outline come back from the
        // other side of the world, as pyproj gives them to PyMappr.
        let wrapped = |lam: f64, phi: f64| {
            (phi.abs() <= FRAC_PI_2 + 1e-9 && lam.is_finite())
                .then(|| (wrap_lon(lam.to_degrees()), phi.to_degrees().clamp(-90.0, 90.0)))
        };
        let (xn, yn) = (x / A, y / A);
        match self.kind {
            Kind::Equirectangular => {
                ((-180.0..=180.0).contains(&x) && (-90.0..=90.0).contains(&y)).then_some((x, y))
            }
            Kind::Mercator => wrapped(xn, phi2((-yn).exp())),
            Kind::Robinson => {
                let (lam, phi) = robinson_inverse(xn, yn)?;
                world(lam, phi)
            }
            Kind::Mollweide => {
                let s = yn / std::f64::consts::SQRT_2;
                if s.abs() > 1.0 + 1e-12 {
                    return None;
                }
                let theta = s.clamp(-1.0, 1.0).asin();
                let cos_t = theta.cos();
                let lam = if cos_t < 1e-12 { 0.0 } else { xn / (2.0 * std::f64::consts::SQRT_2 / PI * cos_t) };
                let phi = ((2.0 * theta + (2.0 * theta).sin()) / PI).clamp(-1.0, 1.0).asin();
                world(lam, phi)
            }
            Kind::NaturalEarth => {
                let (lam, phi) = natural_earth_inverse(xn, yn)?;
                wrapped(lam, phi)
            }
            Kind::WinkelTripel => {
                let seed = seed.map(|(lon, lat)| (lon.to_radians(), lat.to_radians()));
                let starts = [(xn, yn), (xn * 0.75, yn * 0.9), (0.0, 0.0)];
                let (lam, phi) = newton_inverse(winkel_tripel, xn, yn, seed, &starts)?;
                wrapped(lam, phi)
            }
            Kind::Orthographic { sin0, cos0, nu0 } => {
                // The spherical inverse, then Newton on the ellipsoidal
                // forward to take out the flattening.
                // The ellipsoidal disk is slightly off centre on a tilted
                // globe, so allow a little past the unit circle.
                let rho = xn.hypot(yn);
                if rho > 1.01 {
                    return None;
                }
                let c = rho.min(1.0).asin();
                let (sinc, cosc) = c.sin_cos();
                let sphere = if rho < 1e-15 {
                    (0.0, self.lat_0.to_radians())
                } else {
                    (
                        (xn * sinc).atan2(rho * cosc * cos0 - yn * sinc * sin0),
                        (cosc * sin0 + yn * sinc * cos0 / rho).clamp(-1.0, 1.0).asin(),
                    )
                };
                let seed = seed.map(|(lon, lat)| (wrap_lon(lon - self.lon_0).to_radians(), lat.to_radians()));
                let f = |lam: f64, phi: f64| ortho_ellipsoidal(sin0, cos0, nu0, lam, phi);
                let (lam, phi) = newton_inverse(f, xn, yn, seed, &[sphere])?;
                let (sinp, cosp) = phi.sin_cos();
                if sin0 * sinp + cos0 * cosp * lam.cos() < -1e-9 || phi.abs() > FRAC_PI_2 + 1e-9 {
                    return None;
                }
                Some((wrap_lon(self.lon_0 + lam.to_degrees()), phi.to_degrees().clamp(-90.0, 90.0)))
            }
            Kind::Lcc { n, af, rho0 } => {
                let (mut px, mut py) = (x, rho0 - y);
                let mut rho = px.hypot(py);
                if rho == 0.0 {
                    return Some((self.lon_0, if n > 0.0 { 90.0 } else { -90.0 }));
                }
                if n < 0.0 {
                    rho = -rho;
                    px = -px;
                    py = -py;
                }
                let phi = phi2((rho / af).powf(1.0 / n));
                let lam = px.atan2(py) / n;
                Some((wrap_lon(self.lon_0 + lam.to_degrees()), phi.to_degrees()))
            }
            Kind::Laea { sinb1, cosb1, rq, d, .. } => {
                let (mut px, py) = (x / d, y * d);
                let rho = px.hypot(py);
                if rho < 1e-10 {
                    return Some((self.lon_0, self.lat_0));
                }
                let arg = 0.5 * rho / rq;
                if arg > 1.0 {
                    return None;
                }
                let sce = 2.0 * arg.asin();
                let (s, c) = sce.sin_cos();
                px *= s;
                let ab = c * sinb1 + py * s * cosb1 / rho;
                let yy = rho * cosb1 * c - py * sinb1 * s;
                let lam = px.atan2(yy);
                let phi = authalic_to_geodetic(ab.clamp(-1.0, 1.0).asin());
                Some((wrap_lon(self.lon_0 + lam.to_degrees()), phi.to_degrees()))
            }
        }
    }

    /// PyMappr's `bounds`: the projected box of the drawn region, from 60
    /// points along each edge (the horizon ring on the globe).
    fn compute_bounds(&self) -> [f64; 4] {
        if self.kind == Kind::Equirectangular {
            return [-180.0, 180.0, -90.0, 90.0];
        }
        let mut pts = Vec::new();
        if self.is_globe() {
            pts.extend(cap_ring(self.lon_0, self.lat_0, HORIZON_RADIUS, 361));
        } else {
            let (l0, l1) = (self.lon_0 - self.lon_halfspan, self.lon_0 + self.lon_halfspan);
            let (p0, p1) = (self.min_lat, self.max_lat);
            let n = 60;
            for i in 0..n {
                let t = i as f64 / (n - 1) as f64;
                let lon = l0 + (l1 - l0) * t;
                let lat = p0 + (p1 - p0) * t;
                pts.extend([[lon, p0], [lon, p1], [l0, lat], [l1, lat]]);
            }
        }
        let mut b = [f64::MAX, f64::MIN, f64::MAX, f64::MIN];
        for [lon, lat] in pts {
            if let Some((x, y)) = self.forward(lon, lat) {
                b = [b[0].min(x), b[1].max(x), b[2].min(y), b[3].max(y)];
            }
        }
        b
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

/// A row of the Robinson table as PROJ holds it: in single precision,
/// which moves points by up to a few metres.
fn robin(c: [f64; 4]) -> [f64; 4] {
    c.map(|v| v as f32 as f64)
}

fn robinson(lam: f64, phi: f64) -> (f64, f64) {
    const FXC: f64 = 0.8487;
    const FYC: f64 = 1.3523;
    let v = |c: [f64; 4], z: f64| c[0] + z * (c[1] + z * (c[2] + z * c[3]));
    let aphi = phi.abs();
    let i = ((aphi * 180.0 / (5.0 * PI) + 1e-15).floor() as usize).min(18);
    let z = (aphi - (5.0f64).to_radians() * i as f64).to_degrees();
    let x = v(robin(ROBIN_X[i]), z) * FXC * lam;
    let y = v(robin(ROBIN_Y[i]), z) * FYC;
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

/// PyMappr's `normalize_origin`, with missing or non-finite values taking
/// the preset's default.
fn normalize_origin(lon: Option<f64>, lat: Option<f64>, default: (f64, f64)) -> (f64, f64) {
    let lon = lon.filter(|v| v.is_finite()).unwrap_or(default.0);
    let lat = lat.filter(|v| v.is_finite()).unwrap_or(default.1);
    let lon = if (-180.0..=180.0).contains(&lon) { lon } else { (lon + 180.0).rem_euclid(360.0) - 180.0 };
    (lon, lat.clamp(-90.0, 90.0))
}

/// The ring `radius` great-circle degrees from (lon_0, lat_0), traced by
/// azimuth (PyMappr's `_cap_ring`). Longitudes stay within 180° of lon_0.
pub fn cap_ring(lon_0: f64, lat_0: f64, radius: f64, n: usize) -> Vec<[f64; 2]> {
    let phi0 = lat_0.to_radians();
    let r = radius.to_radians();
    (0..n)
        .map(|i| {
            let az = 2.0 * PI * i as f64 / (n - 1) as f64;
            let lat = (phi0.sin() * r.cos() + phi0.cos() * r.sin() * az.cos()).clamp(-1.0, 1.0).asin();
            let dlon = (az.sin() * r.sin() * phi0.cos()).atan2(r.cos() - phi0.sin() * lat.sin());
            [lon_0 + dlon.to_degrees(), lat.to_degrees()]
        })
        .collect()
}

/// Latitude from Snyder's t (PROJ's `pj_phi2`).
fn phi2(ts: f64) -> f64 {
    let e = ES.sqrt();
    let mut phi = FRAC_PI_2 - 2.0 * ts.atan();
    for _ in 0..15 {
        let con = e * phi.sin();
        let dphi = FRAC_PI_2 - 2.0 * (ts * ((1.0 - con) / (1.0 + con)).powf(0.5 * e)).atan() - phi;
        phi += dphi;
        if dphi.abs() < 1e-12 {
            break;
        }
    }
    phi
}

/// Geodetic latitude from authalic latitude (PROJ's `pj_authlat` series).
fn authalic_to_geodetic(beta: f64) -> f64 {
    const P00: f64 = 1.0 / 3.0;
    const P01: f64 = 31.0 / 180.0;
    const P02: f64 = 517.0 / 5040.0;
    const P10: f64 = 23.0 / 360.0;
    const P11: f64 = 251.0 / 3780.0;
    const P20: f64 = 761.0 / 45360.0;
    let (es, es2) = (ES, ES * ES);
    let es3 = es2 * ES;
    let apa = [es * P00 + es2 * P01 + es3 * P02, es2 * P10 + es3 * P11, es3 * P20];
    let t = beta + beta;
    beta + apa[0] * t.sin() + apa[1] * (t + t).sin() + apa[2] * (t + t + t).sin()
}

/// The ellipsoidal orthographic forward in units of the semi-major axis.
fn ortho_ellipsoidal(sin0: f64, cos0: f64, nu0: f64, lam: f64, phi: f64) -> (f64, f64) {
    let (sinp, cosp) = phi.sin_cos();
    let (sinl, cosl) = lam.sin_cos();
    let nu = 1.0 / (1.0 - ES * sinp * sinp).sqrt();
    (nu * cosp * sinl, nu * (sinp * cos0 - cosp * sin0 * cosl) + ES * (nu0 * sin0 - nu * sinp) * cos0)
}

/// Solve `f(λ, φ) = (x, y)` by Newton's method from `seed`, else from each
/// of `starts` in turn. Radians; units of the semi-major axis.
fn newton_inverse(
    f: impl Fn(f64, f64) -> (f64, f64),
    x: f64,
    y: f64,
    seed: Option<(f64, f64)>,
    starts: &[(f64, f64)],
) -> Option<(f64, f64)> {
    let solve = |(mut lam, mut phi): (f64, f64)| -> Option<(f64, f64)> {
        for _ in 0..30 {
            let (fx, fy) = f(lam, phi);
            let (ex, ey) = (fx - x, fy - y);
            if ex.abs() < 1e-11 && ey.abs() < 1e-11 {
                return Some((lam, phi));
            }
            let h = 1e-7;
            let (ax, ay) = f(lam + h, phi);
            let (bx, by) = f(lam, phi + h);
            let (j11, j21, j12, j22) = ((ax - fx) / h, (ay - fy) / h, (bx - fx) / h, (by - fy) / h);
            let det = j11 * j22 - j12 * j21;
            if det.abs() < 1e-14 {
                break;
            }
            lam -= ((j22 * ex - j12 * ey) / det).clamp(-0.5, 0.5);
            phi = (phi - ((-j21 * ex + j11 * ey) / det).clamp(-0.5, 0.5)).clamp(-FRAC_PI_2, FRAC_PI_2);
        }
        let (fx, fy) = f(lam, phi);
        ((fx - x).abs() < 1e-9 && (fy - y).abs() < 1e-9).then_some((lam, phi))
    };
    seed.and_then(solve).or_else(|| starts.iter().find_map(|&s| solve(s)))
}

/// PROJ's Robinson inverse: the latitude from the y table by Newton, then
/// the longitude directly. Units of the semi-major axis.
fn robinson_inverse(x: f64, y: f64) -> Option<(f64, f64)> {
    const FXC: f64 = 0.8487;
    const FYC: f64 = 1.3523;
    const NODES: usize = 18;
    let v = |c: [f64; 4], z: f64| c[0] + z * (c[1] + z * (c[2] + z * c[3]));
    let dv = |c: [f64; 4], z: f64| c[1] + z * (c[2] + c[2] + z * 3.0 * c[3]);
    let mut lam = x / FXC;
    let mut phi = (y / FYC).abs();
    if phi >= 1.0 {
        if phi > 1.000001 {
            return None;
        }
        phi = FRAC_PI_2.copysign(y);
        lam /= robin(ROBIN_X[NODES])[0];
        return Some((lam, phi));
    }
    let mut i = ((phi * NODES as f64).floor() as usize).min(NODES - 1);
    loop {
        if robin(ROBIN_Y[i])[0] > phi {
            if i == 0 {
                break;
            }
            i -= 1;
        } else if robin(ROBIN_Y[i + 1])[0] <= phi {
            i += 1;
            if i >= NODES {
                return None;
            }
        } else {
            break;
        }
    }
    let t_row = robin(ROBIN_Y[i]);
    let mut t = 5.0 * (phi - t_row[0]) / (robin(ROBIN_Y[i + 1])[0] - t_row[0]);
    for _ in 0..100 {
        let t1 = (v(t_row, t) - phi) / dv(t_row, t);
        t -= t1;
        if t1.abs() < 1e-8 {
            break;
        }
    }
    let mut lat = (5.0 * i as f64 + t).to_radians();
    if y < 0.0 {
        lat = -lat;
    }
    lam /= v(robin(ROBIN_X[i]), t);
    Some((lam, lat))
}

/// PROJ's Natural Earth inverse: Newton on the y polynomial.
fn natural_earth_inverse(x: f64, y: f64) -> Option<(f64, f64)> {
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
    const C0: f64 = B0;
    const C1: f64 = 3.0 * B1;
    const C2: f64 = 7.0 * B2;
    const C3: f64 = 9.0 * B3;
    const C4: f64 = 11.0 * B4;
    let max_y = 0.8707 * 0.52 * PI;
    let y = y.clamp(-max_y, max_y);
    let mut yc = y;
    for _ in 0..100 {
        let y2 = yc * yc;
        let y4 = y2 * y2;
        let f = yc * (B0 + y2 * (B1 + y4 * (B2 + B3 * y2 + B4 * y4))) - y;
        let fder = C0 + y2 * (C1 + y4 * (C2 + C3 * y2 + C4 * y4));
        let tol = f / fder;
        yc -= tol;
        if tol.abs() < 1e-11 {
            break;
        }
    }
    let y2 = yc * yc;
    let lam = x / (A0 + y2 * (A1 + y2 * (A2 + y2 * y2 * y2 * (A3 + y2 * A4))));
    Some((lam, yc))
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
            let tol = 1e-6;
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

    /// Every projection's analytic inverse undoes its forward across the
    /// drawn region, to well under a metre.
    #[test]
    fn analytic_inverse_round_trips_on_a_grid() {
        for name in projection_names() {
            for origin in [None, Some((-178.0, -17.0)), Some((47.0, 62.0))] {
                let spec = ProjectionSpec { name: name.into(), lon_0: origin.map(|o| o.0), lat_0: origin.map(|o| o.1) };
                let p = Projection::new(&spec).unwrap();
                let mut checked = 0;
                for i in 0..=24 {
                    for j in 0..=24 {
                        let rel = -p.lon_halfspan * 0.98 + 2.0 * p.lon_halfspan * 0.98 * i as f64 / 24.0;
                        let lat = p.min_lat + (p.max_lat - p.min_lat) * (0.01 + 0.98 * j as f64 / 24.0);
                        let lon = wrap_lon(p.lon_0 + rel);
                        if p.is_globe() && p.cap_distance(lon, lat) > 89.0 {
                            continue;
                        }
                        let Some((x, y)) = p.forward(lon, lat) else { continue };
                        let (lon2, lat2) = p.inverse_raw(x, y).unwrap_or_else(|| panic!("{name} {spec:?}: ({lon}, {lat})"));
                        let (x2, y2) = p.forward(lon2, lat2).unwrap();
                        let tol = if p.is_geographic() { 1e-9 } else { 0.01 };
                        assert!(
                            (x - x2).abs() < tol && (y - y2).abs() < tol,
                            "{name} {spec:?}: ({lon}, {lat}) -> ({lon2}, {lat2}) off by ({}, {})",
                            x - x2,
                            y - y2
                        );
                        assert!((lat - lat2).abs() < 1e-6, "{name}: lat {lat} vs {lat2}");
                        checked += 1;
                    }
                }
                assert!(checked > 200, "{name}: only {checked}");
            }
        }
    }

    #[test]
    fn inverse_is_none_off_the_world() {
        let robin = proj("Robinson");
        let (x, y) = robin.forward(180.0, 60.0).unwrap();
        assert!(robin.inverse_raw(x * 1.1, y).is_none());
        let globe = proj(GLOBE);
        assert!(globe.inverse_raw(A * 1.01, 0.0).is_none());
        let moll = proj("Mollweide");
        assert!(moll.inverse_raw(0.0, A * 1.5).is_none());
        // A Lambert map inverts outside its region, as pyproj does.
        let lcc = proj("Lambert: N. America");
        let (x, y) = lcc.forward(0.0, 30.0).unwrap();
        let (lon, lat) = lcc.inverse_raw(x, y).unwrap();
        assert!((lon - 0.0).abs() < 1e-6 && (lat - 30.0).abs() < 1e-6);
        assert!(lcc.inverse(x, y).is_none());
    }

    #[test]
    fn seeded_winkel_inverse_matches_unseeded() {
        let p = proj("Winkel Tripel");
        let (x, y) = p.forward(150.0, -70.0).unwrap();
        let a = p.inverse_raw(x, y).unwrap();
        let b = p.inverse_seeded(x, y, Some((149.0, -69.5))).unwrap();
        assert!((a.0 - b.0).abs() < 1e-8 && (a.1 - b.1).abs() < 1e-8);
    }

    #[test]
    fn bounds_match_pymappr() {
        // pyproj via PyMappr's _bounds_from_grid.
        for (name, want) in [
            ("Robinson", [-17003189.700318325, 17003189.700318325, -8625154.6651, 8625154.6651]),
            ("Mollweide", [-18036151.73622525, 18036151.73622525, -9020047.847897757, 9020047.847897757]),
            ("Lambert: N. America", [-9125450.01792427, 9125450.01792427, -3633845.6166622792, 6140801.925019262]),
            (GLOBE, [-6378127.2855442865, 6378127.2855442865, -6356742.567109314, 6356742.567109314]),
        ] {
            let got = proj(name).bounds;
            for k in 0..4 {
                assert!((got[k] - want[k]).abs() < 1.0, "{name}: {got:?}");
            }
        }
        assert_eq!(proj("Equirectangular").bounds, [-180.0, 180.0, -90.0, 90.0]);
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
