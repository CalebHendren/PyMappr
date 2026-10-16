//! What the map can draw, as PyMappr defines it: the Natural Earth layers
//! and the files behind them (`pymappr/geo/layers.py`), the layers derived
//! from them, and the draw order, marker and label tables
//! (`pymappr/renderer/tables.py`). Colours stay in the frontend.

use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Geometry {
    Polygon,
    Line,
    Point,
}

/// Zoom thresholds for the three Natural Earth scales: 110m while zoomed
/// out, 50m for continent-level views, 10m from country level in.
pub const Z50: f64 = 1.0;
pub const Z10: f64 = 3.5;

#[derive(Debug)]
pub struct LayerSpec {
    pub key: &'static str,
    /// Directory of the default scale (what labels are anchored on).
    pub directory: &'static str,
    pub geometry: Geometry,
    /// Most labels drawn at once; 0 = never labelled.
    pub label_cap: usize,
    /// Member name in a directory holding several shapefiles.
    pub shapefile: Option<&'static str>,
    /// (min zoom, directory), ascending; empty for a single scale.
    pub resolutions: &'static [(f64, &'static str)],
    pub label_column: &'static str,
}

impl LayerSpec {
    /// The directory for a zoom level (PyMappr's `directory_for_zoom`).
    pub fn directory_for_zoom(&self, zoom: Option<f64>) -> &'static str {
        let Some(zoom) = zoom else { return self.directory };
        if self.resolutions.is_empty() {
            return self.directory;
        }
        let mut chosen = self.resolutions[0].1;
        for &(min_zoom, dir) in self.resolutions {
            if zoom >= min_zoom {
                chosen = dir;
            }
        }
        chosen
    }

    /// Every directory the layer can be drawn from, coarsest first.
    pub fn directories(&self) -> Vec<&'static str> {
        if self.resolutions.is_empty() {
            vec![self.directory]
        } else {
            self.resolutions.iter().map(|r| r.1).collect()
        }
    }

    pub fn is_multi_resolution(&self) -> bool {
        !self.resolutions.is_empty()
    }
}

const fn spec(key: &'static str, directory: &'static str, geometry: Geometry, label_cap: usize) -> LayerSpec {
    LayerSpec { key, directory, geometry, label_cap, shapefile: None, resolutions: &[], label_column: "name" }
}

use Geometry::{Line, Point, Polygon};

pub const LAYER_SPECS: &[LayerSpec] = &[
    // political
    LayerSpec {
        resolutions: &[(0.0, "ne_110m_admin_0_countries"), (Z50, "ne_50m_admin_0_countries"), (Z10, "ne_10m_admin_0_countries")],
        ..spec("countries", "ne_50m_admin_0_countries", Polygon, 400)
    },
    spec("states", "ne_10m_admin_1_states_provinces", Polygon, 600),
    spec("counties", "ne_10m_admin_2_counties", Polygon, 1200),
    spec("sovereignty", "ne_50m_admin_0_sovereignty", Polygon, 0),
    spec("map_units", "ne_50m_admin_0_map_units", Polygon, 0),
    spec("subunits", "ne_50m_admin_0_map_subunits", Polygon, 0),
    spec("disputed", "ne_10m_admin_0_disputed_areas", Polygon, 80),
    spec("disputed_lines", "ne_10m_admin_0_boundary_lines_disputed_areas", Line, 0),
    spec("maritime_all", "ne_10m_admin_0_boundary_lines_maritime_indicator", Line, 0),
    LayerSpec { label_column: "time_zone", ..spec("timezones", "ne_10m_time_zones", Polygon, 60) },
    // cultural
    spec("cities", "ne_10m_populated_places_simple", Point, 250),
    spec("urban", "ne_10m_urban_areas", Polygon, 0),
    spec("airports", "ne_10m_airports", Point, 150),
    spec("ports", "ne_10m_ports", Point, 150),
    LayerSpec {
        shapefile: Some("ne_10m_parks_and_protected_lands_area"),
        ..spec("parks", "ne_10m_parks_and_protected_lands", Polygon, 60)
    },
    spec("roads", "ne_10m_roads", Line, 0),
    // water
    LayerSpec {
        resolutions: &[(0.0, "ne_110m_lakes"), (Z50, "ne_50m_lakes"), (Z10, "ne_10m_lakes")],
        ..spec("lakes", "ne_50m_lakes", Polygon, 60)
    },
    LayerSpec {
        resolutions: &[
            (0.0, "ne_110m_rivers_lake_centerlines"),
            (Z50, "ne_50m_rivers_lake_centerlines"),
            (Z10, "ne_10m_rivers_lake_centerlines"),
        ],
        ..spec("rivers", "ne_10m_rivers_lake_centerlines", Line, 60)
    },
    LayerSpec {
        resolutions: &[(0.0, "ne_110m_ocean"), (Z50, "ne_50m_ocean"), (Z10, "ne_10m_ocean")],
        ..spec("ocean", "ne_50m_ocean", Polygon, 0)
    },
    LayerSpec {
        resolutions: &[(0.0, "ne_110m_land"), (Z50, "ne_50m_land"), (Z10, "ne_10m_land")],
        ..spec("land", "ne_50m_land", Polygon, 0)
    },
    // physical
    spec("glaciers", "ne_10m_glaciated_areas", Polygon, 0),
    spec("ice_shelves", "ne_50m_antarctic_ice_shelves_polys", Polygon, 0),
    spec("reefs", "ne_10m_reefs", Line, 0),
    spec("playas", "ne_10m_playas", Polygon, 40),
    spec("regions", "ne_10m_geography_regions_polys", Polygon, 150),
    // biodiversity & ecoregions (optional, from external sources)
    spec("biodiversity", "biodiversity_hotspots", Polygon, 0),
    spec("ecoregions", "ecoregions_2017", Polygon, 0),
    spec("marine_ecoregions", "marine_ecoregions", Polygon, 0),
];

