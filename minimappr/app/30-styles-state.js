/* styling logic (ported from styles.py) */
function uniqueInOrder(arr){ const seen=new Set(), out=[]; for(const v of arr){ if(!seen.has(v)){seen.add(v);out.push(v);} } return out; }

// Bucket rows by a key in one pass; a Map keeps first-appearance order.
function bucketBy(rows, keyOf){
  const buckets=new Map();
  for(const r of rows){
    const k=keyOf(r); let b=buckets.get(k);
    if(!b) buckets.set(k, b=[]);
    b.push(r);
  }
  return buckets;
}
function groupPoints(rows, groupBy){
  if(!rows.length) return [];
  if(!groupBy) return [["All points", rows]];
  return [...bucketBy(rows, r=>r._attr[groupBy]??"")].map(([lab,sub])=>[lab||"(blank)", sub]);
}
function defaultStyles(labels, colorKeys, varySymbols, base){
  const styles={}, pal=palette();
  if(!colorKeys){
    labels.forEach((lab,i)=>{
      styles[lab]= labels.length===1
        ? {color:base.color, marker:base.marker, size:base.size}
        : {color:pal[i%pal.length],
           marker:varySymbols?MARKER_CYCLE[i%MARKER_CYCLE.length]:base.marker, size:base.size};
    });
    return styles;
  }
  const order=new Map(), seen={};
  for(const key of colorKeys) if(!order.has(key)) order.set(key, order.size);
  labels.forEach((lab,i)=>{
    const key=colorKeys[i]; const s=seen[key]||0; seen[key]=s+1;
    styles[lab]={color:pal[order.get(key)%pal.length],
      marker:MARKER_CYCLE[s%MARKER_CYCLE.length], size:base.size};
  });
  return styles;
}
// True when every value of symbolKey sits under exactly one value of colorKey -
// a hierarchy (genus/species) rather than a cross-product. Nesting is what makes
// it safe to reuse shapes across colour groups and to draw one nested key.
function nestsWithin(rows, colorKey, symbolKey){
  if(!colorKey || !symbolKey || !rows.length) return false;
  const owner={};
  for(const r of rows){
    const c=r._attr[colorKey]??"", s=r._attr[symbolKey]??"";
    if(owner[s]!==undefined && owner[s]!==c) return false;
    owner[s]=c;
  }
  return true;
}

// Legend rows are identified by a tagged key - the same tagging legendCounts
// uses - so a value in both the colour and the symbol column cannot have one
// row's customization land on the other. NUL separates the parts because it
// cannot occur in a data value, unlike "/" or ":" which routinely do.
const ROW_SEP="\u0000";
function rowKey(kind, ...parts){ return [kind,...parts].join(ROW_SEP); }
// A style with whatever colour/marker/size the user pinned for that row.
// Absent fields mean "whatever the styling rules worked out", so a row that
// was only renamed still follows a palette change.
function applyOverride(style, o){
  if(!style || !o) return style;
  return {color:o.color||style.color, marker:o.marker||style.marker,
          size:o.size||style.size};
}
function overrideLabel(o){ return (o && o.label) ? String(o.label) : null; }
function isHidden(o){ return !!(o && o.hidden); }
function manualOrder(o){
  return (o && o.order!=null) ? Number(o.order) : Number.MAX_SAFE_INTEGER;
}

// Whether to treat the two columns as a hierarchy, honouring the user's
// choice: "auto" detects it, "always" forces it, "never" refuses. Every
// caller goes through here so the map's shapes and the legend's layout can
// never disagree about it. Mirrors styles.resolve_nesting.
function resolveNesting(rows, colorKey, symbolKey, mode){
  if(!colorKey || !symbolKey || !rows.length) return false;
  if(mode==="never") return false;
  if(mode==="always") return true;
  return nestsWithin(rows, colorKey, symbolKey);
}
// Symbol value -> the colour group it belongs to, first occurrence wins.
// Under real nesting each symbol has one colour so the rule never bites; it
// only matters when nesting is forced onto crossed columns.
function ownerMap(rows, symbolKey, colorKey){
  const owner={};
  for(const r of rows){
    const s=r._attr[symbolKey]??"";
    if(!(s in owner)) owner[s]=r._attr[colorKey]??"";
  }
  return owner;
}
// Sort legend rows only - never the colour or symbol maps, which are keyed
// by first appearance; reshuffling those would repaint the map.
function orderLabels(values, order, countOf){
  const out=[...values];
  const key=v=>(v||"").toLowerCase();
  if(order==="az") return out.sort((a,b)=>key(a)<key(b)?-1:key(a)>key(b)?1:0);
  if(order==="za") return out.sort((a,b)=>key(a)<key(b)?1:key(a)>key(b)?-1:0);
  if(order==="count_desc"||order==="count_asc"){
    const sign=order==="count_desc"?-1:1, of=countOf||(()=>0);
    return out.sort((a,b)=>{
      const d=sign*(of(a)-of(b));
      return d!==0?d:(key(a)<key(b)?-1:key(a)>key(b)?1:0);
    });
  }
  return out;
}
function ordersByCount(){ return opts.legOrder==="count_desc"||opts.legOrder==="count_asc"; }
// A row's text: the value (or a stand-in when blank) with its count in the
// chosen format. Mirrors legend._legend_label.
function legendLabel(value, n, total){
  const label = value || opts.legBlankLabel;
  if(!opts.legCounts || n===undefined || n===null) return label;
  const pct = total ? Math.round(100*n/total) : 0;
  if(opts.legCountFormat==="n") return `${label} ${n}`;
  if(opts.legCountFormat==="(n, %)") return `${label} (${n}, ${pct}%)`;
  if(opts.legCountFormat==="%") return `${label} ${pct}%`;
  return `${label} (${n})`;
}

