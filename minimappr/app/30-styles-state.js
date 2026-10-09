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
// `offset` starts the colours further into the palette, so several datasets
// on one map get distinct default colours. Mirrors styles.default_styles.
function defaultStyles(labels, colorKeys, varySymbols, base, offset=0){
  const styles={}, pal=palette();
  if(!colorKeys){
    labels.forEach((lab,i)=>{
      styles[lab]= labels.length===1
        ? {color:base.color, marker:base.marker, size:base.size}
        : {color:pal[(i+offset)%pal.length],
           marker:varySymbols?MARKER_CYCLE[i%MARKER_CYCLE.length]:base.marker, size:base.size};
    });
    return styles;
  }
  const order=new Map(), seen={};
  for(const key of colorKeys) if(!order.has(key)) order.set(key, order.size);
  labels.forEach((lab,i)=>{
    const key=colorKeys[i]; const s=seen[key]||0; seen[key]=s+1;
    styles[lab]={color:pal[(order.get(key)+offset)%pal.length],
      marker:MARKER_CYCLE[s%MARKER_CYCLE.length], size:base.size};
  });
  return styles;
}
// Where each dataset's colours start in the palette: group-by datasets pick
// up where the last visible one stopped, advancing by their number of
// groups, so a second dataset is not red again. Symbol-by datasets colour by
// value and take no part. Mirrors layout.layout_points' palette_offset.
function paletteOffsets(){
  const out=new Map(); let offset=0;
  for(const ds of datasets){
    out.set(ds.id, offset);
    if(ds.visible && ds.rows.length && !ds.symbolBy) offset+=groupPoints(ds.rows, ds.groupBy).length;
  }
  return out;
}

