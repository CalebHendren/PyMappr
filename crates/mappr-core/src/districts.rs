//! Download, store, list, remove and load geoBoundaries "gbOpen" ADM2
//! (district) boundaries, one file per country.
//!
//! Files live in `<data_dir>/districts/`: `<ISO3>.geojson` holds the
//! simplified boundaries and `<ISO3>.json` holds a [`DistrictMeta`] record.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};

const API_BASE: &str = "https://www.geoboundaries.org/api/current/gbOpen";

/// One downloaded country, as listed in the UI.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DistrictMeta {
    /// Upper-case ISO3 code, e.g. "KEN".
    pub iso3: String,
    /// Country name from the API's `boundaryName`.
    pub name: String,
    /// The API's `boundaryLicense`.
    pub license: String,
    /// The GeoJSON URL the file was downloaded from.
    pub source: String,
}

/// One district: its name and polygons. Each polygon is a list of rings
/// (first = exterior, rest = holes); each ring a list of `[lon, lat]`.
#[derive(Debug, Clone)]
pub struct District {
    /// District name (empty when the feature has none).
    pub name: String,
    /// Polygons of the district.
    pub polygons: Vec<Vec<Vec<[f64; 2]>>>,
}

/// Errors from downloading, storing or reading district boundaries.
#[derive(Debug, thiserror::Error)]
pub enum DistrictError {
    /// A file could not be read, written or removed.
    #[error("Could not access {path}: {source}")]
    Io {
        /// The file or directory involved.
        path: PathBuf,
        /// The underlying error.
        source: io::Error,
    },
    /// The request to geoBoundaries failed.
    #[error("Could not reach geoBoundaries: {0}")]
    Network(String),
    /// geoBoundaries has no ADM2 data for the country.
    #[error("geoBoundaries has no districts for {0}")]
    NoDistricts(String),
    /// The downloaded or stored data is not valid.
    #[error("The district data could not be read: {0}")]
    Parse(String),
    /// The country code is not three ASCII letters.
    #[error("\"{0}\" is not a valid ISO3 country code (expected three letters, e.g. KEN)")]
    BadCode(String),
}

fn io_err(path: &Path, source: io::Error) -> DistrictError {
    DistrictError::Io {
        path: path.to_path_buf(),
        source,
    }
}

/// `<data_dir>/districts`
pub fn districts_dir(data_dir: &Path) -> PathBuf {
    data_dir.join("districts")
}

/// `<data_dir>/districts/<ISO3>.geojson`
pub fn geojson_path(data_dir: &Path, iso3: &str) -> PathBuf {
    districts_dir(data_dir).join(format!("{iso3}.geojson"))
}

fn meta_path(data_dir: &Path, iso3: &str) -> PathBuf {
    districts_dir(data_dir).join(format!("{iso3}.json"))
}

fn normalize_iso3(iso3: &str) -> Result<String, DistrictError> {
    let code = iso3.trim();
    if code.len() == 3 && code.chars().all(|c| c.is_ascii_alphabetic()) {
        Ok(code.to_ascii_uppercase())
    } else {
        Err(DistrictError::BadCode(iso3.to_string()))
    }
}

/// Every downloaded country, sorted by name, read from the `<ISO3>.json` meta
/// files. Entries whose `.geojson` is missing or whose meta does not parse are
/// skipped.
pub fn list(data_dir: &Path) -> Vec<DistrictMeta> {
    let dir = districts_dir(data_dir);
    let Ok(entries) = fs::read_dir(&dir) else {
        return Vec::new();
    };
    let mut metas: Vec<DistrictMeta> = entries
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|e| e == "json"))
        .filter_map(|p| {
            let meta: DistrictMeta = serde_json::from_str(&fs::read_to_string(&p).ok()?).ok()?;
            let stem = p.file_stem()?.to_str()?;
            dir.join(format!("{stem}.geojson"))
                .is_file()
                .then_some(meta)
        })
        .collect();
    metas.sort_by_key(|m| (m.name.to_lowercase(), m.iso3.clone()));
    metas
}

/// Delete `<ISO3>.geojson` and `<ISO3>.json` (missing files are not an error).
pub fn remove(data_dir: &Path, iso3: &str) -> Result<(), DistrictError> {
    let iso3 = normalize_iso3(iso3)?;
    for path in [geojson_path(data_dir, &iso3), meta_path(data_dir, &iso3)] {
        match fs::remove_file(&path) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(io_err(&path, e)),
        }
    }
    Ok(())
}