/// Layers fetched from outside Natural Earth; absent until downloaded.
pub const OPTIONAL_LAYERS: [&str; 3] = ["biodiversity", "ecoregions", "marine_ecoregions"];

pub fn layer_spec(key: &str) -> Option<&'static LayerSpec> {
    LAYER_SPECS.iter().find(|s| s.key == key)
}

/// Derived layers: (key, source layer). Filters live in the basemap.
pub const DERIVED: &[(&str, &str)] = &[
    ("continents", "countries"),
    ("dependencies", "countries"),
    ("deserts", "regions"),
    ("wadis", "rivers"),
    ("capitals", "cities"),
    ("maritime", "maritime_all"),
    ("eez", "maritime_all"),
];

pub fn derived_source(key: &str) -> Option<&'static str> {
    DERIVED.iter().find(|d| d.0 == key).map(|d| d.1)
}

/// The maritime boundary class split off as the EEZ layer.
pub const MARITIME_200NM: &str = "Marine Indicator 200 mi nl";

/// Depth steps of the `ne_10m_bathymetry_all` archive, shallow to deep.
pub const BATHYMETRY_STEPS: [(&str, u32); 12] = [
    ("L", 0),
    ("K", 200),
    ("J", 1000),
    ("I", 2000),
    ("H", 3000),
    ("G", 4000),
    ("F", 5000),
    ("E", 6000),
    ("D", 7000),
    ("C", 8000),
    ("B", 9000),
    ("A", 10000),
];

/// Curated view extents: (lon_min, lon_max, lat_min, lat_max).
pub const CONTINENT_EXTENTS: &[(&str, [f64; 4])] = &[
    ("World", [-180.0, 180.0, -90.0, 90.0]),
    ("Africa", [-20.0, 55.0, -38.0, 40.0]),
    ("Antarctica", [-180.0, 180.0, -90.0, -60.0]),
    ("Asia", [25.0, 180.0, -12.0, 78.0]),
    ("Europe", [-25.0, 45.0, 34.0, 72.0]),
    ("North America", [-170.0, -50.0, 5.0, 84.0]),
    ("Oceania", [105.0, 180.0, -50.0, 10.0]),
    ("South America", [-85.0, -33.0, -58.0, 14.0]),
];

pub fn continent_extent(name: &str) -> Option<[f64; 4]> {
    CONTINENT_EXTENTS.iter().find(|c| c.0 == name).map(|c| c.1)
}

// ---- draw order (matplotlib z-orders from renderer/tables.py) -------------

pub const Z_SATELLITE: f64 = 0.1;
pub const Z_OCEAN: f64 = 0.3;
pub const Z_BATHYMETRY: f64 = 0.32;
pub const Z_LAKE_FILL: f64 = 0.5;
pub const Z_GRID: f64 = 1.8;
/// Not in PyMappr: districts sit with the counties they stand in for.
pub const Z_DISTRICTS: f64 = 1.41;

/// Line layers: (key, source layer, z-order).
pub const LINE_LAYERS: &[(&str, &str, f64)] = &[
    ("countries", "countries", 1.6),
    ("continents", "continents", 1.55),
    ("sovereignty", "sovereignty", 1.58),
    ("map_units", "map_units", 1.57),
    ("subunits", "subunits", 1.56),
    ("dependencies", "dependencies", 1.62),
    ("disputed_lines", "disputed_lines", 1.65),
    ("maritime", "maritime", 1.3),
    ("eez", "eez", 1.31),
    ("timezones", "timezones", 1.35),
    ("states", "states", 1.5),
    ("counties", "counties", 1.4),
    ("lakes_outline", "lakes", 1.2),
    ("rivers", "rivers", 1.0),
    ("wadis", "wadis", 1.0),
    ("reefs", "reefs", 1.15),
    ("regions", "regions", 1.12),
    ("roads", "roads", 1.1),
];

