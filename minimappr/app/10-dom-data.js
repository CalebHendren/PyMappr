const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const svgNS = "http://www.w3.org/2000/svg";

/* embedded data */
// One topology for everything: its merged land object is the fill, and the
// country arcs split into coastline (used once) and borders (shared), so the
// borders meet the coast exactly.
const CTRY_TOPO = JSON.parse(document.getElementById("countries-topo").textContent);
const LAND = topojson.feature(CTRY_TOPO, CTRY_TOPO.objects.land);
const LAND_MESH = topojson.mesh(CTRY_TOPO, CTRY_TOPO.objects.countries, (a,b)=>a===b);
const BORDERS = topojson.mesh(CTRY_TOPO, CTRY_TOPO.objects.countries, (a,b)=>a!==b);

const SAMPLES = JSON.parse(document.getElementById("samples").textContent);

