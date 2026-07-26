const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const svgNS = "http://www.w3.org/2000/svg";

/* ---------------- embedded data ---------------- */
const LAND_TOPO = JSON.parse(document.getElementById("land-topo").textContent);
const CTRY_TOPO = JSON.parse(document.getElementById("countries-topo").textContent);
const LAND = topojson.feature(LAND_TOPO, LAND_TOPO.objects.land);
const LAND_MESH = topojson.mesh(LAND_TOPO, LAND_TOPO.objects.land);
const BORDERS = topojson.mesh(CTRY_TOPO, CTRY_TOPO.objects.countries, (a,b)=>a!==b);

const SAMPLES = JSON.parse(document.getElementById("samples").textContent);

