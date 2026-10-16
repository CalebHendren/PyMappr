//! Reading locality tables and turning them into point datasets.
//!
//! A port of the parts of PyMappr's `pymappr/files/data_loader.py` that the
//! import flow needs: read a CSV/TSV/text file or spreadsheet as text, guess
//! which columns hold the coordinates, and parse every row.

use std::path::Path;

use calamine::{Reader, open_workbook_auto};
use serde::{Deserialize, Serialize};

use crate::coords::{Kind, parse_coordinate};

pub const SPREADSHEET_EXTENSIONS: &[&str] = &["xlsx", "xlsm", "xltx", "xltm", "xls", "ods"];

const LON_HINTS: &[&str] = &["lon", "lng", "long", "longitude", "x"];
const LAT_HINTS: &[&str] = &["lat", "latitude", "y"];

#[derive(Debug, thiserror::Error)]
pub enum TableError {
    #[error("could not read {path}: {source}")]
    Io { path: String, source: std::io::Error },
    #[error("could not read the file as a table: {0}")]
    Csv(#[from] csv::Error),
    #[error("could not read the spreadsheet: {0}")]
    Spreadsheet(String),
    #[error("{0}")]
    Invalid(String),
}

/// An all-text table: every cell is a string, short rows are padded.
#[derive(Debug, Clone, Default, Serialize)]
pub struct Table {
    pub headers: Vec<String>,
    pub rows: Vec<Vec<String>>,
    /// The 1-based file line each data row starts on (text files only).
    #[serde(skip)]
    pub source_lines: Option<Vec<usize>>,
}

impl Table {
    fn column(&self, name: &str) -> Option<usize> {
        self.headers.iter().position(|h| h == name)
    }
}

/// Which columns hold each field. `names` are the name/grouping columns in
/// order; `use_headers` keeps the original headers as their labels.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ColumnMapping {
    pub longitude: String,
    pub latitude: String,
    pub names: Vec<String>,
    pub use_headers: bool,
    pub header_row: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Point {
    pub lon: f64,
    pub lat: f64,
    pub names: Vec<String>,
    pub row: usize,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Dataset {
    pub name_labels: Vec<String>,
    pub points: Vec<Point>,
    /// One "row N: reason" message per row that had no usable coordinates.
    pub skipped: Vec<String>,
}

fn extension(path: &Path) -> String {
    path.extension().and_then(|e| e.to_str()).unwrap_or("").to_ascii_lowercase()
}

pub fn is_spreadsheet(path: &Path) -> bool {
    SPREADSHEET_EXTENSIONS.contains(&extension(path).as_str())
}

/// Worksheet names of a spreadsheet ([] for text formats).
pub fn list_sheets(path: &Path) -> Result<Vec<String>, TableError> {
    if !is_spreadsheet(path) {
        return Ok(Vec::new());
    }
    let book = open_workbook_auto(path).map_err(|e| TableError::Spreadsheet(e.to_string()))?;
    Ok(book.sheet_names().to_vec())
}

/// Read a delimited text file or spreadsheet as an all-text table.
///
/// `headers` says whether the first row holds column names; without one the
/// columns are named "Column 1", "Column 2", ... `sheet` picks a worksheet
/// (the first when `None`).
pub fn read_table(path: &Path, headers: bool, sheet: Option<&str>) -> Result<Table, TableError> {
    if is_spreadsheet(path) {
        return read_spreadsheet(path, headers, sheet);
    }
    let bytes = std::fs::read(path).map_err(|source| TableError::Io {
        path: path.display().to_string(),
        source,
    })?;
    let text = String::from_utf8_lossy(&bytes);
    let text = text.strip_prefix('\u{feff}').unwrap_or(&text);
    let sep = match extension(path).as_str() {
        "csv" => b',',
        "tsv" => b'\t',
        _ => sniff_delimiter(text),
    };
    parse_delimited(text, sep, headers)
}

/// The likeliest delimiter of a text table: the candidate that appears the
/// same, non-zero number of times on the most of the first lines.
pub fn sniff_delimiter(text: &str) -> u8 {
    let lines: Vec<&str> = text.lines().filter(|l| !l.trim().is_empty()).take(20).collect();
    let mut best = (b',', 0usize);
    for sep in [b',', b'\t', b';', b'|'] {
        let counts: Vec<usize> =
            lines.iter().map(|l| l.bytes().filter(|&b| b == sep).count()).collect();
        let Some(&first) = counts.first() else { continue };
        if first == 0 {
            continue;
        }
        let agree = counts.iter().filter(|&&c| c == first).count();
        if agree > best.1 {
            best = (sep, agree);
        }
    }
    best.0
}

pub fn parse_delimited(text: &str, sep: u8, headers: bool) -> Result<Table, TableError> {
    let mut reader = csv::ReaderBuilder::new()
        .delimiter(sep)
        .has_headers(false)
        .flexible(true)
        .trim(csv::Trim::Fields)
        .from_reader(text.as_bytes());

    // The csv reader places a record after a blank line on that blank line,
    // so number each record by its first non-newline byte instead.
    let bytes = text.as_bytes();
    let newlines: Vec<usize> =
        bytes.iter().enumerate().filter(|(_, b)| **b == b'\n').map(|(i, _)| i).collect();
    let line_at = |mut byte: usize| {
        while byte < bytes.len() && matches!(bytes[byte], b'\r' | b'\n') {
            byte += 1;
        }
        newlines.partition_point(|&n| n < byte) + 1
    };

    let mut records: Vec<(usize, Vec<String>)> = Vec::new();
    for record in reader.records() {
        let record = record?;
        // Like pandas, skip blank and whitespace-only lines but keep lines of
        // bare delimiters (",,").
        if record.len() == 1 && record[0].trim().is_empty() {
            continue;
        }
        let line = record.position().map_or(0, |p| line_at(p.byte() as usize));
        records.push((line, record.iter().map(str::to_string).collect()));
    }
    Ok(assemble(records, headers, true))
}

fn read_spreadsheet(path: &Path, headers: bool, sheet: Option<&str>) -> Result<Table, TableError> {
    let mut book = open_workbook_auto(path).map_err(|e| TableError::Spreadsheet(e.to_string()))?;
    let name = match sheet {
        Some(s) => s.to_string(),
        None => book
            .sheet_names()
            .first()
            .cloned()
            .ok_or_else(|| TableError::Spreadsheet("the workbook has no sheets".into()))?,
    };
    let range = book.worksheet_range(&name).map_err(|e| TableError::Spreadsheet(e.to_string()))?;
    let records = range
        .rows()
        .map(|row| row.iter().map(|c| c.to_string().trim().to_string()).collect::<Vec<_>>())
        .filter(|cells| cells.iter().any(|c| !c.is_empty()))
        .map(|cells| (0, cells))
        .collect();
    Ok(assemble(records, headers, false))
}

fn assemble(mut records: Vec<(usize, Vec<String>)>, headers: bool, keep_lines: bool) -> Table {
    let width = records.iter().map(|(_, r)| r.len()).max().unwrap_or(0);
    for (_, r) in &mut records {
        r.resize(width, String::new());
    }
    let header_names = if headers && !records.is_empty() {
        unique_headers(records.remove(0).1)
    } else {
        (1..=width).map(|i| format!("Column {i}")).collect()
    };
    let source_lines = keep_lines.then(|| records.iter().map(|(l, _)| *l).collect());
    Table {
        headers: header_names,
        rows: records.into_iter().map(|(_, r)| r).collect(),
        source_lines,
    }
}

/// Make header names unique the way pandas does ("a", "a.1", "a.2") and name
/// blank headers after their position.
fn unique_headers(raw: Vec<String>) -> Vec<String> {
    let mut out: Vec<String> = Vec::with_capacity(raw.len());
    for (i, h) in raw.into_iter().enumerate() {
        let base = if h.is_empty() { format!("Unnamed: {i}") } else { h };
        let mut name = base.clone();
        let mut n = 1;
        while out.contains(&name) {
            name = format!("{base}.{n}");
            n += 1;
        }
        out.push(name);
    }
    out
}

/// Guess whether the header row is really data: two or more numeric-looking
/// headers means the file probably has no header row.
pub fn headers_look_like_data(table: &Table) -> bool {
    table.headers.iter().filter(|h| h.trim().parse::<f64>().is_ok()).count() >= 2
}

/// The column a coordinate header most likely names: an exact hint ("lng"),
/// then one starting with a hint ("Long."), then one containing the whole
/// word ("decimalLongitude"). Short hints never match inside other words.
fn match_hint<'a>(columns: &'a [String], hints: &[&str]) -> Option<&'a String> {
    type Rule = fn(&str, &str) -> bool;
    let rules: [Rule; 3] = [
        |low, hint| low == hint,
        |low, hint| hint.len() > 1 && low.starts_with(hint),
        |low, hint| hint.len() > 4 && low.contains(hint),
    ];
    let lowered: Vec<(String, &String)> =
        columns.iter().map(|c| (c.trim().to_lowercase(), c)).collect();
    for rule in rules {
        for hint in hints {
            if let Some((_, original)) = lowered.iter().find(|(low, _)| rule(low, hint)) {
                return Some(original);
            }
        }
    }
    None
}

