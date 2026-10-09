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
// The outline filled markers get by default, and the one the publication
// style sets. Match POINT_EDGE_COLOR / POINT_EDGE_WIDTH and
// PUBLICATION_POINT_EDGE in styles.py.
const POINT_EDGE_COLOR="#ffffff", POINT_EDGE_WIDTH=0.5;
const PUBLICATION_POINT_EDGE=["#000000", 0.6];
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

// Shapes follow matplotlib's marker paths, which PyMappr draws with: each is
// drawn for a marker `m` pixels across (matplotlib's markersize), centred on
// the point, with y down as SVG has it.
function regPoly(n,r,rot){ const p=[]; for(let i=0;i<n;i++){const a=rot+i*2*Math.PI/n;
  p.push([r*Math.cos(a), r*Math.sin(a)]);} return p; }
function poly(pts){ return "M"+pts.map(p=>p[0].toFixed(2)+","+p[1].toFixed(2)).join("L")+"Z"; }
function circlePath(r){ return `M${(-r).toFixed(2)},0 a${r},${r} 0 1,0 ${(2*r).toFixed(2)},0 a${r},${r} 0 1,0 ${(-2*r).toFixed(2)},0 Z`; }
// A five-point star, inner radius as matplotlib's unit_regular_star.
function starPts(r){ const p=[]; for(let i=0;i<10;i++){const rr=(i%2)?r*0.381966:r;
  const a=-Math.PI/2+i*Math.PI/5; p.push([rr*Math.cos(a), rr*Math.sin(a)]);} return p; }
const turn=(pts,deg)=>{ const a=deg*Math.PI/180, c=Math.cos(a), s=Math.sin(a);
  return pts.map(([x,y])=>[x*c-y*s, x*s+y*c]); };
// matplotlib's filled plus ("P") and filled X ("X"), in sixths and quarters.
const PLUS_FILLED=[[-1,-3],[1,-3],[1,-1],[3,-1],[3,1],[1,1],[1,3],[-1,3],[-1,1],[-3,1],[-3,-1],[-1,-1]]
  .map(([x,y])=>[x/6,y/6]);
const X_FILLED=[[-1,-2],[0,-1],[1,-2],[2,-1],[1,0],[2,1],[1,2],[0,1],[-1,2],[-2,1],[-1,0],[-2,-1]]
  .map(([x,y])=>[x/4,y/4]);

function markerPath(marker,m){
  const b = baseMarker(marker), h=m/2, U=-Math.PI/2;
  // matplotlib's triangle: apex at the top, base as wide as the marker.
  const tri=deg=>poly(turn([[0,-h],[-h,h],[h,h]], deg));
  switch(b){
    case "Circle": return circlePath(h);
    case "Dot": return circlePath(h*0.5);
    case "Square": return poly([[-h,-h],[h,-h],[h,h],[-h,h]]);
    case "Triangle": return tri(0);
    case "Triangle down": return tri(180);
    case "Triangle left": return tri(-90);
    case "Triangle right": return tri(90);
    case "Diamond": { const d=h*Math.SQRT2; return poly([[0,-d],[d,0],[0,d],[-d,0]]); }
    case "Thin diamond": { const d=h*Math.SQRT2; return poly([[0,-d],[d*0.6,0],[0,d],[-d*0.6,0]]); }
    case "Star": return poly(starPts(h));
    case "Plus": return poly(PLUS_FILLED.map(([x,y])=>[x*m,y*m]));
    case "X": return poly(X_FILLED.map(([x,y])=>[x*m,y*m]));
    case "Pentagon": return poly(regPoly(5,h,U));
    case "Hexagon": return poly(regPoly(6,h,U));
    case "Octagon": return poly(regPoly(8,h,U+Math.PI/8));
    default: return circlePath(h);
  }
}

/* coordinate parsing (ported from coords.py) */
const HEMI = {N:1,S:-1,E:1,W:-1};
const DMS_RE = /^(\d+(?:[.,]\d+)?(?![\d.,]))\s*(?:[°ºd]|deg(?:rees)?)?(?:[\s:]*(\d+(?:[.,]\d+)?(?![\d.,]))\s*([′ʹ']|m(?:in(?:utes)?)?)?)?(?:[\s:]*(\d+(?:[.,]\d+)?(?![\d.,]))\s*(?:[″ʺ"]|''|s(?:ec(?:onds)?)?)?)?\s*$/i;
function toFloat(t){ return parseFloat(String(t).replace(",",".")); }
// A trailing "s" closes a DMS value rather than meaning South when it sits
// right against the seconds digits and the text reads as D M S, and either
// the minutes carry an explicit marker or the value is a longitude. A leading
// sign ("-122d30m15s") is not part of the DMS text.
function isSecondsMarker(text, m, kind){
  if(m[2].toLowerCase()!=="s" || !/\d/.test(text.charAt(text.length-2))) return false;
  const dms = text.replace(/^[+-]\s*/,"").match(DMS_RE);
  if(!dms || !dms[2] || !dms[4]) return false;
  return kind==="longitude" || !!dms[3];
}
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
  else if((m = text.match(/^(.*?)\s*([NSEW])$/i)) && !isSecondsMarker(text, m, kind)){ hemi=m[2].toUpperCase(); sign=HEMI[hemi]; text=m[1]; }
  if(hemi && hemis.indexOf(hemi)<0) throw new Error("hemisphere "+hemi+" invalid for "+kind);
  text = text.trim();
  let neg=false;
  if(text[0]==="+"||text[0]==="-"){
    if(sign!==null) throw new Error("cannot combine sign and hemisphere");
    neg = text[0]==="-"; text=text.slice(1).trim();
  }
  // Plain decimal degrees: one number with at most one decimal mark, as
  // Python's float() accepts. "45.30.15" and "45,30,15" are not numbers.
  let deg;
  if(/^(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:e[+-]?\d+)?$/i.test(text)){
    deg = toFloat(text);
  } else {
    const dm = text.match(DMS_RE);
    if(!dm) throw new Error("cannot parse "+kind+" "+value);
    const d=toFloat(dm[1]), mi=dm[2]?toFloat(dm[2]):0, se=dm[4]?toFloat(dm[4]):0;
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

