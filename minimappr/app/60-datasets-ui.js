/* ---------------- dataset ingest ---------------- */
function makeDataset(name, columns, rows, base){
  // rows: array of {lon,lat,label,_attr}
  return {
    id:nextId++, name, visible:true, columns, rows,
    base: base || {color:"#d62728", marker:"Circle", size:30},
    groupBy: columns[0]||null, colorBy:null, symbolBy:null, varySymbols:false,
    overrides:{}, opacity:1, source:"csv",
  };
}
// The manual dataset that placed points are appended to: the selected one
// if it is manual, otherwise a fresh "Placed points" set.
function placementDataset(){
  let ds = placeDsId!=null ? datasets.find(d=>d.id===placeDsId) : null;
  if(!ds){
    const sel=selectedDataset();
    if(sel && sel.source==="manual"){ ds=sel; }
    else {
      ds=makeDataset("Placed points", [], [], {color:"#d62728",marker:"Circle",size:30});
      ds.groupBy=null; ds.source="manual";
      ds._manual={legend:"Placed points", text:"", order:"latlon", base:ds.base};
      datasets.push(ds); selId=ds.id;
    }
    placeDsId=ds.id;
  }
  return ds;
}
// Convert a screen click to lon/lat and append it as a point, exactly like
// a typed coordinate line (kept in _manual.text so Edit shows it too).
function placeAt(clientX, clientY){
  if(!currentProjection || !currentProjection.invert) return;
  const r=svg.getBoundingClientRect();
  const px=(clientX-r.left-view.x)/view.k, py=(clientY-r.top-view.y)/view.k;
  const ll=currentProjection.invert([px,py]);
  if(!ll || !isFinite(ll[0]) || !isFinite(ll[1])) return;
  let [lon,lat]=ll;
  if(lon< -180||lon>180||lat< -90||lat>90) return;
  if(currentProjDef().globe &&
     d3.geoDistance([lon,lat],[opts.centerLon,opts.centerLat])>Math.PI/2) return;
  const ds=placementDataset();
  const order=(ds._manual&&ds._manual.order)||"latlon";
  ds.rows.push({lon,lat,label:null,_attr:{Set:ds.name}});
  const line = order==="latlon" ? `${lat.toFixed(5)}, ${lon.toFixed(5)}`
                                : `${lon.toFixed(5)}, ${lat.toFixed(5)}`;
  ds._manual.text = ds._manual.text ? ds._manual.text+"\n"+line : line;
  renderDatasetList(); syncStylePanel(); render(); scheduleSave();
}

function pointsFromMapping(parsed, mapping){
  const {columns, rows}=parsed;
  const attrCols = columns.filter(c=>mapping[c]==="attr");
  const labelCol = columns.find(c=>mapping[c]==="label");
  const lonCol = columns.find(c=>mapping[c]==="lon");
  const latCol = columns.find(c=>mapping[c]==="lat");
  const out=[]; let bad=0;
  for(const row of rows){
    try{
      const lon=parseCoordinate(row[lonCol], "longitude");
      const lat=parseCoordinate(row[latCol], "latitude");
      const attr={}; attrCols.forEach(c=>attr[c]=row[c]);
      out.push({lon,lat,label:labelCol?row[labelCol]:null,_attr:attr});
    }catch(e){ bad++; }
  }
  return {points:out, attrCols, bad};
}

