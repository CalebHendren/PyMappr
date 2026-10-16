//! Plane geometry on longitude/latitude features: the continent dissolve,
//! label anchors as shapely computes them (GEOS's interior point and line
//! interpolation), point-in-polygon and distances.

use std::collections::BTreeMap;

use geo::orient::{Direction, Orient};
use geo::{BooleanOps, Distance, Euclidean, LineString, MultiPolygon, Polygon, unary_union};

use crate::basemap::{Attrs, Feature, Part};

type Pt = [f64; 2];

/// A polygon as rings: the shell first, then its holes.
pub fn to_geo_polygon(rings: &[&[Pt]]) -> Polygon {
    let ring = |r: &[Pt]| LineString::from(r.iter().map(|p| (p[0], p[1])).collect::<Vec<_>>());
    Polygon::new(ring(rings[0]), rings[1..].iter().map(|r| ring(r)).collect())
}

/// A polygon feature as a geo `MultiPolygon`.
pub fn feature_to_geo(feature: &Feature) -> MultiPolygon {
    MultiPolygon::new(
        feature
            .polygons()
            .iter()
            .map(|poly| to_geo_polygon(&poly.iter().map(|p| p.points.as_slice()).collect::<Vec<_>>()))
            .collect(),
    )
}

/// A geo `MultiPolygon` back as feature parts.
pub fn geo_to_parts(mp: &MultiPolygon) -> Vec<Part> {
    let pts = |ls: &LineString| ls.0.iter().map(|c| [c.x, c.y]).collect::<Vec<_>>();
    let mut parts = Vec::new();
    for poly in mp {
        if poly.exterior().0.len() < 4 {
            continue;
        }
        parts.push(Part::new(pts(poly.exterior()), false));
        parts.extend(poly.interiors().iter().filter(|r| r.0.len() >= 4).map(|r| Part::new(pts(r), true)));
    }
    parts
}

/// Country polygons dissolved by their `continent` column: outlines
/// without borders (PyMappr's `dissolve(by="continent")`).
pub fn dissolve_by_continent(countries: &[Feature]) -> Vec<Feature> {
    let mut groups: BTreeMap<String, Vec<Polygon>> = BTreeMap::new();
    for f in countries {
        let Some(continent) = f.attrs.continent.clone() else { continue };
        let mp = feature_to_geo(f).orient(Direction::Default);
        groups.entry(continent).or_default().extend(mp.0);
    }
    let groups: Vec<(String, Vec<Polygon>)> = groups.into_iter().collect();
    use rayon::prelude::*;
    groups
        .into_par_iter()
        .map(|(continent, polys)| {
            let merged = unary_union(&polys);
            Feature::new(
                geo_to_parts(&merged),
                Attrs { name: Some(continent.clone()), continent: Some(continent), ..Default::default() },
            )
        })
        .collect()
}

/// A polygon cut to the parts inside `clip` (geo's intersection).
pub fn intersect(subject: &MultiPolygon, clip: &MultiPolygon) -> MultiPolygon {
    subject.intersection(clip)
}

/// shapely's `representative_point` of one polygon (GEOS's
/// `InteriorPointArea`): the middle of the widest stretch of a horizontal
/// scan line placed between vertices near the polygon's vertical middle.
/// Returns the point and that stretch's width.
fn interior_point_polygon(rings: &[&[Pt]]) -> Option<(Pt, f64)> {
    let shell = *rings.first()?;
    let first = *shell.first()?;
    // ScanLineYOrdinateFinder
    let (mut lo, mut hi) = (f64::MAX, f64::MIN);
    for p in shell {
        lo = lo.min(p[1]);
        hi = hi.max(p[1]);
    }
    let centre = (lo + hi) / 2.0;
    for ring in rings {
        for p in ring.iter() {
            let y = p[1];
            if y <= centre {
                if y > lo {
                    lo = y;
                }
            } else if y < hi {
                hi = y;
            }
        }
    }
    let scan_y = (hi + lo) / 2.0;
    let mut crossings = Vec::new();
    for ring in rings {
        let (mut rlo, mut rhi) = (f64::MAX, f64::MIN);
        for p in ring.iter() {
            rlo = rlo.min(p[1]);
            rhi = rhi.max(p[1]);
        }
        if scan_y < rlo || scan_y > rhi {
            continue;
        }
        for w in ring.windows(2) {
            let (p0, p1) = (w[0], w[1]);
            if (p0[1] > scan_y && p1[1] > scan_y) || (p0[1] < scan_y && p1[1] < scan_y) {
                continue;
            }
            if p0[1] == p1[1] {
                continue;
            }
            if p0[1] == scan_y && p1[1] < scan_y {
                continue;
            }
            if p1[1] == scan_y && p0[1] < scan_y {
                continue;
            }
            let x = if p0[0] == p1[0] {
                p0[0]
            } else {
                let m = (p1[1] - p0[1]) / (p1[0] - p0[0]);
                p0[0] + (scan_y - p0[1]) / m
            };
            crossings.push(x);
        }
    }
    crossings.sort_by(f64::total_cmp);
    let mut best = (first, 0.0);
    for pair in crossings.chunks_exact(2) {
        let width = pair[1] - pair[0];
        if width > best.1 {
            best = ([(pair[0] + pair[1]) / 2.0, scan_y], width);
        }
    }
    Some(best)
}

