/* ---------------- events ---------------- */
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
  rd.onload=()=>startMapping(parseDelimited(rd.result), f.name.replace(/\.[^.]+$/,""));
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
  startMapping(parsed, ds?ds.name:"Pasted data", ds?editId:undefined);
});
$$("[data-sample]").forEach(b=>b.addEventListener("click",()=>{
  const s=SAMPLES[b.dataset.sample];
  const parsed=parseDelimited(s.text);
  const mapping=autoMapping(parsed.columns);
  addFromMapping(parsed, mapping, s.name, s.marker, s.groupBy);
}));
$("#btnClear").addEventListener("click",()=>{ datasets=[]; selId=null; renderDatasetList(); syncStylePanel(); render(); });
$("#btnRemove").addEventListener("click",()=>{ const ds=selectedDataset(); if(!ds) return;
  datasets=datasets.filter(d=>d.id!==ds.id); selId=datasets[0]?datasets[0].id:null;
  renderDatasetList(); syncStylePanel(); render(); });

// column mapping
// editingId: manual dataset being edited (manual modal).
// mapEditingId: imported dataset being edited (mapping modal updates in place).
// pasteEditingId: imported dataset whose table is being re-edited (paste modal).
let pendingParsed=null, editingId=null, mapEditingId=null, pasteEditingId=null;
function autoMapping(columns){
  const map={};
  for(const c of columns){
    if(/^(lon|long|longitude|x|lng)$/i.test(c)) map[c]="lon";
    else if(/^(lat|latitude|y)$/i.test(c)) map[c]="lat";
    else map[c]="attr";
  }
  return map;
}
function startMapping(parsed, name, editId){
  if(!parsed.columns.length){ alert("No rows found in that file."); return; }
  pendingParsed=parsed;
  mapEditingId = editId!=null ? editId : null;
  const editing = mapEditingId!=null;
  $("#mapName").value=name||"Dataset";
  const auto=autoMapping(parsed.columns);
  // When re-editing, start from the mapping the dataset was built with so a
  // column the user already assigned keeps its role across the round-trip.
  const prior = editing ? ((datasets.find(d=>d.id===mapEditingId)||{})._import||{}).mapping : null;
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
  $("#mapErr").textContent="";
  $("#mapModalTitle").textContent = editing ? "Edit dataset" : "Map columns";
  $("#mapOk").textContent = editing ? "Save changes" : "Add dataset";
  openModal("mapModal");
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
function addFromMapping(parsed, mapping, name, baseMarker, groupBy){
  const {points, attrCols, bad}=pointsFromMapping(parsed, mapping);
  if(!points.length){ alert("No valid coordinates could be read from that data."); return false; }
  const ds=makeDataset(name, attrCols, points);
  if(baseMarker) ds.base.marker=baseMarker;
  ds.groupBy = groupBy || attrCols[0] || null;
  ds._import={columns:parsed.columns, rows:parsed.rows, mapping:{...mapping}};
  datasets.push(ds); selId=ds.id;
  renderDatasetList(); syncStylePanel(); render(); scheduleSave();
  if(bad){ flashStage(`${bad} row${bad!==1?"s":""} skipped (unreadable coordinates).`); }
  return true;
}
// Re-apply an edited table/mapping to an existing dataset, keeping its styling
// (base marker, colours, overrides, opacity, visibility) intact; only drop
// group/colour/symbol choices whose column no longer exists.
function updateFromMapping(id, parsed, mapping, name){
  const ds=datasets.find(d=>d.id===id); if(!ds) return true;
  const {points, attrCols, bad}=pointsFromMapping(parsed, mapping);
  if(!points.length){ alert("No valid coordinates could be read from that data."); return false; }
  ds.name=name; ds.columns=attrCols; ds.rows=points;
  ds._import={columns:parsed.columns, rows:parsed.rows, mapping:{...mapping}};
  if(ds.groupBy && !attrCols.includes(ds.groupBy)) ds.groupBy=attrCols[0]||null;
  if(ds.colorBy && !attrCols.includes(ds.colorBy)) ds.colorBy=null;
  if(ds.symbolBy && !attrCols.includes(ds.symbolBy)) ds.symbolBy=null;
  selId=ds.id;
  renderDatasetList(); syncStylePanel(); render(); scheduleSave();
  if(bad){ flashStage(`${bad} row${bad!==1?"s":""} skipped (unreadable coordinates).`); }
  return true;
}
function flashStage(msg){ $("#stagebar").textContent=msg;
  setTimeout(()=>updateStagebar(),3000); }

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
  const lines=$("#mText").value.split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
  if(!lines.length){ $("#mErr").textContent="Enter at least one coordinate line."; return; }
  const points=[]; let bad=0;
  for(const line of lines){
    const parts=line.split(/\s*,\s*/);
    if(parts.length<2){ bad++; continue; }
    try{
      const a=parts[0], b=parts[1];
      const lat = order==="latlon" ? parseCoordinate(a,"latitude") : parseCoordinate(b,"latitude");
      const lon = order==="latlon" ? parseCoordinate(b,"longitude") : parseCoordinate(a,"longitude");
      const label = parts.slice(2).join(", ")||null;
      points.push({lon,lat,label,_attr:{Set:legend}});
    }catch(e){ bad++; }
  }
  if(!points.length){ $("#mErr").textContent="No readable coordinates. Use e.g. 38, -100."; return; }
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
  }
  closeModal("manualModal"); renderDatasetList(); syncStylePanel(); render();
  if(bad) flashStage(`${bad} line${bad!==1?"s":""} skipped.`);
});
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
  ds.overrides={}; renderGroupOverrides(ds); render(); renderDatasetList(); });
