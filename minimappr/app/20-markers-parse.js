/* palette / markers (ported from styles.py) */
const DEFAULT_PALETTE = ["#d62728","#1f77b4","#2ca02c","#ff7f0e","#9467bd",
  "#8c564b","#e377c2","#17becf","#bcbd22","#7f7f7f"];
// Okabe-Ito: eight hues that stay distinguishable under the common forms of
// colour-vision deficiency, which the default palette's adjacent red and
// green do not. Matches OKABE_ITO in styles.py.
const OKABE_ITO = ["#0072b2","#d55e00","#009e73","#cc79a7","#e69f00",
  "#56b4e9","#f0e442","#000000"];
// Black, white and grey, the look of a printed journal figure. White points
// only show with a dark point outline. Matches BLACK_AND_WHITE in styles.py.
const BLACK_AND_WHITE = ["#000000","#ffffff","#808080"];
const PALETTES = {"Default": DEFAULT_PALETTE,
  "Colourblind safe (Okabe-Ito)": OKABE_ITO,
  "Black & white": BLACK_AND_WHITE};
// The palette in use is a map-wide setting (opts.palette), not a per-dataset one.
function palette(){ return PALETTES[opts.palette] || DEFAULT_PALETTE; }
const BASE_MARKERS = ["Circle","Square","Triangle","Triangle down","Triangle left",
  "Triangle right","Diamond","Thin diamond","Star","Plus","X","Pentagon","Hexagon","Octagon","Dot"];
const OPEN_SUFFIX = " (open)";
const MARKERS = BASE_MARKERS.concat(BASE_MARKERS.map(m=>m+OPEN_SUFFIX));
const MARKER_CYCLE = ["Circle","Square","Triangle","Diamond","Star","Plus","X","Pentagon",
  "Triangle down","Hexagon","Thin diamond","Triangle left","Octagon","Triangle right"];

function isOpen(marker){ return marker.endsWith(OPEN_SUFFIX); }
function baseMarker(marker){ return isOpen(marker) ? marker.slice(0,-OPEN_SUFFIX.length) : marker; }

function regPoly(n,r,rot){ const p=[]; for(let i=0;i<n;i++){const a=rot+i*2*Math.PI/n;
  p.push([r*Math.cos(a), r*Math.sin(a)]);} return p; }
function poly(pts){ return "M"+pts.map(p=>p[0].toFixed(2)+","+p[1].toFixed(2)).join("L")+"Z"; }
function circlePath(r){ return `M${(-r).toFixed(2)},0 a${r},${r} 0 1,0 ${(2*r).toFixed(2)},0 a${r},${r} 0 1,0 ${(-2*r).toFixed(2)},0 Z`; }
function starPts(r,ri){ const p=[]; for(let i=0;i<10;i++){const rr=(i%2)?ri:r;
  const a=-Math.PI/2+i*Math.PI/5; p.push([rr*Math.cos(a), rr*Math.sin(a)]);} return p; }
function plusPts(r,w){ return [[-w,-r],[w,-r],[w,-w],[r,-w],[r,w],[w,w],[w,r],[-w,r],[-w,w],[-r,w],[-r,-w],[-w,-w]]; }
function rot45(pts){ const c=Math.SQRT1_2; return pts.map(([x,y])=>[(x-y)*c,(x+y)*c]); }