fn http_client() -> Result<reqwest::blocking::Client, DistrictError> {
    // reqwest is built without a bundled crypto provider, so install ring once.
    // An error only means a provider is already installed.
    let _ = rustls::crypto::ring::default_provider().install_default();
    reqwest::blocking::Client::builder()
        .user_agent("RustyMappr")
        .connect_timeout(Duration::from_secs(20))
        .timeout(Duration::from_secs(300))
        .build()
        .map_err(|e| DistrictError::Network(e.to_string()))
}

fn get(
    client: &reqwest::blocking::Client,
    url: &str,
) -> Result<reqwest::blocking::Response, DistrictError> {
    client
        .get(url)
        .send()
        .map_err(|e| DistrictError::Network(e.to_string()))
}

/// Download one country's districts into `data_dir`. `progress` receives short
/// human-readable steps. Blocking. The code is validated and upper-cased.
pub fn fetch(
    data_dir: &Path,
    iso3: &str,
    progress: &mut dyn FnMut(&str),
) -> Result<DistrictMeta, DistrictError> {
    let iso3 = normalize_iso3(iso3)?;
    let client = http_client()?;

    progress(&format!("Asking geoBoundaries for {iso3}"));
    let resp = get(&client, &format!("{API_BASE}/{iso3}/ADM2/"))?;
    if !resp.status().is_success() {
        return Err(DistrictError::NoDistricts(iso3));
    }
    let reply = resp
        .text()
        .map_err(|e| DistrictError::Network(e.to_string()))?;
    let body: serde_json::Value = serde_json::from_str(&reply)
        .map_err(|e| DistrictError::Parse(format!("unexpected reply from geoBoundaries ({e})")))?;
    let info = match &body {
        serde_json::Value::Array(items) => items.first(),
        other => Some(other),
    };
    let field = |name: &str| -> Option<String> {
        info.and_then(|v| v.get(name))
            .and_then(|v| v.as_str())
            .map(str::to_string)
    };
    let Some(source) = field("simplifiedGeometryGeoJSON").filter(|s| !s.is_empty()) else {
        return Err(DistrictError::NoDistricts(iso3));
    };
    let name = field("boundaryName")
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| iso3.clone());
    let license = field("boundaryLicense").unwrap_or_default();

    progress(&format!("Downloading {name} districts"));
    let resp = get(&client, &source)?;
    if !resp.status().is_success() {
        return Err(DistrictError::Network(format!(
            "the district file for {iso3} could not be downloaded (HTTP {})",
            resp.status().as_u16()
        )));
    }
    let text = resp
        .text()
        .map_err(|e| DistrictError::Network(e.to_string()))?;

    progress("Checking the boundaries");
    parse(&text)?;

    progress(&format!("Saving {name} districts"));
    let dir = districts_dir(data_dir);
    fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;
    write_atomic(&geojson_path(data_dir, &iso3), text.as_bytes())?;

    let meta = DistrictMeta {
        iso3: iso3.clone(),
        name,
        license,
        source,
    };
    let json =
        serde_json::to_string_pretty(&meta).map_err(|e| DistrictError::Parse(e.to_string()))?;
    write_atomic(&meta_path(data_dir, &iso3), json.as_bytes())?;
    Ok(meta)
}

/// Write to a `.part` sibling, then rename over the target.
fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), DistrictError> {
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(".part");
    let tmp = PathBuf::from(tmp);
    fs::write(&tmp, bytes).map_err(|e| io_err(&tmp, e))?;
    fs::rename(&tmp, path).map_err(|e| {
        let _ = fs::remove_file(&tmp);
        io_err(path, e)
    })
}

/// Parse a downloaded file into districts.
pub fn load(path: &Path) -> Result<Vec<District>, DistrictError> {
    let text = fs::read_to_string(path).map_err(|e| io_err(path, e))?;
    parse(&text)
}

/// Parse GeoJSON text (a FeatureCollection or a single Feature) into
/// districts, keeping only Polygon and MultiPolygon features.
pub fn parse(text: &str) -> Result<Vec<District>, DistrictError> {
    let gj: geojson::GeoJson = text
        .parse()
        .map_err(|e: geojson::Error| DistrictError::Parse(e.to_string()))?;
    let features = match gj {
        geojson::GeoJson::FeatureCollection(fc) => fc.features,
        geojson::GeoJson::Feature(f) => vec![f],
        geojson::GeoJson::Geometry(_) => {
            return Err(DistrictError::Parse(
                "expected a FeatureCollection of districts".into(),
            ));
        }
    };
    let mut out = Vec::new();
    for feature in features {
        let Some(geometry) = feature.geometry else {
            continue;
        };
        let polygons = match geometry.value {
            geojson::GeometryValue::Polygon { coordinates } => vec![convert_polygon(&coordinates)],
            geojson::GeometryValue::MultiPolygon { coordinates } => {
                coordinates.iter().map(|p| convert_polygon(p)).collect()
            }
            _ => continue,
        };
        let name = ["shapeName", "name", "NAME"]
            .iter()
            .find_map(|k| feature.properties.as_ref()?.get(*k)?.as_str())
            .unwrap_or("")
            .to_string();
        out.push(District { name, polygons });
    }
    Ok(out)
}

