//! RustyMappr's core: everything that is not UI.

pub mod basemap;
pub mod catalog;
pub mod coords;
pub mod districts;
pub mod export;
pub mod geom;
pub mod graticule;
pub mod inset;
pub mod labels;
pub mod overlays;
pub mod projection;
#[cfg(test)]
mod pymappr_reference;
pub mod raster;
pub mod regions;
pub mod render;
pub mod table;
pub mod view;

/// PyMappr's checkout, for tests that use its sample data and map data:
/// `PYMAPPR_DIR`, else `C:\PyCharm\PyMappr`. Tests skip themselves when the
/// folder they need is missing.
#[cfg(test)]
pub(crate) fn pymappr_dir() -> std::path::PathBuf {
    std::env::var_os("PYMAPPR_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| std::path::PathBuf::from(r"C:\PyCharm\PyMappr"))
}
