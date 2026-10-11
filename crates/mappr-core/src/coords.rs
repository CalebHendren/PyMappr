//! Coordinate parsing: decimal degrees, DMS and hemisphere letters.
//!
//! A port of PyMappr's `pymappr/files/coords.py`; the accepted formats and the
//! error cases are the same.

use std::sync::LazyLock;

use fancy_regex::{Captures, Regex};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[error("{0}")]
pub struct CoordinateError(pub String);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    Longitude,
    Latitude,
}

impl Kind {
    fn name(self) -> &'static str {
        match self {
            Kind::Longitude => "longitude",
            Kind::Latitude => "latitude",
        }
    }

    fn hemispheres(self) -> &'static str {
        match self {
            Kind::Longitude => "EW",
            Kind::Latitude => "NS",
        }
    }

    pub fn limit(self) -> f64 {
        match self {
            Kind::Longitude => 180.0,
            Kind::Latitude => 90.0,
        }
    }
}

// Degree / minute / second markers, including the unicode variants commonly
// produced by GPS tools and spreadsheets.
const DEG_MARK: &str = r"[°ºd]|deg(?:rees)?";
const MIN_MARK: &str = r"[′ʹ']|m(?:in(?:utes)?)?";
const SEC_MARK: &str = r#"[″ʺ"]|''|s(?:ec(?:onds)?)?"#;
// The lookahead keeps a digit run whole: "120s" must not split into 12° 0".
const NUM: &str = r"\d+(?:[.,]\d+)?(?![\d.,])";

static DMS_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(&format!(
        r"(?i)^(?P<deg>{NUM})\s*(?:{DEG_MARK})?(?:[\s:]*(?P<min>{NUM})\s*(?P<minmark>{MIN_MARK})?)?(?:[\s:]*(?P<sec>{NUM})\s*(?:{SEC_MARK})?)?\s*$"
    ))
    .expect("DMS regex compiles")
});
static HEMI_PREFIX: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?is)^([NSEW])\s*(.*)$").unwrap());
static HEMI_SUFFIX: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?is)^(.*?)\s*([NSEW])$").unwrap());
static LEADING_SIGN: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[+-]\s*").unwrap());

fn to_float(text: &str) -> Option<f64> {
    text.replace(',', ".").parse::<f64>().ok()
}

fn dms(text: &str) -> Option<Captures<'_, str>> {
    DMS_RE.captures(text).ok().flatten()
}

fn hemi_sign(letter: char) -> f64 {
    if matches!(letter, 'S' | 'W') { -1.0 } else { 1.0 }
}

/// True when a trailing "s" closes a DMS value rather than meaning South.
///
/// The "s" must sit right against the seconds digits and the whole text must
/// read as degrees, minutes and seconds. It is then the seconds marker if the
/// minutes carry an explicit marker ("45d30m15s") or if the value is a
/// longitude, which has no South. Otherwise "45 30 15s" stays South, like
/// "45 30 15 S". A leading sign ("-122d30m15s") is not part of the DMS text.
fn is_seconds_marker(text: &str, letter: char, kind: Kind) -> bool {
    let chars: Vec<char> = text.chars().collect();
    let before_last = chars.len().checked_sub(2).map(|i| chars[i]);
    if !letter.eq_ignore_ascii_case(&'s') || !before_last.is_some_and(char::is_numeric) {
        return false;
    }
    let unsigned = LEADING_SIGN.replace(text, "");
    let Some(m) = dms(&unsigned) else { return false };
    if m.name("min").is_none() || m.name("sec").is_none() {
        return false;
    }
    kind == Kind::Longitude || m.name("minmark").is_some()
}

/// Parse `value` into signed decimal degrees.
pub fn parse_coordinate(value: &str, kind: Kind) -> Result<f64, CoordinateError> {
    let name = kind.name();
    let limit = kind.limit();
    let err = |msg: String| Err(CoordinateError(msg));

    let mut text = value.trim().to_string();
    if text.is_empty() {
        return err(format!("missing {name}"));
    }

    // Pull out an optional hemisphere letter from either end.
    let mut hemi: Option<char> = None;
    if let Some(m) = HEMI_PREFIX.captures(text.as_str()).ok().flatten() {
        hemi = m[1].chars().next().map(|c| c.to_ascii_uppercase());
        text = m[2].to_string();
    } else if let Some(m) = HEMI_SUFFIX.captures(text.as_str()).ok().flatten() {
        let letter = m[2].chars().next().unwrap();
        if !is_seconds_marker(&text, letter, kind) {
            hemi = Some(letter.to_ascii_uppercase());
            text = m[1].to_string();
        }
    }
    if let Some(letter) = hemi
        && !kind.hemispheres().contains(letter)
    {
        return err(format!("hemisphere '{letter}' is not valid for a {name}"));
    }

    // An explicit numeric sign; cannot be combined with a hemisphere letter.
    let mut neg = false;
    let mut text = text.trim();
    if let Some(first) = text.chars().next().filter(|c| matches!(c, '+' | '-')) {
        if hemi.is_some() {
            return err(format!("cannot combine a sign and a hemisphere letter in '{value}'"));
        }
        neg = first == '-';
        text = text[1..].trim();
    }

    let mut degrees = match to_float(text) {
        Some(d) => d,
        None => {
            let Some(m) = dms(text) else {
                return err(format!("cannot parse {name} '{value}'"));
            };
            let part = |key: &str| m.name(key).and_then(|g| to_float(g.as_str())).unwrap_or(0.0);
            let (deg, minutes, seconds) = (part("deg"), part("min"), part("sec"));
            if minutes >= 60.0 || seconds >= 60.0 {
                return err(format!("minutes/seconds must be < 60 in '{value}'"));
            }
            deg + minutes / 60.0 + seconds / 3600.0
        }
    };

    if neg {
        degrees = -degrees;
    }
    if let Some(letter) = hemi {
        degrees = degrees.abs() * hemi_sign(letter);
    }
    // Written this way round so NaN fails the check too.
    if !(-limit <= degrees && degrees <= limit) {
        return err(format!("{name} {degrees} out of range ±{limit}"));
    }
    Ok(degrees)
}

