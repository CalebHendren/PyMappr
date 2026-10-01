/* events */
function openModal(id){ $("#"+id).classList.add("on"); }
function closeModal(id){ $("#"+id).classList.remove("on"); }
$$("[data-close]").forEach(b=>b.addEventListener("click",()=>closeModal(b.dataset.close)));
$$(".modal-bg").forEach(bg=>bg.addEventListener("mousedown",e=>{ if(e.target===bg) bg.classList.remove("on"); }));
// Cancelling an edit dialog drops the "editing this dataset" intent so the
// next add starts clean.
["#pasteModal","#mapModal"].forEach(sel=>$(sel).addEventListener("mousedown",e=>{
  if(e.target.matches(".modal-bg")){ pasteEditingId=null; mapEditingId=null; }}));
$$('[data-close="pasteModal"],[data-close="mapModal"]').forEach(b=>
  b.addEventListener("click",()=>{ pasteEditingId=null; mapEditingId=null; }));
$("#aboutBtn").addEventListener("click",e=>{ e.preventDefault(); openModal("aboutModal"); });
// Modals were mouse-only: backdrop click or the Close button. Escape closes the
// last-opened one, matching what the backdrop click already does.
document.addEventListener("keydown",e=>{
  if(e.key!=="Escape") return;
  const open=$$(".modal-bg.on");
  if(!open.length) return;
  const top=open[open.length-1];
  top.classList.remove("on");
  // The notice can sit over the mapping dialog; closing it keeps the edit.
  if(top.id==="pasteModal" || top.id==="mapModal"){ pasteEditingId=null; mapEditingId=null; }
});

// tabs
$$("#tabs button").forEach(b=>b.addEventListener("click",()=>{
  $$("#tabs button").forEach(x=>x.classList.remove("active")); b.classList.add("active");
  $$(".tabpage").forEach(p=>p.classList.toggle("active", p.dataset.page===b.dataset.tab));
}));

// data buttons
$("#btnCsv").addEventListener("click",()=>$("#fileInput").click());
$("#fileInput").addEventListener("change",e=>{
  const f=e.target.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=()=>startMapping(rd.result, f.name.replace(/\.[^.]+$/,""));
  rd.readAsText(f); e.target.value="";
});
$("#btnPaste").addEventListener("click",()=>{ pasteEditingId=null;
  $("#pText").value=""; $("#pErr").textContent="";
  $("#pasteModalTitle").textContent="Paste a table"; $("#pOk").textContent="Continue →";
  openModal("pasteModal"); });
$("#pOk").addEventListener("click",()=>{
  const txt=$("#pText").value.trim();
  if(!txt){ $("#pErr").textContent="Paste some rows first."; return; }
  const parsed=parseDelimited(txt);
  if(parsed.columns.length<2){ $("#pErr").textContent="Could not find columns. Check the delimiter."; return; }
  closeModal("pasteModal");
  const editId=pasteEditingId; pasteEditingId=null;
  const ds = editId!=null ? datasets.find(d=>d.id===editId) : null;
  startMapping(txt, ds?ds.name:"Pasted data", ds?editId:undefined);
});
$$("[data-sample]").forEach(b=>b.addEventListener("click",()=>{
  const s=SAMPLES[b.dataset.sample];
  const parsed=parseDelimited(s.text);
  addFromMapping(parsed, guessMapping(parsed), s.name, s.marker, s.groupBy);
}));
// Removing data cannot be undone, so both ask first, as PyMappr does.
$("#btnClear").addEventListener("click",()=>{
  if(datasets.length && !confirm(`Remove all ${datasets.length} dataset${datasets.length!==1?"s":""}?`)) return;
  datasets=[]; selId=null; renderDatasetList(); syncStylePanel(); render(); });
$("#btnRemove").addEventListener("click",()=>{ const ds=selectedDataset(); if(!ds) return;
  if(!confirm(`Remove the dataset “${ds.name}”?`)) return;
  datasets=datasets.filter(d=>d.id!==ds.id); selId=datasets[0]?datasets[0].id:null;
  renderDatasetList(); syncStylePanel(); render(); });

