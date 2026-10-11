//! Config values written as Python and R source (PyMappr's
//! `pymappr/export/literals.py`), and the bits of Python's own formatting
//! the scripts depend on: `repr()` of floats and strings, `round()`.

/// A Python value, as the code export writes it. Tuples and lists are kept
/// apart because they print differently.
#[derive(Debug, Clone, PartialEq)]
pub enum Lit {
    None,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    List(Vec<Lit>),
    Tuple(Vec<Lit>),
    Dict(Vec<(Lit, Lit)>),
}

impl Lit {
    pub fn str(s: impl Into<String>) -> Lit {
        Lit::Str(s.into())
    }

    pub fn opt_str(s: Option<&str>) -> Lit {
        s.map_or(Lit::None, Lit::str)
    }

    pub fn opt_float(v: Option<f64>) -> Lit {
        v.map_or(Lit::None, Lit::Float)
    }

    pub fn dict<K: Into<String>>(pairs: Vec<(K, Lit)>) -> Lit {
        Lit::Dict(pairs.into_iter().map(|(k, v)| (Lit::Str(k.into()), v)).collect())
    }

    pub fn floats(values: &[f64]) -> Lit {
        Lit::Tuple(values.iter().map(|v| Lit::Float(*v)).collect())
    }

    /// The value as a number, for comparisons (`2 == 2.0` in Python).
    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Lit::Int(i) => Some(*i as f64),
            Lit::Float(f) => Some(*f),
            Lit::Bool(b) => Some(f64::from(u8::from(*b))),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Lit::Str(s) => Some(s),
            _ => None,
        }
    }

    /// Python's `==`: numbers compare by value whatever their type.
    pub fn py_eq(&self, other: &Lit) -> bool {
        match (self.as_f64(), other.as_f64()) {
            (Some(a), Some(b)) => a == b,
            _ => self == other,
        }
    }

    /// Python truthiness.
    pub fn truthy(&self) -> bool {
        match self {
            Lit::None => false,
            Lit::Bool(b) => *b,
            Lit::Int(i) => *i != 0,
            Lit::Float(f) => *f != 0.0,
            Lit::Str(s) => !s.is_empty(),
            Lit::List(v) | Lit::Tuple(v) => !v.is_empty(),
            Lit::Dict(v) => !v.is_empty(),
        }
    }
}

// ------------------------------------------------------------ Python floats

/// Python's `round(x, ndigits)`: correctly rounded, ties to even.
pub fn round_to(x: f64, ndigits: usize) -> f64 {
    if !x.is_finite() {
        return x;
    }
    format!("{x:.ndigits$}").parse().unwrap_or(x)
}

pub fn round6(x: f64) -> f64 {
    round_to(x, 6)
}

/// Python's `repr()` of a float (shortest round-trip digits, `1e-05` style
/// exponents past the fixed-notation range, `.0` on whole numbers).
pub fn float_repr(x: f64) -> String {
    if x.is_nan() {
        return "nan".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".into() } else { "-inf".into() };
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0".into() } else { "0.0".into() };
    }
    let sci = format!("{x:e}");
    let (mantissa, exp) = sci.split_once('e').expect("exponent");
    let exp: i32 = exp.parse().expect("exponent");
    let negative = mantissa.starts_with('-');
    let digits: String = mantissa.chars().filter(|c| c.is_ascii_digit()).collect();
    let decpt = exp + 1;
    let n = digits.len() as i32;
    let body = if -4 < decpt && decpt <= 16 {
        if decpt <= 0 {
            format!("0.{}{}", "0".repeat((-decpt) as usize), digits)
        } else if decpt >= n {
            format!("{}{}.0", digits, "0".repeat((decpt - n) as usize))
        } else {
            format!("{}.{}", &digits[..decpt as usize], &digits[decpt as usize..])
        }
    } else {
        let rest = if n > 1 { format!(".{}", &digits[1..]) } else { String::new() };
        let e = decpt - 1;
        format!("{}{}e{}{:02}", &digits[..1], rest, if e < 0 { '-' } else { '+' }, e.abs())
    };
    if negative { format!("-{body}") } else { body }
}

// ----------------------------------------------------------- Python strings

/// Python's `str.isprintable()` for one character, without the Unicode
/// database: control and format characters, separators other than the
/// space, surrogates and private use are not printable. Unassigned code
/// points (also unprintable in Python) are not known here.
fn is_printable(c: char) -> bool {
    let u = c as u32;
    if u < 0x20 || (0x7f..=0xa0).contains(&u) {
        return false;
    }
    !matches!(u,
        0xad | 0x600..=0x605 | 0x61c | 0x6dd | 0x70f | 0x890..=0x891 | 0x8e2 | 0x1680 | 0x180e
        | 0x2000..=0x200f | 0x2028..=0x202f | 0x205f..=0x2064 | 0x2066..=0x206f | 0x3000
        | 0xd800..=0xf8ff | 0xfeff | 0xfff9..=0xfffb | 0x110bd | 0x110cd | 0x13430..=0x1343f
        | 0x1bca0..=0x1bca3 | 0x1d173..=0x1d17a | 0xe0001 | 0xe0020..=0xe007f
        | 0xf0000..=0xffffd | 0x100000..=0x10fffd)
}

