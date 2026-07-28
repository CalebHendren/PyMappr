/* ---------------- zoom + pan over the map ---------------- */
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
  clampView(); applyView(); scheduleSave();
},{passive:false});
svg.addEventListener("mousedown",e=>{
  if(e.button!==0) return;
  // Click-to-place: drop a point where the map is clicked (ignore drags).
  if(placeMode){
    e.preventDefault();
    const sx=e.clientX, sy=e.clientY; let moved=false;
    function mv(ev){ if(Math.abs(ev.clientX-sx)+Math.abs(ev.clientY-sy)>4) moved=true; }
    function up(ev){ window.removeEventListener("mousemove",mv); window.removeEventListener("mouseup",up);
      if(!moved) placeAt(ev.clientX, ev.clientY); }
    window.addEventListener("mousemove",mv); window.addEventListener("mouseup",up);
    return;
  }
  // Spinning the globe: a drag rotates it by re-centring the projection.
  if(currentProjDef().globe){
    e.preventDefault();
    const sx=e.clientX, sy=e.clientY, lon0=opts.centerLon, lat0=opts.centerLat;
    const r=svg.getBoundingClientRect();
    const scale=180/Math.max(Math.min(r.width,r.height),1);  // deg per pixel across the disk
    svg.classList.add("panning");
    function mv(ev){
      let lon=lon0-(ev.clientX-sx)*scale, lat=clamp(lat0+(ev.clientY-sy)*scale,-90,90);
      lon=((lon+180)%360+360)%360-180;
      opts.centerLon=lon; opts.centerLat=lat;
      $("#centerLon").value=Math.round(lon); $("#centerLat").value=Math.round(lat);
      render();
    }
    function up(){ window.removeEventListener("mousemove",mv); window.removeEventListener("mouseup",up);
      svg.classList.remove("panning"); scheduleSave(); }
    window.addEventListener("mousemove",mv); window.addEventListener("mouseup",up);
    return;
  }
  if(view.k<=1.0001) return; // nothing to pan at fit-to-frame zoom
  e.preventDefault();
  const sx=e.clientX, sy=e.clientY, ox=view.x, oy=view.y; let moved=false;
  svg.classList.add("panning");
  function mv(ev){ view.x=ox+(ev.clientX-sx); view.y=oy+(ev.clientY-sy); clampView(); applyView(); moved=true; }
  function up(){ window.removeEventListener("mousemove",mv); window.removeEventListener("mouseup",up);
    svg.classList.remove("panning"); if(moved) scheduleSave(); }
  window.addEventListener("mousemove",mv); window.addEventListener("mouseup",up);
});
svg.addEventListener("dblclick",()=>{ view={k:1,x:0,y:0}; applyView(); scheduleSave(); }); // reset view

/* ---------------- persistence (localStorage) ---------------- */
const STORE_KEY="minimappr.state.v1";
let saveTimer=null;
function scheduleSave(){ clearTimeout(saveTimer); saveTimer=setTimeout(saveState,400); }
function saveState(){
  try{
    localStorage.setItem(STORE_KEY, JSON.stringify({
      theme:$("#themeSelect").value, datasets, selId, nextId, opts, view, legendDrag
    }));
  }catch(e){ /* private mode or over quota: keep working, just don't persist */ }
}
function loadState(){
  let d; try{ d=JSON.parse(localStorage.getItem(STORE_KEY)); }catch(e){ return false; }
  if(!d) return false;
  if(d.theme) $("#themeSelect").value=d.theme;
  if(Array.isArray(d.datasets)) datasets=d.datasets;
  if(d.selId!=null) selId=d.selId;
  if(typeof d.nextId==="number") nextId=d.nextId;
  if(d.opts) Object.assign(opts, d.opts);
  if(d.view) view=d.view;
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
  $("#matColor").value=opts.matColor;
  $("#lineWidth").value=opts.lineWidth; $("#lwVal").textContent=Number(opts.lineWidth).toFixed(2);
  $("#legShow").checked=opts.legShow; $("#legFrame").checked=opts.legFrame;
  $("#legCounts").checked=opts.legCounts; $("#legPos").value=opts.legPos;
  $("#legTitle").value=opts.legTitle; $("#legFont").value=opts.legFont;
  $("#legCols").value=opts.legCols; $("#legScale").value=opts.legScale;
  $("#legLabelBold").checked=opts.legLabelBold; $("#legLabelItalic").checked=opts.legLabelItalic;
  $("#legLabelUnderline").checked=opts.legLabelUnderline;
  $("#legTitleBold").checked=opts.legTitleBold; $("#legTitleItalic").checked=opts.legTitleItalic;
  $("#legTitleUnderline").checked=opts.legTitleUnderline;
}

/* ---------------- theme ---------------- */
const themeSel=$("#themeSelect");
const darkMQ=window.matchMedia("(prefers-color-scheme: dark)");
function applyTheme(){
  const v=themeSel.value;
  const mode = v==="system" ? (darkMQ.matches?"dark":"light") : v;
  document.documentElement.setAttribute("data-theme", mode);
}
themeSel.addEventListener("change",()=>{ applyTheme(); scheduleSave(); });
darkMQ.addEventListener("change",()=>{ if(themeSel.value==="system") applyTheme(); });

/* ---------------- boot ---------------- */
const restored=loadState();
applyTheme();
if(restored) syncMapControls();
let rt; new ResizeObserver(()=>{ clearTimeout(rt); rt=setTimeout(render,60); }).observe($("#stage"));
syncOrigin(!restored);   // keep any restored centre/extent when reloading
syncStylePanel();
renderDatasetList();
render();
clampView(); applyView(); // keep a restored zoom/pan valid for the current window size