fn beyond_latitude(table: &Table, col: usize) -> bool {
    table
        .rows
        .iter()
        .filter_map(|r| r[col].trim().parse::<f64>().ok())
        .any(|v| v.abs() > 90.0)
}

/// Guess the column mapping from headers, falling back to position: the
/// last two columns are longitude and latitude (swapped when the values say
/// so) and everything else is a name column.
pub fn guess_mapping(table: &Table) -> Result<ColumnMapping, TableError> {
    let columns = &table.headers;
    let lon = match_hint(columns, LON_HINTS);
    let lat = match_hint(columns, LAT_HINTS);
    let (lon, lat) = match (lon, lat) {
        (Some(lon), Some(lat)) if lon != lat => (lon.clone(), lat.clone()),
        _ => {
            if columns.len() < 2 {
                return Err(TableError::Invalid(
                    "The file needs at least two columns (longitude, latitude)".into(),
                ));
            }
            let (i, j) = (columns.len() - 2, columns.len() - 1);
            if beyond_latitude(table, j) && !beyond_latitude(table, i) {
                (columns[j].clone(), columns[i].clone())
            } else {
                (columns[i].clone(), columns[j].clone())
            }
        }
    };
    let names = columns.iter().filter(|c| **c != lon && **c != lat).cloned().collect();
    Ok(ColumnMapping { longitude: lon, latitude: lat, names, use_headers: true, header_row: true })
}