// combine columns
function combineChoice(){
  return {parts:$$("#cCols input:checked").map(i=>i.value), sep:$("#cSep").value};
}
function updateCombinePreview(){
  const ds=selectedDataset(); if(!ds) return;
  const {parts,sep}=combineChoice();
  const first=ds.rows[0];
  $("#cPreview").textContent = parts.length<2 ? "Tick at least two columns."
    : first ? "First row: "+combinedValue(first._attr, parts, sep) : "";
  $("#cOk").disabled = parts.length<2;
}
$("#btnCombine").addEventListener("click",()=>{
  const ds=selectedDataset(); if(!ds || ds.columns.length<2) return;
  const box=$("#cCols"); box.innerHTML="";
  ds.columns.forEach((c,i)=>{
    const lab=document.createElement("label"); lab.className="check";
    const cb=document.createElement("input"); cb.type="checkbox"; cb.value=c;
    cb.checked = i>=ds.columns.length-2;   // the last two, as in PyMappr
    cb.addEventListener("change",updateCombinePreview);
    lab.appendChild(cb); lab.appendChild(document.createTextNode(" "+c)); box.appendChild(lab);
  });
  $("#cSep").value=" ";
  updateCombinePreview();
  openModal("combineModal");
});
$("#cSep").addEventListener("input",updateCombinePreview);
$("#cOk").addEventListener("click",()=>{
  const ds=selectedDataset(); if(!ds) return;
  const {parts,sep}=combineChoice();
  if(parts.length<2) return;
  const name=combinedName(ds.columns, parts, sep);
  ds.combined=(ds.combined||[]).concat([{name, parts, sep}]);
  applyCombined(ds);
  // Group by the new column; Symbol by would switch the legend to the
  // two-column key and hide the full names again.
  ds.groupBy=name; ds.symbolBy=null;
  closeModal("combineModal");
  renderDatasetList(); syncStylePanel(); render();
  flashStage(`Added the column “${name}” and grouped by it.`);
});