// More shapes than this stop being easy to tell apart. Matches
// LEGIBLE_MARKER_LIMIT in styles.py.
const LEGIBLE_MARKER_LIMIT=6;
// How many shapes a reader has to tell apart: under nesting, the most
// symbol values inside one colour group (shapes restart per group);
// otherwise every symbol value. Mirrors styles.marker_load.
function markerLoad(rows, colorKey, symbolKey, hierarchy){
  if(!symbolKey || !rows.length) return 0;
  if(!resolveNesting(rows, colorKey, symbolKey, hierarchy))
    return new Set(rows.map(r=>r._attr[symbolKey]??"")).size;
  const per=new Map();
  for(const r of rows){
    const c=r._attr[colorKey]??"";
    if(!per.has(c)) per.set(c, new Set());
    per.get(c).add(r._attr[symbolKey]??"");
  }
  return Math.max(...[...per.values()].map(s=>s.size));
}
// A warning for the status line when the map asks too much of its shapes,
// or when forced nesting leaves the key not describing the map; null when
// all is well. Mirrors PyMapprApp._warn_marker_load, wording included.
function legendWarning(visible){
  if(opts.legHierarchy==="always"){
    for(const ds of visible){
      if(!ds.symbolBy || !ds.colorBy) continue;
      if(resolveNesting(ds.rows, ds.colorBy, ds.symbolBy, "auto")) continue;
      return `${ds.name}: “${ds.symbolBy}” does not nest inside “${ds.colorBy}”, so each `
        + "shape is listed under the first colour it appears in. Set Hierarchy to Auto for "
        + "two independent keys.";
    }
  }
  let worst=0, worstDs=null;
  for(const ds of visible){
    const load=markerLoad(ds.rows, ds.colorBy, ds.symbolBy, opts.legHierarchy);
    if(load>worst){ worst=load; worstDs=ds; }
  }
  if(worst<=LEGIBLE_MARKER_LIMIT) return null;
  return `${worstDs.name}: “${worstDs.symbolBy}” needs ${worst} shapes, more than the `
    + `${LEGIBLE_MARKER_LIMIT} that stay easy to tell apart. Consider a Color by column that `
    + "groups them, or filtering to fewer values.";
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
  // Centred wherever the user puts it; no region of its own.
  "Lambert Azimuthal (custom)":{make:()=>d3.geoAzimuthalEqualArea(), maxLat:90, origin:[0,0], lambert:true, azimuthal:true},
};
const OCEAN_COLORS = {none:null, grey:"#dcdcdc", blue:"#d4e6f4"};
// Every legend control, as [element id, kind, default]. One table drives the
// defaults below, the listeners in 70-events.js and the restore in
// 80-view-persist-theme-boot.js, so adding a setting is one row rather than
// four near-identical lines in three files.
//   bool -> checkbox, num -> number input, str -> text/select/colour
// The defaults are legend.LegendOptions'. Sizes are points; the gaps and the
// swatch width are fractions of the font size, as matplotlib's legend
// measures them.
const LEGEND_CONTROLS = [
  // what is shown at all
  ["legShow", "bool", true],
  ["legPos", "str", "best"],
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
  // Only matters while the filter bar hides every row inside a group.
  ["legEmptyGroups", "bool", false],
  // nested keys
  ["legIndent", "num", 3],
  ["legBoldGroups", "bool", true],
  ["legGroupSpacer", "bool", true],
  ["legGroupSwatch", "str", "circle"],
  ["legSymbolColor", "str", "#555555"],
  // layout
  ["legCols", "num", 1],
  ["legScale", "num", 1],
  ["legSwatchWidth", "num", 2],          // handlelength
  ["legColSpacing", "num", 2],           // columnspacing
  ["legRowSpacing", "num", 0.5],         // labelspacing
  ["legSwatchGap", "num", 0.8],          // handletextpad
  ["legPad", "num", 0.4],                // borderpad
  // frame
  ["legFrame", "bool", true],
  ["legFrameColor", "str", "#ffffff"],
  ["legFrameAlpha", "num", 0.85],
  ["legFrameEdge", "str", "#cccccc"],
  ["legFrameWidth", "num", 0.8],
  ["legRadius", "num", 1.6],             // matplotlib's round box: 0.2 of 8 pt
  ["legShadow", "bool", false],
  // text
  ["legFont", "num", 8],
  ["legTitleFont", "num", 9],
  ["legFontFamily", "str", "sans-serif"],
  ["legLabelColor", "str", "#000000"],
  ["legTitleColor", "str", "#000000"],
  ["legTitleAlign", "str", "center"],
  ["legLabelBold", "bool", false],
  ["legLabelItalic", "bool", false],
  ["legLabelUnderline", "bool", false],
  ["legTitleBold", "bool", true],
  ["legTitleItalic", "bool", false],
  ["legTitleUnderline", "bool", false],
];
// Map settings that are a plain control each, in the same form: the compass,
// scale bar, grid label and export options. The legend table's listener and restore serve these
// too.
const MAP_CONTROLS = [
  ["compassPos", "str", "upper right"],
  ["compassStyle", "str", "arrow"],        // arrow | triangle
  ["compassSize", "num", 1],
  ["scaleUnits", "str", "km"],             // km | mi | both
  ["scalePos", "str", "lower left"],
  ["scaleStyle", "str", "segmented"],      // segmented | plain
  ["scaleLengthMode", "str", "auto"],      // auto | fixed
  ["scaleFixed", "num", 100],              // in scaleUnits, for a fixed length
  ["gridHideLabels", "bool", false],       // degree labels on Equirectangular
  // The inset map (57-inset.js), as decorations.InsetOptions, without the
  // State region. The custom extent stays text so it can be left blank.
  ["insetShow", "bool", false],
  ["insetRegion", "str", "country"],       // country | around | custom | a CONTINENT_EXTENTS name
  ["insetZoomOut", "num", 6],              // "around": the view's span times this
  ["insetLonMin", "str", ""],              // "custom"
  ["insetLonMax", "str", ""],
  ["insetLatMin", "str", ""],
  ["insetLatMax", "str", ""],
  ["insetProjection", "str", "same"],      // same | Equirectangular | Robinson | Globe
  ["insetPos", "str", "lower right"],
  ["insetSize", "num", 0.3],               // width, as a fraction of the frame
  ["insetCountries", "bool", true],
  ["insetLand", "bool", true],
  ["insetOcean", "str", "none"],           // none | grey | blue
  ["insetPoints", "bool", true],
  ["insetBox", "bool", true],
  ["insetBoxColor", "str", "#d62728"],
  ["exportFormat", "str", "png"],          // png | jpeg | webp | tiff | pdf | svg
  ["exportWidth", "num", 9],               // print width; PyMappr's figure is 9 in
  ["exportUnit", "str", "in"],             // in | cm
  ["exportDpi", "num", 200],               // PyMappr's default export DPI
];
// Changing one of these re-derives the rows; the rest only restyle. Kept for
// readability - MiniMappr rebuilds the whole SVG either way.
// The legend half of the publication style: a plain white box with a thin
// black border, and italic entries because taxon names are set in italics.
// Mirrors legend.PUBLICATION_LEGEND: 9/10 pt text, a step up from the 8/9 pt
// defaults.
const PUBLICATION_LEGEND = {legFrame:true, legFrameColor:"#ffffff", legFrameAlpha:1,
  legFrameEdge:"#000000", legFrameWidth:0.5, legRadius:0, legShadow:false,
  legLabelItalic:true, legFont:9, legTitleFont:10};
const LEGEND_CONTENT_KEYS = new Set(["legHierarchy", "legOrder", "legCounts",
  "legCountFormat", "legBlankLabel", "legSectionTitles", "legTitleSeparator",
  "legDatasetPrefix", "legEmptyGroups", "legGroupSwatch"]);