$("#colorBy").addEventListener("change",e=>{ const ds=selectedDataset(); ds.colorBy=e.target.value||null;
  ds.overrides={}; render(); renderDatasetList(); });
$("#symbolBy").addEventListener("change",e=>{ const ds=selectedDataset(); ds.symbolBy=e.target.value||null;
  ds.overrides={}; renderGroupOverrides(ds); render(); });
$("#varySymbols").addEventListener("change",e=>{ const ds=selectedDataset(); ds.varySymbols=e.target.checked;
  ds.overrides={}; render(); });
$("#baseMarker").addEventListener("change",e=>{ const ds=selectedDataset(); ds.base.marker=e.target.value; render(); });
$("#baseColor").addEventListener("input",e=>{ const ds=selectedDataset(); ds.base.color=e.target.value; render(); renderDatasetList(); });
$("#sizeRange").addEventListener("input",e=>{ const ds=selectedDataset(); ds.base.size=+e.target.value;
  $("#sizeVal").textContent=e.target.value; render(); });
$("#opacityRange").addEventListener("input",e=>{ const ds=selectedDataset(); ds.opacity=+e.target.value;
  $("#opacityVal").textContent=(+e.target.value).toFixed(2); render(); });
$("#resetStyles").addEventListener("click",()=>{ const ds=selectedDataset(); if(!ds) return;
  ds.overrides={}; renderGroupOverrides(ds); render(); renderDatasetList(); });

// map controls
fillSelect($("#extent"), Object.keys(CONTINENT_EXTENTS), "World");
fillSelect($("#projection"), Object.keys(PROJ_DEFS), "Equirectangular");
$("#extent").addEventListener("change",e=>{ opts.extent=e.target.value; render(); });
$("#projection").addEventListener("change",e=>{ opts.projection=e.target.value; syncOrigin(); render(); });
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
  opts.orientation=b.dataset.orient; setSeg("#orientSeg",b); render(); });
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
$("#showLabels").addEventListener("change",e=>{ opts.labels=e.target.checked; render(); });
$("#matColor").addEventListener("input",e=>{ opts.matColor=e.target.value; render(); });
$("#lineWidth").addEventListener("input",e=>{ opts.lineWidth=+e.target.value; $("#lwVal").textContent=(+e.target.value).toFixed(2); render(); });

// Legend controls, wired from the LEGEND_CONTROLS table so a new setting is
// one row there rather than another near-identical line here.
for(const [id,kind,fallback] of LEGEND_CONTROLS){
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
    render();
  });
}

// export
$("#btnSvg").addEventListener("click",()=>{
  const s=new XMLSerializer().serializeToString(svg);
  const blob=new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n'+s],{type:"image/svg+xml"});
  downloadBlob(blob, "minimappr.svg");
});
$("#btnPng").addEventListener("click",()=>{
  const outW=Math.max(600,Math.min(8000,parseInt($("#pngWidth").value)||2000));
  const W=sceneSize.w, H=sceneSize.h, outH=Math.round(outW*H/W);
  const s=new XMLSerializer().serializeToString(svg);
  const img=new Image();
  const url="data:image/svg+xml;charset=utf-8,"+encodeURIComponent(s);
  img.onload=()=>{
    const cv=document.createElement("canvas"); cv.width=outW; cv.height=outH;
    const ctx=cv.getContext("2d"); ctx.fillStyle=opts.matColor; ctx.fillRect(0,0,outW,outH);
    ctx.drawImage(img,0,0,outW,outH);
    cv.toBlob(b=>downloadBlob(b,"minimappr.png"),"image/png");
  };
  img.onerror=()=>alert("PNG export failed in this browser. Try the SVG export instead.");
  img.src=url;
});
function downloadBlob(blob,name){ const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download=name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000); }