/// Parse the coordinates, skipping (and reporting) rows without a usable
/// pair. Rows are numbered by the file line they start on when known,
/// otherwise by position.
pub fn build_dataset(table: &Table, mapping: &ColumnMapping) -> Result<Dataset, TableError> {
    let find = |name: &str| {
        table
            .column(name)
            .ok_or_else(|| TableError::Invalid(format!("no column named '{name}'")))
    };
    let lon_col = find(&mapping.longitude)?;
    let lat_col = find(&mapping.latitude)?;
    let name_cols = mapping.names.iter().map(|n| find(n)).collect::<Result<Vec<_>, _>>()?;

    let offset = if mapping.header_row { 2 } else { 1 };
    let line_of = |i: usize| match &table.source_lines {
        Some(lines) if lines.len() == table.rows.len() => lines[i],
        _ => i + offset,
    };

    let mut points = Vec::with_capacity(table.rows.len());
    let mut skipped = Vec::new();
    for (i, row) in table.rows.iter().enumerate() {
        let lon = parse_coordinate(&row[lon_col], Kind::Longitude);
        let lat = parse_coordinate(&row[lat_col], Kind::Latitude);
        match (lon, lat) {
            (Ok(lon), Ok(lat)) => points.push(Point {
                lon,
                lat,
                names: name_cols.iter().map(|&c| row[c].trim().to_string()).collect(),
                row: line_of(i),
            }),
            // The longitude error wins: it is the one a reader meets first.
            (Err(e), _) | (_, Err(e)) => skipped.push(format!("row {}: {e}", line_of(i))),
        }
    }
    let name_labels = if mapping.use_headers {
        mapping.names.clone()
    } else {
        (1..=mapping.names.len()).map(|i| format!("Name {i}")).collect()
    };
    Ok(Dataset { name_labels, points, skipped })
}