// `nested` and `owner` come from the caller, which needs them for the legend
// too, so the hierarchy is worked out once per dataset per render.
function attributeStyleMaps(rows, colorKey, symbolKey, nested, owner){
  const colorMap={}, symbolMap={}, pal=palette();
  if(colorKey){ uniqueInOrder(rows.map(r=>r._attr[colorKey]??"")).forEach((v,i)=>{
    colorMap[v]=pal[i%pal.length]; }); }
  if(symbolKey){
    // Shapes may only repeat when a colour tells the repeats apart, so the
    // cycle restarts per colour group when the columns nest: three genera of
    // three species each then need three shapes rather than nine. Turning
    // nesting off therefore also gives every symbol its own shape again.
    const seen={};
    uniqueInOrder(rows.map(r=>r._attr[symbolKey]??"")).forEach(v=>{
      const g=nested?(owner[v]??""):"";
      const i=seen[g]||0; seen[g]=i+1;
      symbolMap[v]=MARKER_CYCLE[i%MARKER_CYCLE.length]; });
  }
  return {colorMap, symbolMap};
}

/* state */
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
// Every legend control, as [element id, kind, default]. One table drives the
// defaults below, the listeners in 70-events.js and the restore in
// 80-view-persist-theme-boot.js, so adding a setting is one row rather than
// four near-identical lines in three files.
//   bool -> checkbox, num -> number input, str -> text/select/colour
const LEGEND_CONTROLS = [
  // what is shown at all
  ["legShow", "bool", true],
  ["legPos", "str", "tr"],
  ["legTitle", "str", ""],
  // rows and order (these change the row text, not just its look)
  ["legHierarchy", "str", "auto"],
  ["legOrder", "str", "data"],
  ["legCounts", "bool", false],
  ["legCountFormat", "str", "(n)"],
  ["legBlankLabel", "str", "(blank)"],
  ["legSectionTitles", "bool", true],
  ["legTitleSeparator", "str", " / "],
  ["legDatasetPrefix", "bool", true],
  // No "keep empty groups" here: PyMappr needs it because its filter bar can
  // hide every row inside a group, and MiniMappr has no filter.
  // nested keys
  ["legIndent", "num", 3],
  ["legBoldGroups", "bool", true],
  ["legGroupSpacer", "bool", true],
  ["legGroupSwatch", "str", "circle"],
  ["legSymbolColor", "str", "#555555"],
  // layout
  ["legCols", "num", 1],
  ["legScale", "num", 1],
  ["legRowSpacing", "num", 0.5],
  ["legSwatchGap", "num", 8],
  ["legPad", "num", 9],
  // frame
  ["legFrame", "bool", true],
  ["legFrameColor", "str", "#ffffff"],
  ["legFrameAlpha", "num", 0.92],
  ["legFrameEdge", "str", "#c7ccd2"],
  ["legFrameWidth", "num", 1],
  ["legRadius", "num", 6],
  ["legShadow", "bool", false],
  // text
  ["legFont", "num", 12],
  ["legTitleFont", "num", 13],
  ["legFontFamily", "str", "sans-serif"],
  ["legLabelColor", "str", "#22262c"],
  ["legTitleColor", "str", "#1d2127"],
  ["legTitleAlign", "str", "left"],
  ["legLabelBold", "bool", false],
  ["legLabelItalic", "bool", false],
  ["legLabelUnderline", "bool", false],
  ["legTitleBold", "bool", true],
  ["legTitleItalic", "bool", false],
  ["legTitleUnderline", "bool", false],
];
// Changing one of these re-derives the rows; the rest only restyle. Kept for
// readability - MiniMappr rebuilds the whole SVG either way.
const LEGEND_CONTENT_KEYS = new Set(["legHierarchy", "legOrder", "legCounts",
  "legCountFormat", "legBlankLabel", "legSectionTitles", "legTitleSeparator",
  "legDatasetPrefix", "legEmptyGroups", "legGroupSwatch"]);