/// shapely's `representative_point` of a (multi)polygon given as polygons
/// of rings: the widest of each polygon's interior points.
pub fn representative_point(polygons: &[Vec<&[Pt]>]) -> Option<Pt> {
    let mut best: Option<(Pt, f64)> = None;
    for rings in polygons {
        if let Some((p, w)) = interior_point_polygon(rings)
            && best.is_none_or(|b| w > b.1)
        {
            best = Some((p, w));
        }
    }
    best.map(|b| b.0)
}

fn line_length(line: &[Pt]) -> f64 {
    line.windows(2).map(|w| (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1])).sum()
}

/// Total length of a (multi)line, in degrees, as shapely measures it.
pub fn length(lines: &[&[Pt]]) -> f64 {
    lines.iter().map(|l| line_length(l)).sum()
}

/// shapely's `interpolate(0.5, normalized=True)`: the point half way along
/// the parts taken end to end.
pub fn midpoint_along(lines: &[&[Pt]]) -> Option<Pt> {
    let total = length(lines);
    let first = *lines.iter().find(|l| !l.is_empty())?.first()?;
    if total <= 0.0 {
        return Some(first);
    }
    let mut left = total * 0.5;
    let mut last = first;
    for line in lines {
        for w in line.windows(2) {
            let seg = (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1]);
            if seg > 0.0 && left <= seg {
                let t = left / seg;
                return Some([w[0][0] + t * (w[1][0] - w[0][0]), w[0][1] + t * (w[1][1] - w[0][1])]);
            }
            left -= seg;
            last = w[1];
        }
    }
    Some(last)
}

/// Even-odd point-in-polygon over all rings.
pub fn contains(rings: &[&[Pt]], p: Pt) -> bool {
    let mut inside = false;
    for ring in rings {
        let n = ring.len();
        if n < 3 {
            continue;
        }
        let mut j = n - 1;
        for i in 0..n {
            let (a, b) = (ring[i], ring[j]);
            if (a[1] > p[1]) != (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0] {
                inside = !inside;
            }
            j = i;
        }
    }
    inside
}

/// Distance between two polygons (0 when they touch or overlap), as
/// shapely's `distance`.
pub fn polygon_distance(a: &[&[Pt]], b: &[&[Pt]]) -> f64 {
    Euclidean.distance(&to_geo_polygon(a), &to_geo_polygon(b))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interior_point_of_a_square_is_its_centre() {
        let sq: Vec<Pt> = vec![[0.0, 0.0], [0.0, 2.0], [4.0, 2.0], [4.0, 0.0], [0.0, 0.0]];
        let p = representative_point(&[vec![sq.as_slice()]]).unwrap();
        assert_eq!(p, [2.0, 1.0]);
    }

    #[test]
    fn interior_point_avoids_a_hole_and_matches_shapely() {
        // shapely: Polygon([(0,0),(10,0),(10,10),(0,10)], [[(2,2),(8,2),(8,8),(2,8)]]).representative_point()
        // is POINT (1 5).
        let shell: Vec<Pt> = vec![[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]];
        let hole: Vec<Pt> = vec![[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [2.0, 8.0], [2.0, 2.0]];
        let p = representative_point(&[vec![shell.as_slice(), hole.as_slice()]]).unwrap();
        assert_eq!(p, [1.0, 5.0]);
    }

    #[test]
    fn widest_polygon_wins() {
        let small: Vec<Pt> = vec![[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]];
        let big: Vec<Pt> = vec![[10.0, 0.0], [10.0, 1.0], [15.0, 1.0], [15.0, 0.0], [10.0, 0.0]];
        let p = representative_point(&[vec![small.as_slice()], vec![big.as_slice()]]).unwrap();
        assert_eq!(p, [12.5, 0.5]);
    }

    #[test]
    fn midpoint_runs_along_the_parts() {
        let a: Vec<Pt> = vec![[0.0, 0.0], [2.0, 0.0]];
        let b: Vec<Pt> = vec![[10.0, 0.0], [10.0, 6.0]];
        assert_eq!(midpoint_along(&[&a, &b]).unwrap(), [10.0, 2.0]);
    }

    #[test]
    fn point_in_polygon_respects_holes() {
        let shell: Vec<Pt> = vec![[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]];
        let hole: Vec<Pt> = vec![[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [2.0, 8.0]];
        assert!(contains(&[&shell, &hole], [1.0, 1.0]));
        assert!(!contains(&[&shell, &hole], [5.0, 5.0]));
        assert!(!contains(&[&shell, &hole], [11.0, 5.0]));
    }

    #[test]
    fn distance_between_polygons() {
        let a: Vec<Pt> = vec![[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]];
        let b: Vec<Pt> = vec![[4.0, 0.0], [5.0, 0.0], [5.0, 1.0], [4.0, 1.0], [4.0, 0.0]];
        assert!((polygon_distance(&[&a], &[&b]) - 3.0).abs() < 1e-12);
    }
}