// A point is "far from the rest" when the nearest other point is at least
// this far away, and this many times further than points usually are from
// their nearest neighbour. Checked only for datasets small enough to compare
// every pair quickly.
const FAR_POINT_KM: f64 = 1000.0;
const FAR_POINT_FACTOR: f64 = 10.0;
const FAR_POINT_MAX_ROWS: usize = 5000;
const EARTH_KM: f64 = 6371.0;

fn unit(lon: f64, lat: f64) -> [f64; 3] {
    let (l, p) = (lon.to_radians(), lat.to_radians());
    [p.cos() * l.cos(), p.cos() * l.sin(), p.sin()]
}

fn nearest_km(v: &[f64; 3], others: &[[f64; 3]], skip: Option<usize>) -> f64 {
    let best = others
        .iter()
        .enumerate()
        .filter(|(j, _)| Some(*j) != skip)
        .map(|(_, o)| (v[0] * o[0] + v[1] * o[1] + v[2] * o[2]).clamp(-1.0, 1.0))
        .fold(-1.0f64, f64::max);
    best.acos() * EARTH_KM
}

/// Python's `{:g}`: six significant digits, no trailing zeros.
fn fmt_g(v: f64) -> String {
    if v == 0.0 {
        return "0".into();
    }
    let exp = v.abs().log10().floor() as i32;
    if !(-5..6).contains(&exp) {
        let s = format!("{:.5e}", v);
        let (m, e) = s.split_once('e').unwrap();
        let m = m.trim_end_matches('0').trim_end_matches('.');
        let e: i32 = e.parse().unwrap();
        return format!("{m}e{}{:02}", if e < 0 { '-' } else { '+' }, e.abs());
    }
    let decimals = (5 - exp).max(0) as usize;
    let s = format!("{v:.decimals$}");
    if s.contains('.') { s.trim_end_matches('0').trim_end_matches('.').to_string() } else { s }
}

/// Python's `{:,.0f}`.
fn fmt_thousands(v: f64) -> String {
    let n = v.round() as i64;
    let digits = n.unsigned_abs().to_string();
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(c);
    }
    if n < 0 { format!("-{out}") } else { out }
}