function markerPath(marker,r){
  const b = baseMarker(marker);
  const U=-Math.PI/2;
  switch(b){
    case "Circle": return circlePath(r);
    case "Dot": return circlePath(r*0.5);
    case "Square": { const s=r*0.86; return poly([[-s,-s],[s,-s],[s,s],[-s,s]]); }
    case "Triangle": return poly(regPoly(3,r*1.1,U));
    case "Triangle down": return poly(regPoly(3,r*1.1,Math.PI/2));
    case "Triangle left": return poly(regPoly(3,r*1.1,Math.PI));
    case "Triangle right": return poly(regPoly(3,r*1.1,0));
    case "Diamond": return poly([[0,-r*1.1],[r*0.82,0],[0,r*1.1],[-r*0.82,0]]);
    case "Thin diamond": return poly([[0,-r*1.2],[r*0.5,0],[0,r*1.2],[-r*0.5,0]]);
    case "Star": return poly(starPts(r*1.15,r*0.5));
    case "Plus": return poly(plusPts(r,r*0.36));
    case "X": return poly(rot45(plusPts(r,r*0.36)));
    case "Pentagon": return poly(regPoly(5,r*1.05,U));
    case "Hexagon": return poly(regPoly(6,r,U));
    case "Octagon": return poly(regPoly(8,r,Math.PI/8));
    default: return circlePath(r);
  }
}