// column mapping
// editingId: manual dataset being edited (manual modal).
// mapEditingId: imported dataset being edited (mapping modal updates in place).
// pasteEditingId: imported dataset whose table is being re-edited (paste modal).
// pendingText: the raw table, kept so the header checkbox can re-read it.
let pendingParsed=null, pendingText="", editingId=null, mapEditingId=null, pasteEditingId=null;
function startMapping(text, name, editId){
  const parsed=parseDelimited(text);
  if(!parsed.columns.length){ alert("No rows found in that file."); return; }
  pendingText=text;
  mapEditingId = editId!=null ? editId : null;
  const editing = mapEditingId!=null;
  $("#mapName").value=name||"Dataset";
  $("#mapHeaders").checked=parsed.headers;
  fillMappingRows(parsed);
  $("#mapErr").textContent="";
  $("#mapModalTitle").textContent = editing ? "Edit dataset" : "Map columns";
  $("#mapOk").textContent = editing ? "Save changes" : "Add dataset";
  openModal("mapModal");
}
// Whether the first row names the columns is guessed on import; ticking the
// box either way re-reads the table, and the guesses start over.
$("#mapHeaders").addEventListener("change",e=>{
  fillMappingRows(parseDelimited(pendingText, e.target.checked));
});
function fillMappingRows(parsed){
  pendingParsed=parsed;
  const auto=guessMapping(parsed);
  // When re-editing, start from the mapping the dataset was built with so a
  // column the user already assigned keeps its role across the round-trip.
  const prior = mapEditingId!=null ? ((datasets.find(d=>d.id===mapEditingId)||{})._import||{}).mapping : null;
  const roleFor = c => (prior && prior[c]!=null) ? prior[c] : auto[c];
  const tbody=$("#mapRows"); tbody.innerHTML="";
  const roles=[["attr","Attribute"],["lon","Longitude"],["lat","Latitude"],["label","Label"],["ignore","Ignore"]];
  parsed.columns.forEach(c=>{
    const tr=document.createElement("tr");
    const samp=parsed.rows.slice(0,3).map(r=>r[c]).filter(v=>v!=="").join(", ");
    const sel=document.createElement("select");
    roles.forEach(([v,l])=>{ const o=document.createElement("option"); o.value=v; o.textContent=l; sel.appendChild(o); });
    sel.value=roleFor(c); sel.dataset.col=c;
    const td=document.createElement("td"); td.appendChild(sel);
    tr.innerHTML=`<td>${escapeHtml(c)}</td><td class="samp">${escapeHtml(samp)}</td>`;
    tr.appendChild(td); tbody.appendChild(tr);
  });
}
$("#mapOk").addEventListener("click",()=>{
  const mapping={};
  $$("#mapRows select").forEach(s=>mapping[s.dataset.col]=s.value);
  const roles=Object.values(mapping);
  if(roles.filter(r=>r==="lon").length!==1 || roles.filter(r=>r==="lat").length!==1){
    $("#mapErr").textContent="Pick exactly one Longitude and one Latitude column."; return;
  }
  const name=$("#mapName").value.trim()||"Dataset";
  if(mapEditingId!=null){
    if(!updateFromMapping(mapEditingId, pendingParsed, mapping, name)) return;
  } else {
    if(!addFromMapping(pendingParsed, mapping, name)) return;
  }
  mapEditingId=null;
  closeModal("mapModal");
});
// A failed import leaves the mapping dialog open under the notice, so the
// columns can be re-assigned straight away.
function addFromMapping(parsed, mapping, name, baseMarker, groupBy){
  const {points, attrCols, skipped}=pointsFromMapping(parsed, mapping);
  if(!reportSkipped(points.length, skipped)) return false;
  const ds=makeDataset(name, attrCols, points);
  if(baseMarker) ds.base.marker=baseMarker;
  ds.groupBy = groupBy || attrCols[0] || null;
  ds._import={columns:parsed.columns, rows:parsed.rows, mapping:{...mapping}};
  datasets.push(ds); selId=ds.id;
  renderDatasetList(); syncStylePanel(); zoomToData(); scheduleSave();
  return true;
}
// Re-apply an edited table/mapping to an existing dataset, keeping its styling
// (base marker, colours, overrides, opacity, visibility) and its combined
// columns intact; only drop group/colour/symbol choices whose column no
// longer exists.
function updateFromMapping(id, parsed, mapping, name){
  const ds=datasets.find(d=>d.id===id); if(!ds) return true;
  const {points, skipped}=pointsFromMapping(parsed, mapping);
  if(!reportSkipped(points.length, skipped)) return false;
  ds.name=name; ds.rows=points;
  ds._import={columns:parsed.columns, rows:parsed.rows, mapping:{...mapping}};
  applyCombined(ds);
  if(ds.groupBy && !ds.columns.includes(ds.groupBy)) ds.groupBy=ds.columns[0]||null;
  if(ds.colorBy && !ds.columns.includes(ds.colorBy)) ds.colorBy=null;
  if(ds.symbolBy && !ds.columns.includes(ds.symbolBy)) ds.symbolBy=null;
  selId=ds.id;
  renderDatasetList(); syncStylePanel(); render(); scheduleSave();
  return true;
}
// A message in the status line for three seconds. It outlives the render
// that usually follows it, which would otherwise wipe it at once.
let flash=null, flashTimer=0;
function flashStage(msg){
  flash={text:msg, until:Date.now()+3000};
  updateStagebar();
  clearTimeout(flashTimer); flashTimer=setTimeout(updateStagebar, 3000);
}

// manual entry
$("#btnManual").addEventListener("click",()=>{ editingId=null; fillSelect($("#mMarker"),MARKERS,"Circle");
  $("#mLegend").value=""; $("#mText").value=""; $("#mSize").value=30; $("#mColor").value="#d62728";
  $("#mOrder").value="latlon"; $("#mErr").textContent="";
  $("#manualModalTitle").textContent="Manual coordinate entry"; $("#mOk").textContent="Add points";
  openModal("manualModal"); });