const opts = {
  extent:"World", projection:"Equirectangular", centerLon:0, centerLat:0,
  orientation:"landscape", showLand:true, landColor:"#ffffff", showBorders:true,
  showCoast:true, ocean:"none", graticule:0, title:"", compass:false, labels:false,
  matColor:"#ffffff", lineWidth:1, palette:"Default", scaleBar:false,
  // The outline drawn around filled markers (open markers outline in their
  // own colour). White keeps overlapping points apart; width 0 turns it off.
  pointEdgeColor:POINT_EDGE_COLOR, pointEdgeWidth:POINT_EDGE_WIDTH,
};
for(const [id,,value] of [...LEGEND_CONTROLS, ...MAP_CONTROLS]) opts[id]=value;
// Where the scale bar was dragged to, as frame fractions; null = its corner.
opts.scaleAnchor=null;
// Where the inset was dragged to, as frame fractions of its lower left
// corner; null = its corner.
opts.insetAnchor=null;
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

/* filter bar */
// Which values of one column of the selected dataset the filter bar hides.
// Not saved, as in PyMappr, and dropped when the selection moves to another
// dataset. Hidden values are kept rather than shown ones, so a point placed
// with a new value shows up instead of being filtered out unseen.
let filter={dsId:null, column:null, hidden:new Set()};
function filterSig(){
  return filter.column && filter.hidden.size
    ? JSON.stringify([filter.dsId, filter.column, [...filter.hidden]]) : "";
}
// The rows the map draws. Remembered per row array and filter, since the
// render, the legend and the status line all ask.
const shownCache=new WeakMap();
function shownRows(ds){
  if(filter.dsId!==ds.id || !filter.column || !filter.hidden.size) return ds.rows;
  const sig=filterSig(), hit=shownCache.get(ds.rows);
  if(hit && hit.sig===sig) return hit.rows;
  const col=filter.column;
  const rows=ds.rows.filter(r=>!filter.hidden.has(r._attr[col]??""));
  shownCache.set(ds.rows, {sig, rows});
  return rows;
}

/* dataset styling resolution */
// Colours and shapes are worked out from the whole dataset, so a group keeps
// its look while the filter hides others; only the drawn rows are filtered.
// Mirrors layout.group_styles / layout._attribute_layout.
function resolveGroups(ds, offset){
  // returns {mode, groups:[{label,style,rows}], shown, filtering, ...}
  const rows = ds.rows;
  const shown = shownRows(ds), filtering = shown!==rows;
  if(ds.symbolBy){
    const nestedNow = resolveNesting(rows, ds.colorBy, ds.symbolBy, opts.legHierarchy);
    const owner = nestedNow ? ownerMap(rows, ds.symbolBy, ds.colorBy) : null;
    const {colorMap,symbolMap} = attributeStyleMaps(rows, ds.colorBy, ds.symbolBy, nestedNow, owner);
    const defColor = Object.values(colorMap)[0]||palette()[0];
    const combos = bucketBy(shown, r=>(r._attr[ds.colorBy]??"")+ROW_SEP+(r._attr[ds.symbolBy]??""));
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
        // A colour pinned on the symbol row only reaches the points when no
        // colour key exists to defer to.
        const base=style.color;
        style=applyOverride(style, ds.overrides[rowKey("symbol",sv)]);
        if(ds.colorBy) style={...style, color:base};
        const co=ds.overrides[rowKey("color",cv)];
        if(co&&co.color) style={...style, color:co.color};
      }
      return {label, rows:sub, style};
    });
    return {mode:"attr", groups, colorMap, symbolMap, colorKey:ds.colorBy, symbolKey:ds.symbolBy,
            nested:nestedNow, owner, shown, filtering};
  }
  const grp = groupPoints(rows, ds.groupBy);
  const labels = grp.map(g=>g[0]);
  const colorKeys = ds.colorBy ? grp.map(g=>{ const r=g[1][0]; return r?(r._attr[ds.colorBy]??""):""; }) : null;
  if(offset===undefined) offset=paletteOffsets().get(ds.id)||0;
  const styles = defaultStyles(labels, colorKeys, ds.varySymbols, ds.base, offset);
  // A group the filter empties keeps its place and style, with no rows.
  const shownBy = filtering ? new Map(groupPoints(shown, ds.groupBy)) : null;
  const groups = grp.map(([label,sub])=>({label, rows:shownBy ? (shownBy.get(label)||[]) : sub,
                                          style:{...styles[label]}}));
  if(!ds.groupBy && groups.length===1) groups[0].label = ds.name;
  for(const g of groups) g.style=applyOverride(g.style, ds.overrides[rowKey("group",g.label)]);
  return {mode:"group", groups, shown, filtering};
}

