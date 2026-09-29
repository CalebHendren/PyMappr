/* zoom + pan over the map */
const stageEl=$("#stage");
stageEl.addEventListener("wheel",e=>{
  e.preventDefault();
  const r=svg.getBoundingClientRect();
  const sx=e.clientX-r.left, sy=e.clientY-r.top;
  const oldK=view.k;
  const newK=clamp(oldK*Math.exp(-e.deltaY*0.0015), 1, 12);
  if(newK===oldK) return;
  const lx=(sx-view.x)/oldK, ly=(sy-view.y)/oldK; // point under cursor, in scene coords
  view.k=newK; view.x=sx-newK*lx; view.y=sy-newK*ly;
  clampView(); render();
},{passive:false});
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
  for(const k of ["groupBy","colorBy","symbolBy"])
    if(ds[k]!=null && !ds.columns.includes(ds[k])) ds[k]=null;
  if(!Array.isArray(ds.rows) && ds._import && Array.isArray(ds._import.rows) && ds._import.mapping)
    ds.rows = pointsFromMapping(ds._import, ds._import.mapping).points;
  if(!Array.isArray(ds.rows)) return null;
  ds.rows = ds.rows.filter(r=>r && isFinite(r.lon) && isFinite(r.lat))
                   .map(r=>r._attr ? r : {...r, _attr:{}});
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
  for(const [id,kind] of LEGEND_CONTROLS){
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
let rt; new ResizeObserver(()=>{ clearTimeout(rt); rt=setTimeout(render,60); }).observe($("#stage"));
syncOrigin(!restored);   // keep any restored centre/extent when reloading
syncStylePanel();
renderDatasetList();
renderNow();   // also clamps a restored zoom/pan to the current window size