/// Python's `repr()` of a string.
pub fn str_repr(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if is_printable(c) => out.push(c),
            c => {
                let u = c as u32;
                if u < 0x100 {
                    out.push_str(&format!("\\x{u:02x}"));
                } else if u < 0x10000 {
                    out.push_str(&format!("\\u{u:04x}"));
                } else {
                    out.push_str(&format!("\\U{u:08x}"));
                }
            }
        }
    }
    out.push(quote);
    out
}

/// Python's `str.isspace()` for one character.
pub fn is_py_space(c: char) -> bool {
    c.is_whitespace() || ('\x1c'..='\x1f').contains(&c)
}

/// Python's `str.strip()`.
pub fn py_strip(s: &str) -> &str {
    s.trim_matches(is_py_space)
}

/// Python's `str.casefold()`, near enough for sorting legend rows.
pub fn casefold(s: &str) -> String {
    s.to_lowercase().replace('ß', "ss")
}

// ---------------------------------------------------------------- literals

/// A Python literal for a config value (`_py`). Floats are rounded to 6
/// places; NaN and infinity become `float()` calls; NULs are dropped.
pub fn py(value: &Lit) -> String {
    match value {
        Lit::None => "None".into(),
        Lit::Bool(b) => if *b { "True" } else { "False" }.into(),
        Lit::Int(i) => i.to_string(),
        Lit::Float(f) => {
            if f.is_nan() {
                "float(\"nan\")".into()
            } else if f.is_infinite() {
                if *f > 0.0 { "float(\"inf\")".into() } else { "-float(\"inf\")".into() }
            } else {
                float_repr(round6(*f))
            }
        }
        Lit::Str(s) => str_repr(&s.replace('\0', "")),
        Lit::List(items) => format!("[{}]", items.iter().map(py).collect::<Vec<_>>().join(", ")),
        Lit::Tuple(items) => {
            let inner: Vec<String> = items.iter().map(py).collect();
            format!("({}{})", inner.join(", "), if inner.len() == 1 { "," } else { "" })
        }
        Lit::Dict(pairs) => format!(
            "{{{}}}",
            pairs.iter().map(|(k, v)| format!("{}: {}", py(k), py(v))).collect::<Vec<_>>().join(", ")
        ),
    }
}

/// An R string literal (`_r` on text).
pub fn r_str(text: &str) -> String {
    let text = text
        .replace('\0', "")
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "")
        .replace('\t', "\\t");
    format!("\"{text}\"")
}

/// An R literal for a config value (`_r`). NaN and infinity become R's own
/// `NA_real_`, `Inf` and `-Inf`.
pub fn r(value: &Lit) -> String {
    match value {
        Lit::None => "NULL".into(),
        Lit::Bool(b) => if *b { "TRUE" } else { "FALSE" }.into(),
        Lit::Int(i) => i.to_string(),
        Lit::Float(f) => {
            if f.is_nan() {
                "NA_real_".into()
            } else if f.is_infinite() {
                if *f > 0.0 { "Inf".into() } else { "-Inf".into() }
            } else {
                float_repr(round6(*f))
            }
        }
        Lit::Str(s) => r_str(s),
        // PyMappr writes str(value) for anything else; never reached.
        other => r_str(&py(other)),
    }
}

pub fn rf(value: f64) -> String {
    r(&Lit::Float(value))
}

/// *text* made safe for a one-line `#` comment in either language.
pub fn comment_text(text: &str) -> String {
    let text = text.replace('\0', "");
    let mut out = String::with_capacity(text.len());
    let mut in_break = false;
    for c in text.chars() {
        if c == '\r' || c == '\n' {
            if !in_break {
                out.push(' ');
            }
            in_break = true;
        } else {
            in_break = false;
            out.push(c);
        }
    }
    py_strip(&out).to_string()
}

/// An R `c(...)` or `list(...)` body: one `name = value` per line.
pub fn r_named(pairs: &[(String, String)], indent: &str) -> String {
    let inner: Vec<String> = pairs.iter().map(|(name, value)| format!("{} = {value}", r_str(name))).collect();
    format!("\n{indent}{}\n{}", inner.join(&format!(",\n{indent}")), &indent[..indent.len() - 2])
}

/// Matplotlib scatter area (points^2) -> approximate ggplot2 size.
pub fn size_mm(area: f64) -> f64 {
    round_to((area.max(1.0).sqrt() / 2.845).max(0.3), 2)
}

/// Matplotlib line width (points) -> approximate ggplot2 linewidth.
pub fn linewidth_mm(width: f64) -> f64 {
    round_to((width / 2.13).max(0.05), 2)
}