pub fn parse_longitude(value: &str) -> Result<f64, CoordinateError> {
    parse_coordinate(value, Kind::Longitude)
}

pub fn parse_latitude(value: &str) -> Result<f64, CoordinateError> {
    parse_coordinate(value, Kind::Latitude)
}

#[cfg(test)]
mod tests {
    //! Ported from PyMappr's tests/test_coords.py.
    use super::*;

    fn close(a: f64, b: f64) -> bool {
        (a - b).abs() <= 1e-9
    }
    fn lon(s: &str) -> f64 {
        parse_longitude(s).unwrap_or_else(|e| panic!("{s:?}: {e}"))
    }
    fn lat(s: &str) -> f64 {
        parse_latitude(s).unwrap_or_else(|e| panic!("{s:?}: {e}"))
    }

    #[test]
    fn decimal() {
        assert!(close(lon("-122.4194"), -122.4194));
        assert!(close(lat("37.7749"), 37.7749));
        assert!(close(lon("+122.5"), 122.5));
        assert!(close(lat("37,7749"), 37.7749));
        assert!(close(lon("122.4194 W"), -122.4194));
        assert!(close(lon("122.4194E"), 122.4194));
        assert!(close(lat("37.7749 S"), -37.7749));
        assert!(close(lon("W122.4194"), -122.4194));
        assert!(close(lat("n 37.7749"), 37.7749));
    }

    #[test]
    fn dms_forms() {
        let w = -(122.0 + 25.0 / 60.0 + 10.5 / 3600.0);
        let n = 37.0 + 46.0 / 60.0 + 29.6 / 3600.0;
        assert!(close(lon("122°25'10.5\"W"), w));
        assert!(close(lat("37°46'29.6\"N"), n));
        assert!(close(lat("37º46′29.6″N"), n));
        assert!(close(lon("122d 25m 10.5s W"), w));
        assert!(close(lon("122 25 10.5 W"), w));
        assert!(close(lat("37:46:29.6N"), n));
        assert!(close(lat("37°46.493'N"), 37.0 + 46.493 / 60.0));
        assert!(close(lon("-122 25 10.5"), w));
        assert!(close(lat("S 33 51 54"), -(33.0 + 51.0 / 60.0 + 54.0 / 3600.0)));
    }

    #[test]
    fn errors() {
        for s in ["", "not a coordinate", "181", "-180.1", "122.4 N", "-122.4 W", "nan"] {
            assert!(parse_longitude(s).is_err(), "{s:?} should fail");
        }
        for s in ["90.5", "37.7 E", "37 65 10 N"] {
            assert!(parse_latitude(s).is_err(), "{s:?} should fail");
        }
    }

    #[test]
    fn boundaries() {
        assert!(close(lon("180"), 180.0));
        assert!(close(lon("-180"), -180.0));
        assert!(close(lat("90"), 90.0));
        assert!(close(lat("-90"), -90.0));
    }

    #[test]
    fn seconds_marker_vs_south() {
        let v = 45.0 + 30.0 / 60.0 + 15.0 / 3600.0;
        let l = 120.0 + 30.0 / 60.0 + 15.0 / 3600.0;
        for s in ["45d30m15s", "45°30′15s", "45d 30m 15s"] {
            assert!(close(lat(s), v), "{s}");
        }
        for s in ["45 30 15s", "45 30 15 S", "45°30'15\"S", "S45d30m15s", "45d30m15 S"] {
            assert!(close(lat(s), -v), "{s}");
        }
        for s in ["120d30m15s", "120 30 15s"] {
            assert!(close(lon(s), l), "{s}");
        }
        assert!(parse_longitude("120 30 15 S").is_err());
        for s in ["30s", "120s", "45d30s"] {
            assert!(parse_longitude(s).is_err(), "{s}");
        }
        assert!(close(lat("30s"), -30.0));
        assert!(close(lat("45d30s"), -45.5));
    }

    #[test]
    fn signed_dms_keeps_its_seconds_marker() {
        let a = 122.0 + 30.0 / 60.0 + 15.0 / 3600.0;
        assert!(close(lon("-122d30m15s"), -a));
        assert!(close(lon("+122d30m15s"), a));
        assert!(close(lon("- 122 30 15s"), -a));
        assert!(close(lat("-45d30m15s"), -(45.0 + 30.0 / 60.0 + 15.0 / 3600.0)));
    }
}