/// On/off fill layers: (key, source layer, z-order).
pub const FILL_LAYERS: &[(&str, &str, f64)] = &[
    ("land", "land", 0.35),
    ("deserts", "deserts", 0.52),
    ("playas", "playas", 0.55),
    ("urban", "urban", 0.58),
    ("parks", "parks", 0.6),
    ("ice_shelves", "ice_shelves", 0.61),
    ("glaciers", "glaciers", 0.62),
    ("disputed", "disputed", 0.66),
    ("ecoregions", "ecoregions", 0.44),
    ("marine_ecoregions", "marine_ecoregions", 0.43),
    ("biodiversity", "biodiversity", 0.53),
];

/// Point-marker layers: (key, source layer, zoom bias). A feature shows
/// once `min_zoom <= zoom + bias`.
pub const POINT_LAYERS: &[(&str, &str, f64)] =
    &[("cities", "cities", 2.0), ("capitals", "capitals", 99.0), ("airports", "airports", 4.0), ("ports", "ports", 3.5)];

pub fn point_layer(key: &str) -> Option<(&'static str, &'static str, f64)> {
    POINT_LAYERS.iter().copied().find(|p| p.0 == key)
}

/// A label layer: font size in points, the zoom it starts at, and the
/// per-feature bias (a feature is labelled once `min_label <= zoom + bias`).
#[derive(Debug, Clone, Copy)]
pub struct LabelStyle {
    pub key: &'static str,
    pub source: &'static str,
    pub fontsize: f64,
    pub min_zoom: f64,
    pub feature_bias: Option<f64>,
}

const fn label(key: &'static str, fontsize: f64, min_zoom: f64, feature_bias: Option<f64>) -> LabelStyle {
    LabelStyle { key, source: key, fontsize, min_zoom, feature_bias }
}

/// In PyMappr's order, which is the order labels claim room in. Districts
/// (not in PyMappr) follow the counties, in the counties' style.
pub const LABEL_STYLES: &[LabelStyle] = &[
    label("countries", 9.0, 0.0, None),
    label("states", 8.0, 1.2, None),
    label("counties", 6.5, 3.6, None),
    label("districts", 6.5, 3.6, None),
    label("cities", 7.5, 0.0, Some(2.0)),
    label("airports", 6.5, 2.0, Some(3.0)),
    label("ports", 6.5, 2.0, Some(3.0)),
    label("lakes", 7.5, 1.5, None),
    label("rivers", 7.0, 1.5, None),
    label("regions", 8.0, 0.5, Some(3.0)),
    label("timezones", 8.0, 0.0, None),
];

/// Districts are labelled at most this many at once, as counties are.
pub const DISTRICT_LABEL_CAP: usize = 1200;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolution_switching_picks_finer_data_when_zoomed() {
        let countries = layer_spec("countries").unwrap();
        assert_eq!(countries.directory_for_zoom(Some(0.0)), "ne_110m_admin_0_countries");
        assert_eq!(countries.directory_for_zoom(Some(2.0)), "ne_50m_admin_0_countries");
        assert_eq!(countries.directory_for_zoom(Some(6.0)), "ne_10m_admin_0_countries");
        assert_eq!(countries.directory_for_zoom(None), countries.directory);
        assert_eq!(countries.directory_for_zoom(Some(-3.0)), "ne_110m_admin_0_countries");
    }

    #[test]
    fn single_resolution_layers_ignore_zoom() {
        let states = layer_spec("states").unwrap();
        for zoom in [None, Some(0.0), Some(5.0)] {
            assert_eq!(states.directory_for_zoom(zoom), states.directory);
        }
    }

    #[test]
    fn derived_layers_reference_real_sources() {
        for (key, source) in DERIVED {
            assert!(layer_spec(source).is_some(), "{key} derives from unknown {source}");
        }
        for (key, source, _) in LINE_LAYERS.iter().chain(FILL_LAYERS) {
            assert!(layer_spec(source).is_some() || derived_source(source).is_some(), "{key}");
        }
    }

    #[test]
    fn optional_layers_have_specs() {
        for key in OPTIONAL_LAYERS {
            assert!(layer_spec(key).is_some());
        }
    }

    #[test]
    fn bathymetry_steps_are_sorted_shallow_to_deep() {
        let depths: Vec<u32> = BATHYMETRY_STEPS.iter().map(|s| s.1).collect();
        let mut sorted = depths.clone();
        sorted.sort();
        assert_eq!(depths, sorted);
        assert_eq!((depths[0], depths[11]), (0, 10000));
    }

    #[test]
    fn label_layers_have_caps() {
        for style in LABEL_STYLES {
            let cap = if style.key == "districts" { DISTRICT_LABEL_CAP } else { layer_spec(style.source).unwrap().label_cap };
            assert!(cap > 0, "{}", style.key);
        }
    }
}