$("#mOk").addEventListener("click",()=>{
  const legend=$("#mLegend").value.trim();
  if(!legend){ $("#mErr").textContent="Give the point set a legend name."; return; }
  const order=$("#mOrder").value;
  if(!$("#mText").value.trim()){ $("#mErr").textContent="Enter at least one coordinate line."; return; }
  const {points, skipped}=parseManualLines($("#mText").value, order, legend);
  if(!points.length){
    $("#mErr").textContent="No readable coordinates. Use e.g. 38, -100."
      + (skipped.length ? " ("+skipped[0]+")" : "");
    return;
  }
  const size=Math.max(6,Math.min(200,parseFloat($("#mSize").value)||30));
  const base={color:$("#mColor").value, marker:$("#mMarker").value, size};
  if(editingId){
    const ds=datasets.find(d=>d.id===editingId);
    ds.name=legend; ds.rows=points; ds.base=base;
    ds._manual={legend, text:$("#mText").value, order, base}; editingId=null;
  } else {
    const ds=makeDataset(legend, [], points, base);
    ds.groupBy=null; ds.source="manual";
    ds._manual={legend, text:$("#mText").value, order, base};
    datasets.push(ds); selId=ds.id;
    zoomToData();
  }
  closeModal("manualModal"); renderDatasetList(); syncStylePanel(); render();
  reportSkipped(points.length, skipped);
});
// One point per line: two coordinates separated by a comma, semicolon or
// tab, in the chosen order, then an optional label. Lines are numbered as
// typed, blank ones included. Mirrors data_loader.build_manual_dataset.
function parseManualLines(text, order, legend){
  const points=[], skipped=[];
  text.split(/\r?\n/).forEach((raw,i)=>{
    const line=raw.trim();
    if(!line) return;
    const parts=line.replace(/[;\t]/g,",").split(",").map(p=>p.trim()).filter(Boolean);
    if(parts.length<2){ skipped.push(`line ${i+1}: expected two coordinates, got "${line}"`); return; }
    try{
      const [a,b]=parts;
      let lat, lon;
      if(order==="latlon"){ lat=parseCoordinate(a,"latitude"); lon=parseCoordinate(b,"longitude"); }
      else { lon=parseCoordinate(a,"longitude"); lat=parseCoordinate(b,"latitude"); }
      points.push({lon,lat,label:parts.slice(2).join(", ")||null,_attr:{Set:legend}});
    }catch(e){ skipped.push(`line ${i+1}: ${e.message}`); }
  });
  return {points, skipped};
}
// click-to-place toggle
$("#btnPlace").addEventListener("click",()=>{
  placeMode=!placeMode;
  if(placeMode) placeDsId=null;   // re-resolve target on the next click
  $("#btnPlace").classList.toggle("on", placeMode);
  $("#placeHint").style.display = placeMode ? "block":"none";
  svg.style.cursor = placeMode ? "crosshair" : "";
});
$("#btnEdit").addEventListener("click",()=>{
  const ds=selectedDataset(); if(!ds) return;
  if(ds.source==="manual"){
    const m=ds._manual||{};
    fillSelect($("#mMarker"),MARKERS, ds.base.marker);
    $("#mLegend").value=ds.name; $("#mText").value=m.text||""; $("#mOrder").value=m.order||"latlon";
    $("#mSize").value=ds.base.size; $("#mColor").value=ds.base.color; $("#mErr").textContent="";
    $("#manualModalTitle").textContent="Edit points"; $("#mOk").textContent="Save changes";
    editingId=ds.id; openModal("manualModal");
  } else {
    // Imported data: reopen its table as editable CSV, then remap the columns.
    pasteEditingId=ds.id;
    $("#pText").value=parsedToCsv(datasetToParsed(ds)); $("#pErr").textContent="";
    $("#pasteModalTitle").textContent="Edit dataset"; $("#pOk").textContent="Continue →";
    openModal("pasteModal");
  }
});

// style controls
$("#groupBy").addEventListener("change",e=>{ const ds=selectedDataset(); ds.groupBy=e.target.value||null;
  ds.overrides={}; renderGroupOverrides(ds); render(); });
$("#colorBy").addEventListener("change",e=>{ const ds=selectedDataset(); ds.colorBy=e.target.value||null;
  ds.overrides={}; render(); });
$("#symbolBy").addEventListener("change",e=>{ const ds=selectedDataset(); ds.symbolBy=e.target.value||null;
  ds.overrides={}; renderGroupOverrides(ds); render(); });
$("#varySymbols").addEventListener("change",e=>{ const ds=selectedDataset(); ds.varySymbols=e.target.checked;
  ds.overrides={}; render(); });