const opts = {
  extent:"World", projection:"Equirectangular", centerLon:0, centerLat:0,
  orientation:"landscape", showLand:true, landColor:"#ffffff", showBorders:true,
  showCoast:true, ocean:"blue", graticule:0, title:"", compass:false, labels:false,
  matColor:"#ffffff", lineWidth:1, palette:"Default", scaleBar:false,
  // The outline drawn around filled markers (open markers outline in their
  // own colour). White keeps overlapping points apart; width 0 turns it off.
  // Matches POINT_EDGE_COLOR / POINT_EDGE_WIDTH in styles.py.
  pointEdgeColor:"#ffffff", pointEdgeWidth:0.6,
};
for(const [id,,value] of LEGEND_CONTROLS) opts[id]=value;
let currentProjection=null;     // the d3 projection from the last render()
let placeMode=false;            // click-to-place points onto the map
let placeDsId=null;             // manual dataset placed points go into
let legendDrag=null; // {x,y} fractional override
// Scroll-wheel zoom / drag pan over the map: screen = k * fitted + (x, y).
// It is folded into the projection (buildProjection), not applied as a
// transform, so zooming in keeps markers and line widths at their size.
let view={k:1,x:0,y:0};
let frameRect=[[0,0],[0,0]]; // current map rectangle, for clamping the pan
function clamp(v,a,b){ return v<a?a:(v>b?b:v); }
function isZoomed(){ return view.k>1.0001; }
function clampView(){
  const [[rx0,ry0],[rx1,ry1]]=frameRect;
  view.k=clamp(view.k,1,12);
  if(!isZoomed()){ view.x=0; view.y=0; return; }
  view.x=clamp(view.x, rx1*(1-view.k), rx0*(1-view.k));
  view.y=clamp(view.y, ry1*(1-view.k), ry0*(1-view.k));
}

/* dataset styling resolution */
function resolveGroups(ds){
  // returns {mode, groups:[{label,style,rows}], legend:{...}}
  const rows = ds.rows;
  if(ds.symbolBy){
    const nestedNow = resolveNesting(rows, ds.colorBy, ds.symbolBy, opts.legHierarchy);
    const owner = nestedNow ? ownerMap(rows, ds.symbolBy, ds.colorBy) : null;
    const {colorMap,symbolMap} = attributeStyleMaps(rows, ds.colorBy, ds.symbolBy, nestedNow, owner);
    const defColor = Object.values(colorMap)[0]||palette()[0];
    const combos = bucketBy(rows, r=>(r._attr[ds.colorBy]??"")+ROW_SEP+(r._attr[ds.symbolBy]??""));
    const groups = [...combos.values()].map(sub=>{
      const cv=sub[0]._attr[ds.colorBy]??"", sv=sub[0]._attr[ds.symbolBy]??"";
      const label = [cv,sv].filter(Boolean).join(" / ") || "All points";
      let style={color:colorMap[cv]||defColor, marker:symbolMap[sv]||"Circle", size:ds.base.size};
      // The row that governs a combination depends on the shape of the key:
      // a nested leaf owns the whole combination, while a crossed key takes
      // its colour from the colour row and its shape from the symbol row.
      if(nestedNow){
        style=applyOverride(style, ds.overrides[rowKey("pair",cv,sv)]);
      } else {
        style=applyOverride(style, ds.overrides[rowKey("symbol",sv)]);
        const co=ds.overrides[rowKey("color",cv)];
        if(co&&co.color) style={...style, color:co.color};
      }
      return {label, rows:sub, style};
    });
    return {mode:"attr", groups, colorMap, symbolMap, colorKey:ds.colorBy, symbolKey:ds.symbolBy,
            nested:nestedNow, owner};
  }
  const grp = groupPoints(rows, ds.groupBy);
  const labels = grp.map(g=>g[0]);
  const colorKeys = ds.colorBy ? grp.map(g=>{ const r=g[1][0]; return r?(r._attr[ds.colorBy]??""):""; }) : null;
  const styles = defaultStyles(labels, colorKeys, ds.varySymbols, ds.base);
  const groups = grp.map(([label,sub])=>({label, rows:sub, style:{...styles[label]}}));
  if(!ds.groupBy && groups.length===1) groups[0].label = ds.name;
  for(const g of groups) g.style=applyOverride(g.style, ds.overrides[rowKey("group",g.label)]);
  return {mode:"group", groups};
}

