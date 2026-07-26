/* ---------------- styling logic (ported from styles.py) ---------------- */
function uniqueInOrder(arr){ const seen=new Set(), out=[]; for(const v of arr){ if(!seen.has(v)){seen.add(v);out.push(v);} } return out; }

function groupPoints(rows, groupBy){
  if(!rows.length) return [];
  if(!groupBy) return [["All points", rows]];
  const labels = uniqueInOrder(rows.map(r=>r._attr[groupBy]??""));
  return labels.map(lab=>[lab||"(blank)", rows.filter(r=>(r._attr[groupBy]??"")===lab)]);
}
function defaultStyles(labels, colorKeys, varySymbols, base){
  const styles={};
  if(!colorKeys){
    labels.forEach((lab,i)=>{
      styles[lab]= labels.length===1
        ? {color:base.color, marker:base.marker, size:base.size}
        : {color:DEFAULT_PALETTE[i%DEFAULT_PALETTE.length],
           marker:varySymbols?MARKER_CYCLE[i%MARKER_CYCLE.length]:base.marker, size:base.size};
    });
    return styles;
  }
  const order = uniqueInOrder(colorKeys), seen={};
  labels.forEach((lab,i)=>{
    const key=colorKeys[i]; const s=seen[key]||0; seen[key]=s+1;
    styles[lab]={color:DEFAULT_PALETTE[order.indexOf(key)%DEFAULT_PALETTE.length],
      marker:MARKER_CYCLE[s%MARKER_CYCLE.length], size:base.size};
  });
  return styles;
}
function attributeStyleMaps(rows, colorKey, symbolKey){
  const colorMap={}, symbolMap={};
  if(colorKey){ uniqueInOrder(rows.map(r=>r._attr[colorKey]??"")).forEach(v=>{
    colorMap[v]=DEFAULT_PALETTE[Object.keys(colorMap).length%DEFAULT_PALETTE.length]; }); }
  if(symbolKey){ uniqueInOrder(rows.map(r=>r._attr[symbolKey]??"")).forEach(v=>{
    symbolMap[v]=MARKER_CYCLE[Object.keys(symbolMap).length%MARKER_CYCLE.length]; }); }
  return {colorMap, symbolMap};
}

