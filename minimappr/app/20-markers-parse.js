/* ---------------- palette / markers (ported from styles.py) ---------------- */
const DEFAULT_PALETTE = ["#d62728","#1f77b4","#2ca02c","#ff7f0e","#9467bd",
  "#8c564b","#e377c2","#17becf","#bcbd22","#7f7f7f"];
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

/* ---------------- coordinate parsing (ported from coords.py) ---------------- */
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

/* ---------------- delimited-text parsing ---------------- */
function detectDelim(text){
  const line = text.split(/\r?\n/,1)[0] || "";
  const counts = {",":0,"\t":0,";":0};
  let q=false;
  for(const ch of line){ if(ch==='"') q=!q; else if(!q && ch in counts) counts[ch]++; }
  let best=",", n=-1; for(const d in counts){ if(counts[d]>n){n=counts[d];best=d;} }
  return best;
}
function parseDelimited(text){
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
  if(!clean.length) return {columns:[],rows:[]};
  const header = clean[0].map((h,i)=>h.trim()||("Column "+(i+1)));
  const data = clean.slice(1).map(r=>{ const o={}; header.forEach((h,i)=>o[h]=(r[i]??"").trim()); return o; });
  return {columns:header, rows:data};
}