/// Plain-language notes on points far from all the others (a port of
/// PyMappr's `far_points`). A lone point an ocean away from the rest is
/// usually a coordinate typed without its minus sign or hemisphere letter;
/// each note names the row and, when flipping a sign puts the point among
/// the others, which sign. Empty when nothing stands out.
pub fn far_points(dataset: &Dataset) -> Vec<String> {
    let n = dataset.points.len();
    if !(5..=FAR_POINT_MAX_ROWS).contains(&n) {
        return Vec::new();
    }
    let vectors: Vec<[f64; 3]> = dataset.points.iter().map(|p| unit(p.lon, p.lat)).collect();
    let nearest: Vec<f64> = (0..n).map(|i| nearest_km(&vectors[i], &vectors, Some(i))).collect();
    let mut sorted = nearest.clone();
    sorted.sort_by(f64::total_cmp);
    let typical = if n % 2 == 1 { sorted[n / 2] } else { (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0 };
    let limit = FAR_POINT_KM.max(FAR_POINT_FACTOR * typical);
    let far: Vec<usize> = (0..n).filter(|&i| nearest[i] > limit).collect();
    if far.is_empty() || far.len() > n / 5 {
        return Vec::new(); // a widespread dataset, not a stray point
    }
    let rest: Vec<[f64; 3]> = (0..n).filter(|i| !far.contains(i)).map(|i| vectors[i]).collect();
    far.iter()
        .map(|&i| {
            let p = &dataset.points[i];
            let mut note = format!(
                "row {} ({}, {}) is {} km from the nearest other point",
                p.row,
                fmt_g(p.lat),
                fmt_g(p.lon),
                fmt_thousands(nearest[i])
            );
            for (what, lon, lat) in [
                ("longitude", -p.lon, p.lat),
                ("latitude", p.lon, -p.lat),
                ("longitude and latitude", -p.lon, -p.lat),
            ] {
                if nearest_km(&unit(lon, lat), &rest, None) <= limit {
                    note += &format!("; with the opposite sign on its {what} it would sit with the rest");
                    break;
                }
            }
            note + "."
        })
        .collect()
}

#[cfg(test)]
mod tests {
    //! Cases ported from PyMappr's tests/test_data_loader.py.
    use super::*;

    fn csv_table(text: &str) -> Table {
        parse_delimited(text, b',', true).unwrap()
    }

    #[test]
    fn documented_layout() {
        let t = csv_table(
            "County,City,Longitude,Latitude\n\
             Travis,Austin,-97.7431,30.2672\n\
             King,Seattle,\"122°19'59\"\"W\",\"47°36'35\"\"N\"\n\
             Suffolk,Boston,71 3 37 W,42 21 33 N\n",
        );
        let ds = build_dataset(&t, &guess_mapping(&t).unwrap()).unwrap();
        assert_eq!(ds.points.len(), 3);
        assert!(ds.skipped.is_empty());
        assert_eq!(ds.name_labels, ["County", "City"]);
        let p = &ds.points[1];
        assert_eq!(p.names[0], "King");
        assert!((p.lon + (122.0 + 19.0 / 60.0 + 59.0 / 3600.0)).abs() < 1e-9);
        assert!((p.lat - (47.0 + 36.0 / 60.0 + 35.0 / 3600.0)).abs() < 1e-9);
    }

    #[test]
    fn header_guessing() {
        let m = guess_mapping(&csv_table("lat,lng,place\n30.5,-97.1,Somewhere\n")).unwrap();
        assert_eq!((m.longitude.as_str(), m.latitude.as_str()), ("lng", "lat"));
        assert_eq!(m.names, ["place"]);

        let m = guess_mapping(&csv_table("Taxon,Locality,Long.,Lat.\nEleusis,Manaus,-60.0,-3.1\n"))
            .unwrap();
        assert_eq!((m.longitude.as_str(), m.latitude.as_str()), ("Long.", "Lat."));
        assert_eq!(m.names, ["Taxon", "Locality"]);

        let m = guess_mapping(&csv_table(
            "scientificName,decimalLatitude,decimalLongitude\nEleusis andina,-3.1,-60.0\n",
        ))
        .unwrap();
        assert_eq!(m.longitude, "decimalLongitude");
        assert_eq!(m.latitude, "decimalLatitude");
    }

    #[test]
    fn positional_fallback_and_swap() {
        let m = guess_mapping(&csv_table("A,B,C,D\nTravis,Austin,-97.7431,30.2672\n")).unwrap();
        assert_eq!(m.names, ["A", "B"]);
        assert_eq!((m.longitude.as_str(), m.latitude.as_str()), ("C", "D"));

        let m = guess_mapping(&csv_table("A,B,C\nx,30.2,-97.7\ny,31.0,-120.5\n")).unwrap();
        assert_eq!((m.longitude.as_str(), m.latitude.as_str()), ("C", "B"));
    }

    #[test]
    fn bad_rows_are_reported_with_file_lines() {
        let t = csv_table("Name,Longitude,Latitude\na,-97,30\n\nb,junk,30\nc,-97,95\n");
        let ds = build_dataset(&t, &guess_mapping(&t).unwrap()).unwrap();
        assert_eq!(ds.points.len(), 1);
        assert_eq!(ds.skipped.len(), 2);
        assert!(ds.skipped[0].starts_with("row 4: cannot parse longitude"), "{:?}", ds.skipped);
        assert!(ds.skipped[1].starts_with("row 5: latitude"), "{:?}", ds.skipped);
    }

    #[test]
    fn without_headers() {
        let t = parse_delimited("-97,30\n-98,31\n", b',', false).unwrap();
        assert_eq!(t.headers, ["Column 1", "Column 2"]);
        assert_eq!(t.rows.len(), 2);
        assert!(headers_look_like_data(&csv_table("-97,30\n-98,31\n")));
        assert!(!headers_look_like_data(&csv_table("lon,lat\n-98,31\n")));
    }

    #[test]
    fn sniffs_delimiters() {
        assert_eq!(sniff_delimiter("a;b;c\n1;2;3\n"), b';');
        assert_eq!(sniff_delimiter("a\tb\n1\t2\n"), b'\t');
        assert_eq!(sniff_delimiter("a,b\n1,2\n"), b',');
    }

    fn cluster(extra: &str) -> String {
        let rows: String = (0..12)
            .map(|i| format!("Sp,{:.2},{:.2}
", -88.0 - i as f64 * 0.3, 14.0 + i as f64 * 0.2))
            .collect();
        format!("Name,Longitude,Latitude
{rows}{extra}")
    }

    #[test]
    fn a_point_missing_its_minus_sign_is_pointed_out() {
        let t = csv_table(&cluster("Sp,88.21,15.53
"));
        let notes = far_points(&build_dataset(&t, &guess_mapping(&t).unwrap()).unwrap());
        assert_eq!(notes.len(), 1);
        assert!(notes[0].starts_with("row 14 (15.53, 88.21)"), "{}", notes[0]);
        assert!(notes[0].contains("opposite sign on its longitude"));
    }

    #[test]
    fn a_spread_out_dataset_raises_no_alarm() {
        let t = csv_table(&cluster(""));
        assert!(far_points(&build_dataset(&t, &guess_mapping(&t).unwrap()).unwrap()).is_empty());
        let seabirds = crate::pymappr_dir().join("sample_data/world_seabirds.csv");
        if let Ok(t) = read_table(&seabirds, true, None) {
            assert!(far_points(&build_dataset(&t, &guess_mapping(&t).unwrap()).unwrap()).is_empty());
        }
    }

    #[test]
    fn number_formats_match_python() {
        assert_eq!(fmt_g(15.53), "15.53");
        assert_eq!(fmt_g(-12.354055), "-12.3541");
        assert_eq!(fmt_g(88.0), "88");
        assert_eq!(fmt_thousands(17654.4), "17,654");
        assert_eq!(fmt_thousands(999.6), "1,000");
    }

    #[test]
    fn too_few_columns() {
        assert!(guess_mapping(&csv_table("only\n1\n")).is_err());
    }

    #[test]
    fn pymappr_sample_data() {
        let dir = crate::pymappr_dir().join("sample_data");
        let Ok(entries) = std::fs::read_dir(&dir) else { return };
        for entry in entries.flatten() {
            let path = entry.path();
            if extension(&path) != "csv" {
                continue;
            }
            let t = read_table(&path, true, None).unwrap();
            let ds = build_dataset(&t, &guess_mapping(&t).unwrap()).unwrap();
            assert!(!ds.points.is_empty(), "{}", path.display());
            assert!(ds.skipped.is_empty(), "{}: {:?}", path.display(), ds.skipped);
        }
    }
}