/* coordinate parsing (ported from coords.py) */
const HEMI = {N:1,S:-1,E:1,W:-1};
const DMS_RE = /^(\d+(?:[.,]\d+)?)\s*(?:[°ºd]|deg(?:rees)?)?(?:[\s:]*(\d+(?:[.,]\d+)?)\s*(?:[′ʹ']|m(?:in(?:utes)?)?)?)?(?:[\s:]*(\d+(?:[.,]\d+)?)\s*(?:[″ʺ"]|''|s(?:ec(?:onds)?)?)?)?\s*$/i;
function toFloat(t){ return parseFloat(String(t).replace(",",".")); }
function parseCoordinate(value, kind){
  const hemis = kind==="longitude" ? "EW" : "NS";
  const limit = kind==="longitude" ? 180 : 90;
  if(typeof value==="number"){
    if(Number.isNaN(value)) throw new Error("missing "+kind);
    if(value< -limit || value>limit) throw new Error(kind+" out of range");
    return value;
  }
  let text = String(value).trim();
  if(!text) throw new Error("missing "+kind);
  let sign=null, hemi=null, m;
  if((m = text.match(/^([NSEW])\s*(.*)$/i))){ hemi=m[1].toUpperCase(); sign=HEMI[hemi]; text=m[2]; }
  else if((m = text.match(/^(.*?)\s*([NSEW])$/i))){ hemi=m[2].toUpperCase(); sign=HEMI[hemi]; text=m[1]; }
  if(hemi && hemis.indexOf(hemi)<0) throw new Error("hemisphere "+hemi+" invalid for "+kind);
  text = text.trim();
  let neg=false;
  if(text[0]==="+"||text[0]==="-"){
    if(sign!==null) throw new Error("cannot combine sign and hemisphere");
    neg = text[0]==="-"; text=text.slice(1).trim();
  }
  let deg;
  const plain = toFloat(text);
  if(!Number.isNaN(plain) && /^[\d.,]+$/.test(text)){
    deg = plain;
  } else {
    const dm = text.match(DMS_RE);
    if(!dm) throw new Error("cannot parse "+kind+" "+value);
    const d=toFloat(dm[1]), mi=dm[2]?toFloat(dm[2]):0, se=dm[3]?toFloat(dm[3]):0;
    if(mi>=60 || se>=60) throw new Error("minutes/seconds must be < 60");
    deg = d + mi/60 + se/3600;
  }
  if(neg) deg=-deg;
  if(sign!==null) deg = Math.abs(deg)*sign;
  if(deg< -limit || deg>limit) throw new Error(kind+" out of range");
  return deg;
}

/* delimited-text parsing */
function detectDelim(text){
  const line = text.split(/\r?\n/,1)[0] || "";
  const counts = {",":0,"\t":0,";":0};
  let q=false;
  for(const ch of line){ if(ch==='"') q=!q; else if(!q && ch in counts) counts[ch]++; }
  let best=",", n=-1; for(const d in counts){ if(counts[d]>n){n=counts[d];best=d;} }
  return best;
}
// headers: whether the first row names the columns; undefined guesses it
// (headersLookLikeData). Without headers every row is data and the columns
// are "Column 1", "Column 2", ... Mirrors data_loader.read_table.
function parseDelimited(text, headers){
  text = text.replace(/^﻿/,"");
  const delim = detectDelim(text);
  const rows=[]; let field="", row=[], q=false;
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(q){
      if(c==='"'){ if(text[i+1]==='"'){field+='"';i++;} else q=false; }
      else field+=c;
    } else {
      if(c==='"') q=true;
      else if(c===delim){ row.push(field); field=""; }
      else if(c==="\n"){ row.push(field); rows.push(row); field=""; row=[]; }
      else if(c==="\r"){ /* skip */ }
      else field+=c;
    }
  }
  if(field.length||row.length){ row.push(field); rows.push(row); }
  const clean = rows.filter(r=>r.some(v=>v!==""));
  if(!clean.length) return {columns:[],rows:[],headers:headers!==false};
  if(headers===undefined) headers=!headersLookLikeData(clean[0]);
  const width=Math.max(...clean.map(r=>r.length));
  const header = headers
    ? uniqueNames(clean[0].map((h,i)=>h.trim()||("Column "+(i+1))))
    : Array.from({length:width},(_,i)=>"Column "+(i+1));
  const data = clean.slice(headers?1:0).map(r=>{ const o={}; header.forEach((h,i)=>o[h]=(r[i]??"").trim()); return o; });
  return {columns:header, rows:data, headers};
}
// Two headers that read the same would share one attribute key, and the
// second would silently overwrite the first; number the repeats instead.
function uniqueNames(names){
  const seen=new Set();
  return names.map(n=>{ let name=n, k=2; while(seen.has(name)) name=`${n} (${k++})`;
    seen.add(name); return name; });
}
// Whether the header row is really data: a file whose first row is
// coordinates ("38,-100") reads into numeric-looking column names, where
// real headers are words. Two or more numeric headers means data. Mirrors
// data_loader.headers_look_like_data.
function headersLookLikeData(cells){
  return cells.filter(c=>/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(String(c).trim())).length>=2;
}

// Which columns hold the coordinates, from the headers first and then by
// position: the last two columns are Longitude, Latitude unless the values
// say otherwise. Every other column becomes an attribute. Mirrors
// data_loader.guess_mapping.
const LON_HINTS=["lon","lng","long","longitude","x"];
const LAT_HINTS=["lat","latitude","y"];
// An exact hint ("lng"), then a header starting with one ("Long."), then one
// containing the whole word ("decimalLongitude"). Short hints never match
// inside other words: "x" and "y" sit in Taxon, Family and Locality.
function matchColumn(columns, hints){
  const lowered=new Map(columns.map(c=>[c.toLowerCase().trim(), c]));
  const rules=[(low,h)=>low===h, (low,h)=>h.length>1 && low.startsWith(h),
               (low,h)=>h.length>4 && low.includes(h)];
  for(const rule of rules)
    for(const hint of hints)
      for(const [low,original] of lowered)
        if(rule(low,hint)) return original;
  return null;
}
function beyondLatitude(rows, column){
  return rows.some(r=>{ const n=Number(String(r[column]??"").trim()); return Math.abs(n)>90; });
}
function guessMapping(parsed){
  const {columns, rows}=parsed;
  let lon=matchColumn(columns, LON_HINTS), lat=matchColumn(columns, LAT_HINTS);
  if(lon==null || lat==null || lon===lat){
    if(columns.length<2) return Object.fromEntries(columns.map(c=>[c,"attr"]));
    lon=columns[columns.length-2]; lat=columns[columns.length-1];
    // typed-in "lat, lon" files import the right way round this way
    if(beyondLatitude(rows, lat) && !beyondLatitude(rows, lon)) [lon,lat]=[lat,lon];
  }
  const map={};
  for(const c of columns) map[c] = c===lon ? "lon" : c===lat ? "lat" : "attr";
  return map;
}