/* ---------------- state ---------------- */
let datasets=[]; let selId=null; let nextId=1;
const CONTINENT_EXTENTS = {
  "World":[-180,180,-90,90], "Africa":[-20,55,-38,40], "Antarctica":[-180,180,-90,-60],
  "Asia":[25,180,-12,78], "Europe":[-25,45,34,72], "North America":[-170,-50,5,84],
  "Oceania":[105,180,-50,10], "South America":[-85,-33,-58,14],
};
const PROJ_DEFS = {
  "Equirectangular":{make:()=>d3.geoEquirectangular(), maxLat:90},
  "Mercator":{make:()=>d3.geoMercator(), maxLat:83},
  "Robinson":{make:()=>d3.geoRobinson(), maxLat:90},
  "Mollweide":{make:()=>d3.geoMollweide(), maxLat:90},
  "Natural Earth":{make:()=>d3.geoNaturalEarth1(), maxLat:90},
  "Winkel Tripel":{make:()=>d3.geoWinkel3(), maxLat:90},
  "Globe (Orthographic)":{make:()=>d3.geoOrthographic().clipAngle(90), maxLat:90, globe:true, origin:[0,0]},
  "Lambert: N. America":{make:()=>d3.geoConicConformal().parallels([20,60]), maxLat:90, origin:[-96,40], lambert:true, region:"North America"},
  "Lambert: Europe":{make:()=>d3.geoConicConformal().parallels([35,65]), maxLat:90, origin:[10,52], lambert:true, region:"Europe"},
  "Lambert: Asia":{make:()=>d3.geoConicConformal().parallels([15,65]), maxLat:90, origin:[95,30], lambert:true, region:"Asia"},
  "Lambert: S. America":{make:()=>d3.geoConicConformal().parallels([-42,-5]), maxLat:90, origin:[-60,-32], lambert:true, region:"South America"},
  "Lambert: Africa":{make:()=>d3.geoAzimuthalEqualArea(), maxLat:90, origin:[20,5], lambert:true, azimuthal:true, region:"Africa"},
};
const OCEAN_COLORS = {none:null, grey:"#dcdcdc", blue:"#d4e6f4"};
const opts = {
  extent:"World", projection:"Equirectangular", centerLon:0, centerLat:0,
  orientation:"landscape", showLand:true, landColor:"#ffffff", showBorders:true,
  showCoast:true, ocean:"blue", graticule:0, title:"", compass:false, labels:false,
  matColor:"#ffffff", lineWidth:1,
  legShow:true, legFrame:true, legPos:"tr", legTitle:"", legFont:12, legCols:1, legScale:1,
};
let legendDrag=null; // {x,y} fractional override
let view={k:1,x:0,y:0};      // scroll-wheel zoom / drag pan over the map
let frameRect=[[0,0],[0,0]]; // current map rectangle, for clamping the pan
function clamp(v,a,b){ return v<a?a:(v>b?b:v); }
function viewTransform(){ return `translate(${view.x.toFixed(2)},${view.y.toFixed(2)}) scale(${view.k})`; }
function clampView(){
  const [[rx0,ry0],[rx1,ry1]]=frameRect;
  view.k=clamp(view.k,1,12);
  if(view.k<=1.0001){ view.x=0; view.y=0; return; }
  view.x=clamp(view.x, rx1*(1-view.k), rx0*(1-view.k));
  view.y=clamp(view.y, ry1*(1-view.k), ry0*(1-view.k));
}
function applyView(){ const vp=svg.querySelector("#viewport"); if(vp) vp.setAttribute("transform",viewTransform()); }

/* ---------------- dataset styling resolution ---------------- */
function resolveGroups(ds){
  // returns {mode, groups:[{label,style,rows}], legend:{...}}
  const rows = ds.rows;
  if(ds.symbolBy){
    const {colorMap,symbolMap} = attributeStyleMaps(rows, ds.colorBy, ds.symbolBy);
    const combos = uniqueInOrder(rows.map(r=>JSON.stringify([r._attr[ds.colorBy]??"", r._attr[ds.symbolBy]??""])));
    const groups = combos.map(js=>{
      const [cv,sv]=JSON.parse(js);
      const sub = rows.filter(r=>(r._attr[ds.colorBy]??"")===cv && (r._attr[ds.symbolBy]??"")===sv);
      const label = [cv,sv].filter(Boolean).join(" / ") || "All points";
      const defColor = Object.values(colorMap)[0]||DEFAULT_PALETTE[0];
      return {label, rows:sub, style:{color:colorMap[cv]||defColor, marker:symbolMap[sv]||"Circle", size:ds.base.size}};
    });
    applyOverrides(ds, groups);
    return {mode:"attr", groups, colorMap, symbolMap, colorKey:ds.colorBy, symbolKey:ds.symbolBy};
  }
  const grp = groupPoints(rows, ds.groupBy);
  const labels = grp.map(g=>g[0]);
  const colorKeys = ds.colorBy ? grp.map(g=>{ const r=g[1][0]; return r?(r._attr[ds.colorBy]??""):""; }) : null;
  const styles = defaultStyles(labels, colorKeys, ds.varySymbols, ds.base);
  const groups = grp.map(([label,sub])=>({label, rows:sub, style:{...styles[label]}}));
  if(!ds.groupBy && groups.length===1) groups[0].label = ds.name;
  applyOverrides(ds, groups);
  return {mode:"group", groups};
}
function applyOverrides(ds, groups){
  for(const g of groups){ const o=ds.overrides[g.label]; if(o) g.style={...g.style,...o}; }
}