fn convert_polygon(rings: &[Vec<geojson::Position>]) -> Vec<Vec<[f64; 2]>> {
    rings
        .iter()
        .filter(|r| r.len() >= 3)
        .map(|r| {
            r.iter()
                .filter(|p| p.len() >= 2)
                .map(|p| [p[0], p[1]])
                .collect()
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/data/districts_fixture.geojson"
    );

    fn temp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("districts-test-{tag}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn parses_fixture() {
        let d = load(Path::new(FIXTURE)).unwrap();
        assert_eq!(d.len(), 2);
        assert_eq!(d[0].name, "Alpha");
        assert_eq!(d[0].polygons.len(), 1);
        assert_eq!(d[0].polygons[0].len(), 2, "exterior plus one hole");
        assert_eq!(d[0].polygons[0][1][0], [2.0, 2.0]);
        assert_eq!(d[1].name, "Beta");
        assert_eq!(d[1].polygons.len(), 2);
        assert_eq!(d[1].polygons[1][0][0], [40.0, 0.0]);
    }

    #[test]
    fn parse_rejects_garbage() {
        assert!(matches!(parse("not json"), Err(DistrictError::Parse(_))));
    }

    #[test]
    fn list_remove_round_trip() {
        let data = temp_dir("list");
        let dir = districts_dir(&data);
        fs::create_dir_all(&dir).unwrap();
        for (iso, name) in [("KEN", "Kenya"), ("BEL", "Belgium")] {
            let meta = DistrictMeta {
                iso3: iso.into(),
                name: name.into(),
                license: "CC BY 4.0".into(),
                source: "https://example.org/x.geojson".into(),
            };
            fs::write(
                dir.join(format!("{iso}.json")),
                serde_json::to_string_pretty(&meta).unwrap(),
            )
            .unwrap();
            fs::copy(FIXTURE, geojson_path(&data, iso)).unwrap();
        }
        // Meta without a geojson, and a broken meta, are skipped.
        fs::write(
            dir.join("ZZZ.json"),
            r#"{"iso3":"ZZZ","name":"Zed","license":"","source":""}"#,
        )
        .unwrap();
        fs::write(dir.join("BAD.json"), "{").unwrap();

        let names: Vec<_> = list(&data).into_iter().map(|m| m.name).collect();
        assert_eq!(names, ["Belgium", "Kenya"]);

        remove(&data, "ken").unwrap();
        remove(&data, "KEN").unwrap();
        let names: Vec<_> = list(&data).into_iter().map(|m| m.name).collect();
        assert_eq!(names, ["Belgium"]);
        assert!(!geojson_path(&data, "KEN").exists());
        let _ = fs::remove_dir_all(&data);
    }

    #[test]
    fn list_of_missing_dir_is_empty() {
        assert!(list(&std::env::temp_dir().join("districts-no-such-dir-xyz")).is_empty());
    }

    #[test]
    fn rejects_bad_codes() {
        let data = temp_dir("bad");
        for code in ["K3N", "KENYA", "", "KE"] {
            assert!(
                matches!(normalize_iso3(code), Err(DistrictError::BadCode(_))),
                "{code}"
            );
            assert!(matches!(
                fetch(&data, code, &mut |_| {}),
                Err(DistrictError::BadCode(_))
            ));
        }
        assert_eq!(normalize_iso3("ken").unwrap(), "KEN");
        let _ = fs::remove_dir_all(&data);
    }

    #[test]
    #[ignore = "needs network access"]
    fn fetches_luxembourg() {
        let data = temp_dir("net");
        let mut steps = Vec::new();
        let meta = fetch(&data, "lux", &mut |s| steps.push(s.to_string())).unwrap();
        println!("{steps:?} {meta:?}");
        assert_eq!(meta.iso3, "LUX");
        let listed = list(&data);
        assert_eq!(listed, vec![meta]);
        assert!(!load(&geojson_path(&data, "LUX")).unwrap().is_empty());
        let _ = fs::remove_dir_all(&data);
    }
}