/// ggplot2 linetype name approximating a renderer dash tuple.
pub fn r_linetype(linestyle: &Lit) -> &'static str {
    let Lit::Tuple(parts) = linestyle else { return "solid" };
    let offset = parts.first().and_then(Lit::as_f64);
    let dashes: Option<Vec<f64>> = match parts.get(1) {
        Some(Lit::Tuple(d) | Lit::List(d)) => d.iter().map(Lit::as_f64).collect(),
        _ => None,
    };
    match (offset, dashes.as_deref()) {
        (Some(0.0), Some([a, b])) => match (*a, *b) {
            (1.0, 2.0) => "dotted",
            (3.0, 2.0) | (3.0, 3.0) | (4.0, 2.0) => "dashed",
            (5.0, 3.0) | (6.0, 3.0) => "longdash",
            _ => "dashed",
        },
        _ => "dashed",
    }
}

/// A project name on one line and free of double quotes.
pub fn safe_name(name: &str) -> String {
    let mut out = String::with_capacity(name.len());
    let mut in_ctrl = false;
    for c in name.chars() {
        if (c as u32) < 0x20 || c == '\x7f' {
            if !in_ctrl {
                out.push(' ');
            }
            in_ctrl = true;
        } else {
            in_ctrl = false;
            out.push(if c == '"' { '\'' } else { c });
        }
    }
    let stripped = py_strip(&out);
    if stripped.is_empty() { "map".into() } else { stripped.into() }
}

/// *items* joined by ", " over as many lines as keep them under *width*.
pub fn wrapped_items(items: &[String], indent: &str, width: usize) -> Vec<String> {
    let mut lines = Vec::new();
    let mut line = String::new();
    let indent_len = indent.chars().count();
    for item in items {
        let candidate = if line.is_empty() { item.clone() } else { format!("{line}, {item}") };
        if !line.is_empty() && indent_len + candidate.chars().count() + 1 > width {
            lines.push(format!("{indent}{line},"));
            line = item.clone();
        } else {
            line = candidate;
        }
    }
    if !line.is_empty() {
        lines.push(format!("{indent}{line}"));
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn floats_print_like_python() {
        let cases = [
            (1.0, "1.0"),
            (-0.0, "-0.0"),
            (0.1, "0.1"),
            (1e-4, "0.0001"),
            (1e-5, "1e-05"),
            (1.5e-7, "1.5e-07"),
            (1e15, "1000000000000000.0"),
            (1e16, "1e+16"),
            (1.2345e20, "1.2345e+20"),
            (-68.434871, "-68.434871"),
            (17005833.330525, "17005833.330525"),
            (123456789.0, "123456789.0"),
        ];
        for (x, want) in cases {
            assert_eq!(float_repr(x), want, "{x}");
        }
    }

    #[test]
    fn round_is_python_round() {
        assert_eq!(round_to(0.0078125, 6), 0.007812);
        assert_eq!(round_to(2.675, 2), 2.67);
        assert_eq!(round_to(-0.0000004, 6).to_string(), "-0");
    }

    #[test]
    fn strings_repr_like_python() {
        assert_eq!(str_repr("a'b"), "\"a'b\"");
        assert_eq!(str_repr("a'b\"c"), "'a\\'b\"c'");
        assert_eq!(str_repr("tab\there\nnew\\"), "'tab\\there\\nnew\\\\'");
        assert_eq!(str_repr("caf\u{e9}\u{a0}\u{7}\u{2028}\u{1F600}"), "'caf\u{e9}\\xa0\\x07\\u2028\u{1F600}'");
    }

    #[test]
    fn literals() {
        assert_eq!(py(&Lit::Tuple(vec![Lit::Int(1)])), "(1,)");
        assert_eq!(py(&Lit::Float(f64::NAN)), "float(\"nan\")");
        assert_eq!(py(&Lit::Float(f64::NEG_INFINITY)), "-float(\"inf\")");
        assert_eq!(r(&Lit::Float(f64::NAN)), "NA_real_");
        assert_eq!(r(&Lit::str("a\"b\\c\r\n\t\0")), "\"a\\\"b\\\\c\\n\\t\"");
        assert_eq!(py(&Lit::str("nul\0x")), "'nulx'");
        assert_eq!(comment_text("a\r\nb\n\nc \0"), "a b c");
        assert_eq!(safe_name(" x\"y\n\tz "), "x'y z");
        assert_eq!(safe_name("\n"), "map");
        assert_eq!(size_mm(30.0), 1.93);
        assert_eq!(linewidth_mm(0.5), 0.23);
    }

    #[test]
    fn linetypes() {
        let dash = |a, b| Lit::Tuple(vec![Lit::Int(0), Lit::Tuple(vec![Lit::Int(a), Lit::Int(b)])]);
        assert_eq!(r_linetype(&dash(1, 2)), "dotted");
        assert_eq!(r_linetype(&dash(6, 3)), "longdash");
        assert_eq!(r_linetype(&dash(9, 9)), "dashed");
        assert_eq!(r_linetype(&Lit::str("solid")), "solid");
    }
}