/* ---------------- UI: datasets panel ---------------- */
function selectedDataset(){ return datasets.find(d=>d.id===selId)||null; }
function renderDatasetList(){
  const box=$("#dslist");
  if(!datasets.length){ box.innerHTML='<div id="dsempty">No data yet. Add a CSV, paste a table, or load a sample.</div>'; }
  else{
    box.innerHTML="";
    for(const ds of datasets){
      const res=resolveGroups(ds);
      const sw = res.groups[0] ? res.groups[0].style.color : "#888";
      const row=document.createElement("div");
      row.className="ds"+(ds.id===selId?" sel":"");
      row.innerHTML=`<input type="checkbox" class="vis" ${ds.visible?"checked":""}>
        <span class="sw" style="background:${sw}"></span>
        <span class="nm">${escapeHtml(ds.name)}</span>
        <span class="ct">${ds.rows.length}</span>`;
      row.querySelector(".vis").addEventListener("click",e=>{ e.stopPropagation();
        ds.visible=e.target.checked; render(); });
      row.addEventListener("click",()=>{ selId=ds.id; syncStylePanel(); renderDatasetList(); });
      box.appendChild(row);
    }
  }
  // Every dataset can be edited: manual sets reopen the coordinate editor,
  // imported ones reopen their table (as CSV text) and column mapping.
  $("#btnEdit").disabled = !selectedDataset();
  $("#btnRemove").disabled = !selectedDataset();
}
function escapeHtml(s){ return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

// Reconstruct an editable CSV table for an imported dataset. Prefer the raw
// table it was created from (kept in ._import so every original column and
// value survives a round-trip); fall back to rebuilding one from the parsed
// points if that is missing (e.g. an older saved project).
function csvCell(v){ v = v==null ? "" : String(v);
  return /[",\n\r]/.test(v) ? '"'+v.replace(/"/g,'""')+'"' : v; }
function parsedToCsv(parsed){
  const cols=parsed.columns;
  const lines=[cols.map(csvCell).join(",")];
  for(const r of parsed.rows) lines.push(cols.map(c=>csvCell(r[c])).join(","));
  return lines.join("\n");
}
function datasetToParsed(ds){
  if(ds._import && ds._import.columns && ds._import.columns.length)
    return {columns:ds._import.columns, rows:ds._import.rows,
            mapping:ds._import.mapping||null};
  const attr=[...ds.columns];
  const hasLabel=ds.rows.some(r=>r.label!=null && r.label!=="");
  const columns=["Latitude","Longitude"].concat(attr).concat(hasLabel?["Label"]:[]);
  const rows=ds.rows.map(r=>{ const o={Latitude:r.lat, Longitude:r.lon};
    attr.forEach(c=>o[c]=r._attr?(r._attr[c]??""):""); if(hasLabel) o.Label=r.label??"";
    return o; });
  const mapping={}; columns.forEach(c=>mapping[c]="attr");
  mapping.Latitude="lat"; mapping.Longitude="lon"; if(hasLabel) mapping.Label="label";
  return {columns, rows, mapping};
}

/* ---------------- UI: style panel ---------------- */
function fillSelect(sel, values, current){
  sel.innerHTML=""; for(const v of values){ const o=document.createElement("option");
    o.value=v.value!==undefined?v.value:v; o.textContent=v.label!==undefined?v.label:v; sel.appendChild(o); }
  if(current!==undefined) sel.value=current;
}
function syncStylePanel(){
  const ds=selectedDataset();
  if(!ds){ $("#styleControls").style.display="none"; $("#styleFor").textContent="Select a dataset to style it."; return; }
  $("#styleControls").style.display="block";
  $("#styleFor").innerHTML="Styling <b>"+escapeHtml(ds.name)+"</b>";
  const colOpts=[{value:"",label:"None"}].concat(ds.columns.map(c=>({value:c,label:c})));
  fillSelect($("#groupBy"), colOpts, ds.groupBy||"");
  fillSelect($("#colorBy"), colOpts, ds.colorBy||"");
  fillSelect($("#symbolBy"), colOpts, ds.symbolBy||"");
  $("#varySymbols").checked=ds.varySymbols;
  fillSelect($("#baseMarker"), MARKERS, ds.base.marker);
  $("#baseColor").value=ds.base.color;
  $("#sizeRange").value=ds.base.size; $("#sizeVal").textContent=ds.base.size;
  $("#opacityRange").value=ds.opacity; $("#opacityVal").textContent=Number(ds.opacity).toFixed(2);
  renderGroupOverrides(ds);
}
function renderGroupOverrides(ds){
  const box=$("#groupList");
  const res=resolveGroups(ds);
  if(res.mode==="attr" || (res.groups.length<=1 && !ds.groupBy)){
    box.innerHTML='<span class="muted">Group the data to fine-tune each entry.</span>'; return;
  }
  box.innerHTML="";
  res.groups.forEach(g=>{
    const row=document.createElement("div"); row.className="row wrap";
    row.style.margin="6px 0";
    const c=document.createElement("input"); c.type="color"; c.value=g.style.color;
    c.addEventListener("input",()=>{ setOverride(ds,g.label,{color:c.value}); render(); renderDatasetList(); });
    const m=document.createElement("select"); m.style.flex="1 1 auto";
    fillSelect(m, MARKERS, g.style.marker);
    m.addEventListener("change",()=>{ setOverride(ds,g.label,{marker:m.value}); render(); });
    const sz=document.createElement("input"); sz.type="number"; sz.min="6"; sz.max="200"; sz.step="2";
    sz.value=g.style.size; sz.title="Point size"; sz.style.cssText="width:62px;flex:0 0 auto";
    sz.addEventListener("input",()=>{ setOverride(ds,g.label,{size:Math.max(6,Math.min(200,+sz.value||30))}); render(); });
    const lbl=document.createElement("span"); lbl.className="nm"; lbl.style.cssText="flex:1 1 100%;font-size:12px;color:var(--muted)";
    lbl.textContent=g.label;
    row.appendChild(c); row.appendChild(m); row.appendChild(sz); row.appendChild(lbl);
    box.appendChild(row);
  });
}
function setOverride(ds,label,patch){ ds.overrides[label]={...(ds.overrides[label]||{}),...patch}; }