// The palette is map-wide: clearing every dataset's overrides would throw
// away colours the user pinned, so only the auto-assigned styles change.
// White points vanish inside a white outline, so a palette with white in it
// brings a black outline along, as in PyMappr.
$("#paletteSel").addEventListener("change",e=>{
  opts.palette=e.target.value;
  if(palette().includes("#ffffff") && /^(#ffffff|white)$/i.test(opts.pointEdgeColor)){
    opts.pointEdgeColor="#000000"; $("#pointEdgeColor").value="#000000";
    flashStage("Point outline set to black so white points stay visible.");
  }
  render();
});
// One click for a journal figure: black and white points with black
// outlines and varied shapes, and a plain boxed legend with italic names.
// Rows restyled by hand keep their styling. Mirrors on_publication_style.
$("#btnPublication").addEventListener("click",()=>{
  opts.palette="Black & white";
  [opts.pointEdgeColor, opts.pointEdgeWidth]=PUBLICATION_POINT_EDGE;
  Object.assign(opts, PUBLICATION_LEGEND);
  // three shades alone cannot tell more than three groups apart
  for(const ds of datasets){ ds.opacity=1; ds.varySymbols=true; }
  opts.exportDpi=PUBLICATION_DPI;
  syncMapControls(); syncStylePanel(); render();
  flashStage(`Applied the publication style. Export below at ${PUBLICATION_DPI} DPI.`);
});
$("#baseMarker").addEventListener("change",e=>{ const ds=selectedDataset(); ds.base.marker=e.target.value; render(); });
$("#baseColor").addEventListener("input",e=>{ const ds=selectedDataset(); ds.base.color=e.target.value; render(); });
$("#sizeRange").addEventListener("input",e=>{ const ds=selectedDataset(); ds.base.size=+e.target.value;
  $("#sizeVal").textContent=e.target.value; render(); });
$("#opacityRange").addEventListener("input",e=>{ const ds=selectedDataset(); ds.opacity=+e.target.value;
  $("#opacityVal").textContent=(+e.target.value).toFixed(2); render(); });
$("#resetStyles").addEventListener("click",()=>{ const ds=selectedDataset(); if(!ds) return;
  ds.overrides={}; renderGroupOverrides(ds); render(); });

// filter bar
$("#filterCol").addEventListener("change",e=>{
  const ds=selectedDataset(); if(!ds) return;
  filter={dsId:ds.id, column:e.target.value||null, hidden:new Set()};
  renderFilterValues(ds); render();
});
function setAllFilterValues(show){
  const ds=selectedDataset(); if(!ds || !filter.column) return;
  filter.hidden = show ? new Set()
    : new Set(ds.rows.map(r=>r._attr[filter.column]??""));
  renderFilterValues(ds); render();
}
$("#filterAll").addEventListener("click",()=>setAllFilterValues(true));
$("#filterNone").addEventListener("click",()=>setAllFilterValues(false));
// A mouse wheel has no sideways motion, so it scrolls the value strip.
$("#filterVals").addEventListener("wheel",e=>{
  if(Math.abs(e.deltaY)<=Math.abs(e.deltaX)) return;
  e.preventDefault(); e.currentTarget.scrollLeft+=e.deltaY;
},{passive:false});

// map controls
fillSelect($("#extent"), Object.keys(CONTINENT_EXTENTS), "World");
fillSelect($("#projection"), Object.keys(PROJ_DEFS), "Equirectangular");
// A zoom is kept in screen terms, so it means nothing once the region, the
// projection or the orientation changes; each of those shows the whole map.
$("#extent").addEventListener("change",e=>{ opts.extent=e.target.value; view={k:1,x:0,y:0}; render(); });
$("#projection").addEventListener("change",e=>{ opts.projection=e.target.value; syncOrigin();
  view={k:1,x:0,y:0}; render(); });
function syncOrigin(reset=true){
  const pd=currentProjDef();
  const show = pd.globe||pd.lambert;
  $("#originRow").style.display = show?"block":"none";
  if(reset && show && pd.origin){ opts.centerLon=pd.origin[0]; opts.centerLat=pd.origin[1];
    $("#centerLon").value=pd.origin[0]; $("#centerLat").value=pd.origin[1]; }
  if(reset && pd.region && CONTINENT_EXTENTS[pd.region]){ opts.extent=pd.region; $("#extent").value=pd.region; }
}
$("#centerLon").addEventListener("input",e=>{ opts.centerLon=parseFloat(e.target.value)||0; render(); });
$("#centerLat").addEventListener("input",e=>{ opts.centerLat=parseFloat(e.target.value)||0; render(); });
$("#orientSeg").addEventListener("click",e=>{ const b=e.target.closest("button"); if(!b) return;
  opts.orientation=b.dataset.orient; setSeg("#orientSeg",b); view={k:1,x:0,y:0}; render(); });
$("#oceanSeg").addEventListener("click",e=>{ const b=e.target.closest("button"); if(!b) return;
  opts.ocean=b.dataset.ocean; setSeg("#oceanSeg",b); render(); });
$("#gratSeg").addEventListener("click",e=>{ const b=e.target.closest("button"); if(!b) return;
  opts.graticule=+b.dataset.grat; setSeg("#gratSeg",b); render(); });
function setSeg(sel,btn){ $$(sel+" button").forEach(x=>x.classList.remove("on")); btn.classList.add("on"); }
$("#showLand").addEventListener("change",e=>{ opts.showLand=e.target.checked; render(); });
$("#landColor").addEventListener("input",e=>{ opts.landColor=e.target.value; render(); });
$("#showBorders").addEventListener("change",e=>{ opts.showBorders=e.target.checked; render(); });
$("#showCoast").addEventListener("change",e=>{ opts.showCoast=e.target.checked; render(); });
$("#mapTitle").addEventListener("input",e=>{ opts.title=e.target.value; render(); });
$("#showCompass").addEventListener("change",e=>{ opts.compass=e.target.checked; render(); });
$("#showScaleBar").addEventListener("change",e=>{ opts.scaleBar=e.target.checked; render(); });
$("#pointEdgeColor").addEventListener("input",e=>{ opts.pointEdgeColor=e.target.value; render(); });
$("#pointEdgeWidth").addEventListener("input",e=>{ const n=parseFloat(e.target.value);
  opts.pointEdgeWidth=Number.isFinite(n) ? clamp(n,0,3) : 0; render(); });
$("#showLabels").addEventListener("change",e=>{ opts.labels=e.target.checked; render(); });
$("#matColor").addEventListener("input",e=>{ opts.matColor=e.target.value; render(); });
$("#lineWidth").addEventListener("input",e=>{ opts.lineWidth=+e.target.value; $("#lwVal").textContent=(+e.target.value).toFixed(2); render(); });

// Legend and map controls, wired from the LEGEND_CONTROLS and MAP_CONTROLS
// tables so a new setting is one row there rather than another
// near-identical line here.
for(const [id,kind,fallback] of [...LEGEND_CONTROLS, ...MAP_CONTROLS]){
  const node=$("#"+id);
  if(!node) continue;                       // control not on the page (yet)
  const event = kind==="bool"||node.tagName==="SELECT" ? "change" : "input";
  node.addEventListener(event, e=>{
    if(kind==="bool") opts[id]=e.target.checked;
    else if(kind==="num"){
      const n=parseFloat(e.target.value);
      opts[id]=Number.isFinite(n)?n:fallback;   // mid-edit "" and "-" are normal
    } else opts[id]=e.target.value;
    // Choosing a preset position discards any manual (dragged) placement.
    if(id==="legPos") legendDrag=null;
    if(id==="scalePos") opts.scaleAnchor=null;
    // Switching units keeps the print size, not the number.
    if(id==="exportUnit"){
      opts.exportWidth=Number((opts.exportWidth*(opts.exportUnit==="cm" ? 2.54 : 1/2.54)).toFixed(2));
      $("#exportWidth").value=opts.exportWidth;
    }
    render();
  });
}
$("#scaleReset").addEventListener("click",()=>{ opts.scaleAnchor=null; render(); });
// Controls that only apply in some states are greyed out in the others.
function syncControlStates(){
  $("#scaleFixed").disabled = opts.scaleLengthMode!=="fixed";
  $("#scaleReset").disabled = !opts.scaleAnchor;
  $("#exportDpi").disabled = opts.exportFormat==="svg";
  updateExportReadout();
}


