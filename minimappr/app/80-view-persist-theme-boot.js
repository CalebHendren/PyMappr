/* zoom + pan over the map */
const mapWrap=$("#mapwrap");
// Zoom by `factor` keeping the screen point (sx, sy) where it is.
function zoomAbout(factor, sx, sy){
  const oldK=view.k;
  const newK=clamp(oldK*factor, 1, 12);
  if(newK===oldK) return;
  const lx=(sx-view.x)/oldK, ly=(sy-view.y)/oldK; // that point, in scene coords
  view.k=newK; view.x=sx-newK*lx; view.y=sy-newK*ly;
  clampView(); render();
}
// The buttons and keys zoom about the middle of the frame, x1.5 a step as
// PyMappr's buttons do.
function zoomStep(factor){
  const [[x0,y0],[x1,y1]]=frameRect;
  zoomAbout(factor, (x0+x1)/2, (y0+y1)/2);
}
function resetZoom(){ view={k:1,x:0,y:0}; render(); }
mapWrap.addEventListener("wheel",e=>{
  e.preventDefault();
  const r=svg.getBoundingClientRect();
  zoomAbout(Math.exp(-e.deltaY*0.0015), e.clientX-r.left, e.clientY-r.top);
},{passive:false});
$("#zoomIn").addEventListener("click",()=>zoomStep(1.5));
$("#zoomOut").addEventListener("click",()=>zoomStep(1/1.5));
$("#zoomReset").addEventListener("click",resetZoom);
// + / - / 0 zoom from the keyboard, except while typing or in a dialog;
// with Ctrl or Cmd they stay the browser's own page zoom.
document.addEventListener("keydown",e=>{
  if(e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
  if(e.target.closest && e.target.closest("input,select,textarea,[contenteditable]")) return;
  if($$(".modal-bg.on").length) return;
  if(e.key==="+" || e.key==="=") zoomStep(1.5);
  else if(e.key==="-" || e.key==="_") zoomStep(1/1.5);
  else if(e.key==="0") resetZoom();
  else return;
  e.preventDefault();
});
// Frame the data after an import, as PyMappr does: the box around every
// visible point plus 15% (at least 2 degrees), clamped to the world. The
// zoom is within the region's own frame, so data wider than the region
// leaves the region as it is; the globe is left alone.
function zoomToData(){
  const rows=datasets.filter(d=>d.visible).flatMap(d=>d.rows);
  if(!rows.length || currentProjDef().globe){ render(); return; }
  let lo0=Infinity, lo1=-Infinity, la0=Infinity, la1=-Infinity;
  for(const r of rows){ lo0=Math.min(lo0,r.lon); lo1=Math.max(lo1,r.lon);
    la0=Math.min(la0,r.lat); la1=Math.max(la1,r.lat); }
  const px=Math.max((lo1-lo0)*0.15, 2), py=Math.max((la1-la0)*0.15, 2);
  lo0=Math.max(lo0-px,-180); lo1=Math.min(lo1+px,180);
  la0=Math.max(la0-py,-90); la1=Math.min(la1+py,90);
  view={k:1,x:0,y:0};
  const W=mapWrap.clientWidth, H=mapWrap.clientHeight;
  const rect=drawRect(W,H), proj=buildProjection(W,H);
  let bx0=Infinity, bx1=-Infinity, by0=Infinity, by1=-Infinity;
  for(const pt of boxSample(lo0,lo1,la0,la1).coordinates){
    const xy=proj(pt);
    if(!xy || !Number.isFinite(xy[0]) || !Number.isFinite(xy[1])) continue;
    bx0=Math.min(bx0,xy[0]); bx1=Math.max(bx1,xy[0]); by0=Math.min(by0,xy[1]); by1=Math.max(by1,xy[1]);
  }
  const [[rx0,ry0],[rx1,ry1]]=rect;
  if(!(bx1>bx0) || !(by1>by0)){ render(); return; }
  const k=clamp(Math.min((rx1-rx0)/(bx1-bx0), (ry1-ry0)/(by1-by0)), 1, 12);
  // A whole world is shorter than a landscape frame; zoomed in too little
  // to fill the frame, it would show blank bands where its round outline
  // used to be. Nearly global data keeps the whole map instead.
  const sb=d3.geoPath(proj).bounds({type:"Sphere"});
  const fill=Math.max((rx1-rx0)/(sb[1][0]-sb[0][0]), (ry1-ry0)/(sb[1][1]-sb[0][1]));
  if(k>1.05 && k>=fill-1e-6){
    view={k, x:(rx0+rx1)/2-k*(bx0+bx1)/2, y:(ry0+ry1)/2-k*(by0+by1)/2};
    frameRect=rect; clampView();
  }
  render();
}
// Pointer events, so a finger or a pen drags, spins and places like a mouse.
svg.addEventListener("pointerdown",e=>{
  if(e.button!==0 || !e.isPrimary) return;
  // Click-to-place: drop a point where the map is clicked (ignore drags).
  if(placeMode){
    e.preventDefault();
    const sx=e.clientX, sy=e.clientY; let moved=false;
    trackPointer(svg, e,
      ev=>{ if(Math.abs(ev.clientX-sx)+Math.abs(ev.clientY-sy)>4) moved=true; },
      (ev,lifted)=>{ if(lifted && !moved) placeAt(ev.clientX, ev.clientY); });
    return;
  }
  // Spinning the globe: a drag rotates it by re-centring the projection.
  if(currentProjDef().globe){
    e.preventDefault();
    const sx=e.clientX, sy=e.clientY, lon0=opts.centerLon, lat0=opts.centerLat;
    const r=svg.getBoundingClientRect();
    const scale=180/Math.max(Math.min(r.width,r.height),1)/view.k;  // deg per pixel across the disk
    svg.classList.add("panning");
    trackPointer(svg, e, ev=>{
      let lon=lon0-(ev.clientX-sx)*scale, lat=clamp(lat0+(ev.clientY-sy)*scale,-90,90);
      lon=((lon+180)%360+360)%360-180;
      opts.centerLon=lon; opts.centerLat=lat;
      $("#centerLon").value=Math.round(lon); $("#centerLat").value=Math.round(lat);
      render();
    }, ()=>{ svg.classList.remove("panning"); scheduleSave(); });
    return;
  }
  if(!isZoomed()) return; // nothing to pan at fit-to-frame zoom
  e.preventDefault();
  const sx=e.clientX, sy=e.clientY, ox=view.x, oy=view.y; let moved=false;
  svg.classList.add("panning");
  trackPointer(svg, e,
    ev=>{ view.x=ox+(ev.clientX-sx); view.y=oy+(ev.clientY-sy); clampView(); render(); moved=true; },
    ()=>{ svg.classList.remove("panning"); if(moved) scheduleSave(); });
});
svg.addEventListener("dblclick",()=>{ view={k:1,x:0,y:0}; render(); }); // reset view

/* persistence (localStorage) */
const STORE_KEY="minimappr.state.v1";
let saveTimer=null, saveWarned=false;
function scheduleSave(){ clearTimeout(saveTimer); saveTimer=setTimeout(saveState,400); }
// An imported dataset's points are derived from its raw table (_import), so
// only the table is stored and the points are rebuilt on load; storing both
// doubled the size and ran a larger export into the storage quota.
function storedDataset(ds){
  const rebuildable=ds.source!=="manual" && ds._import && Array.isArray(ds._import.rows) && ds._import.mapping;
  return rebuildable ? {...ds, rows:undefined} : ds;
}
function saveState(){
  try{
    localStorage.setItem(STORE_KEY, JSON.stringify({
      theme:$("#themeSelect").value, datasets:datasets.map(storedDataset), selId, nextId, opts, view, legendDrag
    }));
  }catch(e){
    // Private mode or over quota: keep working, but say once that a reload
    // will not bring this map back.
    if(!saveWarned){ saveWarned=true;
      flashStage("Autosave is off: browser storage is full or blocked. Export to keep this map."); }
  }
}
// Keep only the theme, then reload: every default lives in code, so a reload
// is a true first visit with no list of settings to keep in sync here.
$("#resetAll").addEventListener("click",()=>{
  if(!confirm("Reset MiniMappr? This removes every dataset and puts all settings back to their defaults.")) return;
  clearTimeout(saveTimer);
  try{ localStorage.setItem(STORE_KEY, JSON.stringify({theme:$("#themeSelect").value})); }
  catch(e){ try{ localStorage.removeItem(STORE_KEY); }catch(e2){} }
  location.reload();
});
// Fill in whatever an older or partial save lacks, so restoring never hands
// the renderer a dataset it cannot draw. Returns null for one past saving.
function normalizeDataset(d){
  if(!d || typeof d!=="object") return null;
  const ds={...d};
  ds.name = ds.name!=null ? String(ds.name) : "Dataset";
  ds.source = ds.source==="manual" ? "manual" : "csv";
  ds.columns = Array.isArray(ds.columns) ? ds.columns : [];
  ds.base = {color:"#d62728", marker:"Circle", size:30, ...(ds.base||{})};
  ds.overrides = ds.overrides && typeof ds.overrides==="object" ? ds.overrides : {};
  ds.opacity = typeof ds.opacity==="number" && isFinite(ds.opacity) ? ds.opacity : 1;
  ds.visible = ds.visible!==false;
  ds.varySymbols = !!ds.varySymbols;
  if(!Array.isArray(ds.rows) && ds._import && Array.isArray(ds._import.rows) && ds._import.mapping)
    ds.rows = pointsFromMapping(ds._import, ds._import.mapping).points;
  if(!Array.isArray(ds.rows)) return null;
  ds.rows = ds.rows.filter(r=>r && isFinite(r.lon) && isFinite(r.lat))
                   .map(r=>r._attr ? r : {...r, _attr:{}});
  // Rows rebuilt from the table lack the combined columns; work them out
  // again before checking which columns the choices below may name.
  applyCombined(ds);
  for(const k of ["groupBy","colorBy","symbolBy"])
    if(ds[k]!=null && !ds.columns.includes(ds[k])) ds[k]=null;
  if(ds.source==="manual" && !ds._manual){
    ds._manual={legend:ds.name, order:"latlon", base:ds.base,
      text:ds.rows.map(r=>`${r.lat.toFixed(5)}, ${r.lon.toFixed(5)}`+(r.label?", "+r.label:"")).join("\n")};
  }
  if(typeof ds.id!=="number") ds.id=null;   // numbered by loadState
  return ds;
}
function loadState(){
  let d; try{ d=JSON.parse(localStorage.getItem(STORE_KEY)); }catch(e){ return false; }
  if(!d || typeof d!=="object") return false;
  if(d.theme) $("#themeSelect").value=d.theme;
  if(Array.isArray(d.datasets)) datasets=d.datasets.map(normalizeDataset).filter(Boolean);
  if(typeof d.nextId==="number") nextId=d.nextId;
  for(const ds of datasets){ if(ds.id==null) ds.id=nextId++; nextId=Math.max(nextId, ds.id+1); }
  selId = datasets.some(ds=>ds.id===d.selId) ? d.selId : null;
  if(d.opts && typeof d.opts==="object") Object.assign(opts, d.opts);
  // A setting from a build that named things differently falls back rather
  // than leaving the map without a projection or region.
  if(!PROJ_DEFS[opts.projection]) opts.projection="Equirectangular";
  if(!CONTINENT_EXTENTS[opts.extent]) opts.extent="World";
  if(!PALETTES[opts.palette]) opts.palette="Default";
  normalizeInsetOpts();
  const v=d.view;
  if(v && [v.k,v.x,v.y].every(n=>typeof n==="number" && isFinite(n))) view={k:v.k,x:v.x,y:v.y};
  legendDrag=d.legendDrag||null;
  return true;
}
function setSegBy(sel,attr,val){ $$(sel+" button").forEach(b=>b.classList.toggle("on", b.dataset[attr]===val)); }
function syncMapControls(){
  $("#extent").value=opts.extent; $("#projection").value=opts.projection;
  $("#centerLon").value=opts.centerLon; $("#centerLat").value=opts.centerLat;
  setSegBy("#orientSeg","orient",opts.orientation);
  setSegBy("#oceanSeg","ocean",opts.ocean);
  setSegBy("#gratSeg","grat",String(opts.graticule));
  $("#showLand").checked=opts.showLand; $("#landColor").value=opts.landColor;
  $("#showBorders").checked=opts.showBorders; $("#showCoast").checked=opts.showCoast;
  $("#mapTitle").value=opts.title; $("#showCompass").checked=opts.compass; $("#showLabels").checked=opts.labels;
  $("#showScaleBar").checked=opts.scaleBar;
  $("#pointEdgeColor").value=opts.pointEdgeColor; $("#pointEdgeWidth").value=opts.pointEdgeWidth;
  $("#matColor").value=opts.matColor; $("#paletteSel").value=opts.palette;
  $("#lineWidth").value=opts.lineWidth; $("#lwVal").textContent=Number(opts.lineWidth).toFixed(2);
  // Legend controls come back from the same table that defines them, so a
  // new setting cannot end up rendering from a restored value while its
  // control still shows the default.
  for(const [id,kind] of [...LEGEND_CONTROLS, ...MAP_CONTROLS]){
    const node=$("#"+id);
    if(!node) continue;
    if(kind==="bool") node.checked=opts[id]; else node.value=opts[id];
  }
}

/* theme */
const themeSel=$("#themeSelect");
const darkMQ=window.matchMedia("(prefers-color-scheme: dark)");
function applyTheme(){
  const v=themeSel.value;
  const mode = v==="system" ? (darkMQ.matches?"dark":"light") : v;
  document.documentElement.setAttribute("data-theme", mode);
}
themeSel.addEventListener("change",()=>{ applyTheme(); scheduleSave(); });
darkMQ.addEventListener("change",()=>{ if(themeSel.value==="system") applyTheme(); });

/* boot */
const restored=loadState();
applyTheme();
if(restored) syncMapControls();
let rt; new ResizeObserver(()=>{ clearTimeout(rt); rt=setTimeout(render,60); }).observe(mapWrap);
syncOrigin(!restored);   // keep any restored centre/extent when reloading
syncStylePanel();
renderDatasetList();
renderNow();   // also clamps a restored zoom/pan to the current window size