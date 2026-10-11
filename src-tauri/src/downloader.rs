//! Downloads and prepares the map data, as PyMappr's `scripts/fetch_data.py`
//! does: Natural Earth vector layers, the four raster basemaps (resized to
//! 5400×2700 JPEG), and optionally the biodiversity / ecoregion overlays.
//! Runs as a background job the UI polls.

use std::io::{Cursor, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use serde::Serialize;

use crate::core::Core;

/// Mirrors tried in order: the official S3 bucket, then the NACIS CDN.
const MIRRORS: [&str; 2] = [
    "https://naturalearth.s3.amazonaws.com/{scale}_{category}/{name}.zip",
    "https://naciscdn.org/naturalearth/{scale}/{category}/{name}.zip",
];

/// (scale, category, archive, probe shapefile when not "<archive>.shp").
const VECTOR_LAYERS: &[(&str, &str, &str, Option<&str>)] = &[
    ("110m", "cultural", "ne_110m_admin_0_countries", None),
    ("50m", "cultural", "ne_50m_admin_0_countries", None),
    ("10m", "cultural", "ne_10m_admin_0_countries", None),
    ("10m", "cultural", "ne_10m_admin_1_states_provinces", None),
    ("10m", "cultural", "ne_10m_admin_2_counties", None),
    ("50m", "cultural", "ne_50m_admin_0_sovereignty", None),
    ("50m", "cultural", "ne_50m_admin_0_map_units", None),
    ("50m", "cultural", "ne_50m_admin_0_map_subunits", None),
    ("10m", "cultural", "ne_10m_admin_0_disputed_areas", None),
    ("10m", "cultural", "ne_10m_admin_0_boundary_lines_disputed_areas", None),
    ("10m", "cultural", "ne_10m_admin_0_boundary_lines_maritime_indicator", None),
    ("10m", "cultural", "ne_10m_populated_places_simple", None),
    ("10m", "cultural", "ne_10m_urban_areas", None),
    ("10m", "cultural", "ne_10m_airports", None),
    ("10m", "cultural", "ne_10m_ports", None),
    ("10m", "cultural", "ne_10m_parks_and_protected_lands", Some("ne_10m_parks_and_protected_lands_area.shp")),
    ("10m", "cultural", "ne_10m_time_zones", None),
    ("10m", "cultural", "ne_10m_roads", None),
    ("110m", "physical", "ne_110m_lakes", None),
    ("50m", "physical", "ne_50m_lakes", None),
    ("10m", "physical", "ne_10m_lakes", None),
    ("110m", "physical", "ne_110m_rivers_lake_centerlines", None),
    ("50m", "physical", "ne_50m_rivers_lake_centerlines", None),
    ("10m", "physical", "ne_10m_rivers_lake_centerlines", None),
    ("110m", "physical", "ne_110m_ocean", None),
    ("50m", "physical", "ne_50m_ocean", None),
    ("10m", "physical", "ne_10m_ocean", None),
    ("110m", "physical", "ne_110m_land", None),
    ("50m", "physical", "ne_50m_land", None),
    ("10m", "physical", "ne_10m_land", None),
    ("10m", "physical", "ne_10m_glaciated_areas", None),
    ("50m", "physical", "ne_50m_antarctic_ice_shelves_polys", None),
    ("10m", "physical", "ne_10m_bathymetry_all", Some("ne_10m_bathymetry_L_0.shp")),
    ("10m", "physical", "ne_10m_reefs", None),
    ("10m", "physical", "ne_10m_playas", None),
    ("10m", "physical", "ne_10m_geography_regions_polys", None),
];

/// (archive, output JPEG in `basemap/`).
const BASEMAP_RASTERS: &[(&str, &str)] = &[
    ("NE1_50M_SR_W", "ne1_world.jpg"),
    ("NE2_50M_SR_W", "ne2_world.jpg"),
    ("GRAY_50M_SR_W", "gray_world.jpg"),
    ("HYP_50M_SR_W", "hyp_world.jpg"),
];
const BASEMAP_SIZE: (u32, u32) = (5400, 2700);

enum Source {
    Direct(&'static str),
    Zenodo(&'static str),
}

/// (layer folder, source, shapefile member to pick, credit).
const EXTRA_LAYERS: &[(&str, Source, Option<&str>, &str)] = &[
    (
        "ecoregions_2017",
        Source::Direct("https://storage.googleapis.com/teow2016/Ecoregions2017.zip"),
        Some("Ecoregions2017"),
        "RESOLVE Ecoregions 2017 (Dinerstein et al. 2017), CC-BY 4.0",
    ),
    (
        "biodiversity_hotspots",
        Source::Zenodo("3261807"),
        None,
        "Conservation International Biodiversity Hotspots (2016.1), CC-BY",
    ),
    (
        "marine_ecoregions",
        Source::Direct(
            "https://hub.arcgis.com/api/download/v1/items/903c3ae05b264c00a3b5e58a4561b7e6/shapefile?redirect=true&layers=0",
        ),
        None,
        "WWF/TNC Marine Ecoregions of the World (MEOW), CC-BY 4.0",
    ),
];

const SHAPE_EXTS: [&str; 5] = ["shp", "shx", "dbf", "prj", "cpg"];

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DataStatus {
    pub dir: String,
    pub vectors_ready: usize,
    pub vectors_total: usize,
    pub rasters_ready: usize,
    pub rasters_total: usize,
    pub extras_ready: Vec<String>,
}

fn vector_probe(data: &Path, name: &str, probe: Option<&str>) -> PathBuf {
    data.join("shapes").join(name).join(probe.map(str::to_string).unwrap_or(format!("{name}.shp")))
}

pub fn status(data: &Path) -> DataStatus {
    DataStatus {
        dir: data.display().to_string(),
        vectors_ready: VECTOR_LAYERS.iter().filter(|(_, _, n, p)| vector_probe(data, n, *p).is_file()).count(),
        vectors_total: VECTOR_LAYERS.len(),
        rasters_ready: BASEMAP_RASTERS.iter().filter(|(_, jpg)| data.join("basemap").join(jpg).is_file()).count(),
        rasters_total: BASEMAP_RASTERS.len(),
        extras_ready: EXTRA_LAYERS
            .iter()
            .filter(|(t, ..)| data.join("shapes").join(t).join(format!("{t}.shp")).is_file())
            .map(|(t, ..)| t.to_string())
            .collect(),
    }
}

pub struct Options {
    pub rasters: bool,
    pub extras: bool,
}

/// Start the download as a background job; returns its id.
pub fn start(core: &Arc<Core>, data: PathBuf, opts: Options) -> u64 {
    let id = core.jobs.start("Downloading map data");
    let core = Arc::clone(core);
    std::thread::spawn(move || {
        let result = run(&core, id, &data, &opts);
        if result.is_ok() {
            crate::cmd_app::use_data_dir(&core, &data);
        }
        core.jobs.finish(id, result.err());
    });
    id
}

fn client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .user_agent("RustyMappr-fetch-data")
        .timeout(Duration::from_secs(600))
        .build()
        .map_err(|e| e.to_string())
}

fn run(core: &Core, id: u64, data: &Path, opts: &Options) -> Result<(), String> {
    let client = client()?;
    let total = VECTOR_LAYERS.len()
        + if opts.rasters { BASEMAP_RASTERS.len() } else { 0 }
        + if opts.extras { EXTRA_LAYERS.len() } else { 0 };
    let mut done = 0usize;
    let progress = |done: usize, part: f64| Some((done as f64 + part.clamp(0.0, 1.0)) / total as f64);
    let check_cancel = || if core.jobs.is_cancelled(id) { Err("Download cancelled.".to_string()) } else { Ok(()) };

    for (scale, category, name, probe) in VECTOR_LAYERS {
        check_cancel()?;
        if !vector_probe(data, name, *probe).is_file() {
            let zip = download(&client, scale, category, name, data, &|part| {
                core.jobs.update(id, &format!("Downloading {name}"), progress(done, part))
            })?;
            core.jobs.update(id, &format!("Unpacking {name}"), progress(done, 1.0));
            extract_shapes(&zip, &data.join("shapes").join(name))?;
        }
        done += 1;
        core.jobs.update(id, &format!("Ready: {name}"), progress(done, 0.0));
    }

    if opts.rasters {
        for (name, jpg) in BASEMAP_RASTERS {
            check_cancel()?;
            let out = data.join("basemap").join(jpg);
            if !out.is_file() {
                let zip = download(&client, "50m", "raster", name, data, &|part| {
                    core.jobs.update(id, &format!("Downloading {name}"), progress(done, part))
                })?;
                core.jobs.update(id, &format!("Converting {name} to a JPEG basemap"), progress(done, 1.0));
                convert_raster(&zip, &out)?;
            }
            done += 1;
        }
    }

    if opts.extras {
        // Optional layers are best-effort: report and carry on.
        let mut skipped = Vec::new();
        for (target, source, member, credit) in EXTRA_LAYERS {
            check_cancel()?;
            let out = data.join("shapes").join(target);
            if !out.join(format!("{target}.shp")).is_file() {
                core.jobs.update(id, &format!("Downloading {target} ({credit})"), progress(done, 0.0));
                if let Err(e) = fetch_extra(&client, source, &out, target, *member) {
                    skipped.push(format!("{target}: {e}"));
                }
            }
            done += 1;
        }
        if !skipped.is_empty() {
            core.jobs.update(id, &format!("Skipped optional layers: {}", skipped.join("; ")), progress(done, 0.0));
        }
    }
    Ok(())
}

/// Fetch `url` with progress callbacks (0..1), into memory.
fn fetch(client: &reqwest::blocking::Client, url: &str, on_progress: &dyn Fn(f64)) -> Result<Vec<u8>, String> {
    let mut resp = client.get(url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("{url}: HTTP {}", resp.status()));
    }
    let len = resp.content_length();
    let mut out = Vec::with_capacity(len.unwrap_or(0) as usize);
    let mut buf = vec![0u8; 1 << 20];
    loop {
        let n = resp.read(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        out.extend_from_slice(&buf[..n]);
        if let Some(len) = len {
            on_progress(out.len() as f64 / len as f64);
        }
    }
    Ok(out)
}

/// Download a Natural Earth archive into `downloads/` (cached), trying each
/// mirror three times with backoff.
fn download(
    client: &reqwest::blocking::Client,
    scale: &str,
    category: &str,
    name: &str,
    data: &Path,
    on_progress: &dyn Fn(f64),
) -> Result<PathBuf, String> {
    let dest = data.join("downloads").join(format!("{name}.zip"));
    if dest.metadata().is_ok_and(|m| m.len() > 0) {
        return Ok(dest);
    }
    std::fs::create_dir_all(dest.parent().unwrap()).map_err(|e| e.to_string())?;
    let mut last = String::new();
    for mirror in MIRRORS {
        let url = mirror.replace("{scale}", scale).replace("{category}", category).replace("{name}", name);
        for attempt in 0..3 {
            match fetch(client, &url, on_progress) {
                Ok(bytes) => {
                    let tmp = dest.with_extension("part");
                    std::fs::File::create(&tmp)
                        .and_then(|mut f| f.write_all(&bytes))
                        .and_then(|_| std::fs::rename(&tmp, &dest))
                        .map_err(|e| e.to_string())?;
                    return Ok(dest);
                }
                Err(e) => {
                    last = e;
                    if attempt < 2 {
                        std::thread::sleep(Duration::from_secs(2u64.pow(attempt + 1)));
                    }
                }
            }
        }
    }
    Err(format!("Could not download {name} from any mirror ({last}). Check the internet connection and try again."))
}

fn extract_shapes(zip: &Path, out: &Path) -> Result<(), String> {
    let file = std::fs::File::open(zip).map_err(|e| e.to_string())?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("{}: {e}", zip.display()))?;
    std::fs::create_dir_all(out).map_err(|e| e.to_string())?;
    for i in 0..archive.len() {
        let mut entry = archive.by_index(i).map_err(|e| e.to_string())?;
        if entry.is_dir() {
            continue;
        }
        let full = entry.name().map(|n| n.into_owned()).unwrap_or_default();
        let name = Path::new(&full).file_name().map(|n| n.to_owned());
        let ext = Path::new(&full).extension().and_then(|e| e.to_str()).unwrap_or("").to_ascii_lowercase();
        if let Some(name) = name
            && SHAPE_EXTS.contains(&ext.as_str())
        {
            let mut bytes = Vec::with_capacity(entry.size() as usize);
            entry.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
            std::fs::write(out.join(name), bytes).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

fn convert_raster(zip: &Path, out: &Path) -> Result<(), String> {
    let file = std::fs::File::open(zip).map_err(|e| e.to_string())?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| e.to_string())?;
    let tif = (0..archive.len())
        .find(|&i| {
            archive
                .by_index(i)
                .is_ok_and(|e| e.name().is_ok_and(|n| n.to_ascii_lowercase().ends_with(".tif")))
        })
        .ok_or_else(|| format!("no .tif inside {}", zip.display()))?;
    let mut bytes = Vec::new();
    archive.by_index(tif).map_err(|e| e.to_string())?.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    let mut reader = image::ImageReader::new(Cursor::new(bytes));
    reader.no_limits();
    let img = reader.with_guessed_format().map_err(|e| e.to_string())?.decode().map_err(|e| e.to_string())?;
    let rgb = img.to_rgb8();
    let resized = image::imageops::resize(&rgb, BASEMAP_SIZE.0, BASEMAP_SIZE.1, image::imageops::FilterType::Lanczos3);
    std::fs::create_dir_all(out.parent().unwrap()).map_err(|e| e.to_string())?;
    let file = std::fs::File::create(out).map_err(|e| e.to_string())?;
    let mut enc = image::codecs::jpeg::JpegEncoder::new_with_quality(std::io::BufWriter::new(file), 85);
    enc.encode_image(&resized).map_err(|e| e.to_string())
}

fn zenodo_url(client: &reqwest::blocking::Client, record: &str) -> Result<String, String> {
    let api = format!("https://zenodo.org/api/records/{record}");
    let data: serde_json::Value = client.get(&api).send().and_then(|r| r.json()).map_err(|e| e.to_string())?;
    let files = data["files"].as_array().cloned().unwrap_or_default();
    let mut chosen: Vec<&serde_json::Value> =
        files.iter().filter(|f| f["key"].as_str().is_some_and(|k| k.to_lowercase().ends_with(".zip"))).collect();
    if chosen.is_empty() {
        chosen = files.iter().collect();
        chosen.sort_by_key(|f| std::cmp::Reverse(f["size"].as_u64().unwrap_or(0)));
    }
    let first = chosen.first().ok_or_else(|| format!("Zenodo record {record} has no downloadable files"))?;
    first["links"]["self"]
        .as_str()
        .or(first["links"]["download"].as_str())
        .map(str::to_string)
        .ok_or_else(|| format!("Zenodo record {record}: no file link"))
}

fn fetch_extra(
    client: &reqwest::blocking::Client,
    source: &Source,
    out: &Path,
    target: &str,
    member: Option<&str>,
) -> Result<(), String> {
    let url = match source {
        Source::Direct(u) => u.to_string(),
        Source::Zenodo(r) => zenodo_url(client, r)?,
    };
    let payload = fetch(client, &url, &|_| {})?;
    if !payload.starts_with(b"PK\x03\x04") {
        return Err("download was not a ZIP archive (the source may need a manual download)".into());
    }
    let mut archive = zip::ZipArchive::new(Cursor::new(payload)).map_err(|e| e.to_string())?;
    let names: Vec<String> = archive.file_names().filter_map(|n| n.ok().map(|n| n.into_owned())).collect();
    let shps: Vec<&String> = names.iter().filter(|n| n.to_lowercase().ends_with(".shp")).collect();
    let stem_of = |n: &str| Path::new(n).file_stem().and_then(|s| s.to_str()).unwrap_or("").to_string();
    let chosen = member
        .and_then(|m| shps.iter().find(|n| stem_of(n).eq_ignore_ascii_case(m)))
        .or(shps.first())
        .ok_or("no .shp inside archive")?;
    let stem = stem_of(chosen);
    std::fs::create_dir_all(out).map_err(|e| e.to_string())?;
    let mut wrote_shp = false;
    for name in &names {
        let path = Path::new(name);
        let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("").to_ascii_lowercase();
        if stem_of(name) == stem && SHAPE_EXTS.contains(&ext.as_str()) {
            let mut bytes = Vec::new();
            archive.by_name(name).map_err(|e| e.to_string())?.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
            std::fs::write(out.join(format!("{target}.{ext}")), bytes).map_err(|e| e.to_string())?;
            wrote_shp |= ext == "shp";
        }
    }
    if wrote_shp { Ok(()) } else { Err("archive missing shapefile components".into()) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_counts_what_is_on_disk() {
        let dir = std::env::temp_dir().join("rustymappr-status-test");
        let _ = std::fs::remove_dir_all(&dir);
        let st = status(&dir);
        assert_eq!(st.vectors_ready, 0);
        assert_eq!(st.vectors_total, VECTOR_LAYERS.len());
        std::fs::create_dir_all(dir.join("shapes/ne_110m_land")).unwrap();
        std::fs::write(dir.join("shapes/ne_110m_land/ne_110m_land.shp"), b"x").unwrap();
        assert_eq!(status(&dir).vectors_ready, 1);
    }

    /// Downloads one small layer from Natural Earth; run with --ignored.
    #[test]
    #[ignore]
    fn downloads_and_unpacks_a_layer() {
        let dir = std::env::temp_dir().join("rustymappr-download-test");
        let _ = std::fs::remove_dir_all(&dir);
        let client = client().unwrap();
        let zip = download(&client, "110m", "physical", "ne_110m_land", &dir, &|_| {}).unwrap();
        extract_shapes(&zip, &dir.join("shapes/ne_110m_land")).unwrap();
        assert!(mappr_core::basemap::Basemap::looks_valid(&dir.join("shapes")));
    }
}
