/* ---------------- rendering ---------------- */
const svg = $("#map");
function el(tag, attrs){ const e=document.createElementNS(svgNS,tag);
  if(attrs) for(const k in attrs) e.setAttribute(k, attrs[k]); return e; }
let sceneSize={w:0,h:0};

function render(){
  const stage=$("#stage");
  const W=stage.clientWidth, H=stage.clientHeight;
  sceneSize={w:W,h:H};
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  svg.setAttribute("width",W); svg.setAttribute("height",H);

  const proj = buildProjection(W,H);
  currentProjection = proj;
  const path = d3.geoPath(proj);
  const rect = drawRect(W,H);
  frameRect = rect;
  const [[rx0,ry0],[rx1,ry1]] = rect;
  const rw=rx1-rx0, rh=ry1-ry0;
  const useRect = silhouetteIsRect();
  const sphereD = useRect ? "" : (path({type:"Sphere"})||"");

  // background (mat)
  svg.appendChild(el("rect",{x:0,y:0,width:W,height:H,fill:opts.matColor}));

  // clip map content to the map rectangle
  const defs=el("defs"); const cp=el("clipPath",{id:"frameClip"});
  cp.appendChild(el("rect",{x:rx0,y:ry0,width:rw,height:rh}));
  defs.appendChild(cp); svg.appendChild(defs);
  const content=el("g",{"clip-path":"url(#frameClip)"}); svg.appendChild(content);
  // map layers live inside a viewport group so scroll-zoom / drag-pan can transform them
  const viewport=el("g",{id:"viewport",transform:viewTransform()}); content.appendChild(viewport);

  // ocean / earth silhouette
  const oceanFill = OCEAN_COLORS[opts.ocean] || "#ffffff";
  viewport.appendChild(useRect
    ? el("rect",{x:rx0,y:ry0,width:rw,height:rh,fill:oceanFill,stroke:"none"})
    : el("path",{d:sphereD, fill:oceanFill, stroke:"none"}));

  // graticule
  if(opts.graticule>0){
    const g=d3.geoGraticule().step([opts.graticule,opts.graticule]);
    viewport.appendChild(el("path",{d:path(g())||"", fill:"none", stroke:"#9aa3ac",
      "stroke-width":0.5, "stroke-opacity":0.7}));
  }
  // land
  if(opts.showLand){
    viewport.appendChild(el("path",{d:path(LAND)||"", fill:opts.landColor, stroke:"none"}));
  }
  const lw=opts.lineWidth;
  // borders
  if(opts.showBorders){
    viewport.appendChild(el("path",{d:path(BORDERS)||"", fill:"none", stroke:"#000000",
      "stroke-width":0.55*lw, "stroke-opacity":0.85, "stroke-linejoin":"round"}));
  }
  // coastline
  if(opts.showCoast){
    viewport.appendChild(el("path",{d:path(LAND_MESH)||"", fill:"none", stroke:"#333333",
      "stroke-width":0.7*lw, "stroke-linejoin":"round"}));
  }

  // points
  const ptsG=el("g"); viewport.appendChild(ptsG);
  const labelsG=el("g"); viewport.appendChild(labelsG);
  const legendEntries=[]; // {label, style, kind}
  const attrLegends=[];

  for(const ds of datasets){
    if(!ds.visible) continue;
    const res=resolveGroups(ds);
    for(const grp of res.groups){
      for(const r of grp.rows){
        if(currentProjDef().globe &&
           d3.geoDistance([r.lon,r.lat],[opts.centerLon,opts.centerLat])>Math.PI/2) continue;
        const xy=proj([r.lon, r.lat]);
        if(!xy || !isFinite(xy[0]) || !isFinite(xy[1])) continue;
        const r_=sizePx(grp.style.size)*1;
        const p=el("path",{d:markerPath(grp.style.marker,r_),
          transform:`translate(${xy[0].toFixed(2)},${xy[1].toFixed(2)})`});
        if(isOpen(grp.style.marker)){ p.setAttribute("fill","none");
          p.setAttribute("stroke",grp.style.color); p.setAttribute("stroke-width",Math.max(1.1,r_*0.22)); }
        else { p.setAttribute("fill",grp.style.color); p.setAttribute("stroke","none"); }
        p.setAttribute("fill-opacity", ds.opacity ?? 1);
        if(isOpen(grp.style.marker)) p.setAttribute("stroke-opacity", ds.opacity ?? 1);
        ptsG.appendChild(p);
        if(opts.labels && r.label){
          const t=el("text",{x:(xy[0]+r_+2).toFixed(2), y:(xy[1]+3).toFixed(2),
            "font-family":"sans-serif","font-size":10,fill:"#222"});
          t.textContent=r.label; labelsG.appendChild(t);
        }
      }
    }
    // legend building
    if(res.mode==="attr"){
      attrLegends.push({ds,res});
    } else {
      for(const grp of res.groups) legendEntries.push({label:grp.label, style:grp.style});
    }
  }

  // frame outline (unclipped, crisp)
  svg.appendChild(useRect
    ? el("rect",{x:rx0,y:ry0,width:rw,height:rh,fill:"none",stroke:"#5a6068","stroke-width":1})
    : el("path",{d:sphereD, fill:"none", stroke:"#5a6068","stroke-width":1}));

  // title
  if(opts.title){
    const t=el("text",{x:W/2, y:26, "text-anchor":"middle","font-family":"sans-serif",
      "font-size":19,"font-weight":700,fill:"#1d2127"});
    t.textContent=opts.title; svg.appendChild(t);
  }
  // compass
  if(opts.compass) drawCompass(svg, drawRect(W,H));

  // legend
  if(opts.legShow && (legendEntries.length || attrLegends.length)){
    drawLegend(svg, W, H, legendEntries, attrLegends);
  }

  $("#emptyHint").style.display = datasets.some(d=>d.visible && d.rows.length) ? "none":"block";
  updateStagebar();
  scheduleSave();
}

function drawCompass(svg, rect){
  const [[x0,y0],[x1]] = rect;
  const cx=x1-26, cy=y0+34;
  const g=el("g");
  g.appendChild(el("line",{x1:cx,y1:cy+16,x2:cx,y2:cy-14,stroke:"#1a1a1a","stroke-width":1.6}));
  g.appendChild(el("path",{d:poly([[cx,cy-20],[cx-4,cy-11],[cx+4,cy-11]]),fill:"#1a1a1a"}));
  const t=el("text",{x:cx,y:cy-24,"text-anchor":"middle","font-family":"sans-serif",
    "font-size":13,"font-weight":700,fill:"#1a1a1a"}); t.textContent="N";
  g.appendChild(t); svg.appendChild(g);
}

function legendItems(entries, attrLegends){
  // returns array of sections: {title, rows:[{label, style, symbolOnly, colorOnly}]}
  const sections=[];
  if(entries.length){
    let title=opts.legTitle;
    if(!title){ const ds=selectedDataset(); title = (ds&&ds.groupBy)||""; }
    sections.push({title, rows:entries.map(e=>({label:e.label, style:e.style}))});
  }
  for(const {ds,res} of attrLegends){
    if(Object.keys(res.colorMap).length){
      sections.push({title:res.colorKey||"Colour", rows:Object.entries(res.colorMap).map(([v,c])=>
        ({label:v||"(blank)", style:{color:c,marker:"Circle",size:ds.base.size}, colorOnly:true}))});
    }
    if(Object.keys(res.symbolMap).length){
      sections.push({title:res.symbolKey||"Symbol", rows:Object.entries(res.symbolMap).map(([v,m])=>
        ({label:v||"(blank)", style:{color:"#555",marker:m,size:ds.base.size}, symbolOnly:true}))});
    }
  }
  return sections;
}

function drawLegend(svg, W, H, entries, attrLegends){
  const sections=legendItems(entries, attrLegends);
  if(!sections.length) return;
  const fs=opts.legFont, scale=opts.legScale, cols=Math.max(1,opts.legCols);
  const pad=9, rowH=fs*1.55, mr=Math.min(fs*0.7*scale, 13), swW=fs*1.7*scale;
  const g=el("g"); g.style.cursor="move";
  // measure
  const measure=el("text",{"font-family":"sans-serif","font-size":fs,visibility:"hidden"});
  svg.appendChild(measure);
  const textW=s=>{ measure.textContent=s; return measure.getComputedTextLength(); };

  let maxLabel=0; let totalRows=0;
  const flat=[];
  for(const sec of sections){
    if(sec.title){ flat.push({type:"title",text:sec.title}); }
    for(const r of sec.rows){ flat.push({type:"row",...r}); maxLabel=Math.max(maxLabel,textW(r.label)); totalRows++; }
    flat.push({type:"gap"});
  }
  // layout in columns
  const perCol=Math.ceil(flat.length/cols);
  const colW=swW+8+maxLabel+16;
  let maxColRows=0;
  const colItems=[];
  for(let c=0;c<cols;c++){ colItems.push(flat.slice(c*perCol,(c+1)*perCol)); maxColRows=Math.max(maxColRows,colItems[c].length); }
  const boxW=pad*2 + cols*colW;
  const titleExtra = sections.filter(s=>s.title).length;
  const boxH=pad*2 + maxColRows*rowH;

  // position
  let bx,by;
  if(legendDrag){ bx=legendDrag.x*W; by=legendDrag.y*H; }
  else {
    const m=14;
    bx = opts.legPos.endsWith("r") ? W-boxW-m : m;
    by = opts.legPos.startsWith("t") ? m+ (opts.title?30:0) : H-boxH-m;
  }
  bx=Math.max(2,Math.min(bx,W-boxW-2)); by=Math.max(2,Math.min(by,H-boxH-2));

  if(opts.legFrame){
    g.appendChild(el("rect",{x:bx,y:by,width:boxW,height:boxH,rx:6,
      fill:"rgba(255,255,255,0.92)",stroke:"#c7ccd2","stroke-width":1}));
  } else {
    g.appendChild(el("rect",{x:bx,y:by,width:boxW,height:boxH,rx:6,fill:"rgba(255,255,255,0.0)"}));
  }
  for(let c=0;c<cols;c++){
    let yy=by+pad+rowH*0.5;
    const cx0=bx+pad+c*colW;
    for(const item of colItems[c]){
      if(item.type==="title"){
        const t=el("text",{x:cx0, y:yy+fs*0.34,"font-family":"sans-serif","font-size":fs*1.02,
          "font-weight":opts.legTitleBold?700:400,fill:"#1d2127"});
        if(opts.legTitleItalic) t.setAttribute("font-style","italic");
        if(opts.legTitleUnderline) t.setAttribute("text-decoration","underline");
        t.textContent=item.text; g.appendChild(t);
        yy+=rowH;
      } else if(item.type==="row"){
        const mx=cx0+swW/2, my=yy;
        const r_=Math.min(sizePx(item.style.size)*scale, fs*0.8*scale);
        const rr=Math.max(3.2, r_);
        const p=el("path",{d:markerPath(item.style.marker,rr),
          transform:`translate(${mx.toFixed(2)},${my.toFixed(2)})`});
        if(isOpen(item.style.marker)){ p.setAttribute("fill","none");
          p.setAttribute("stroke",item.style.color); p.setAttribute("stroke-width",Math.max(1,rr*0.24)); }
        else { p.setAttribute("fill",item.style.color); p.setAttribute("stroke","none"); }
        g.appendChild(p);
        const t=el("text",{x:cx0+swW+8, y:my+fs*0.34,"font-family":"sans-serif","font-size":fs,fill:"#22262c",
          "font-weight":opts.legLabelBold?700:400});
        if(opts.legLabelItalic) t.setAttribute("font-style","italic");
        if(opts.legLabelUnderline) t.setAttribute("text-decoration","underline");
        t.textContent=item.label; g.appendChild(t);
        yy+=rowH;
      } else { yy+=rowH*0.4; }
    }
  }
  svg.removeChild(measure);
  // drag
  g.style.cursor="move";
  g.addEventListener("mousedown",ev=>{
    ev.preventDefault(); ev.stopPropagation(); // don't also start a map pan
    const startX=ev.clientX, startY=ev.clientY, ox=bx, oy=by;
    function mv(e){ legendDrag={x:(ox+(e.clientX-startX))/W, y:(oy+(e.clientY-startY))/H}; render(); }
    function up(){ window.removeEventListener("mousemove",mv); window.removeEventListener("mouseup",up); }
    window.addEventListener("mousemove",mv); window.addEventListener("mouseup",up);
  });
  g.addEventListener("dblclick",ev=>{ ev.stopPropagation(); legendDrag=null; render(); });
  svg.appendChild(g);
}

function updateStagebar(){
  const n=datasets.reduce((a,d)=>a+(d.visible?d.rows.length:0),0);
  const shown=datasets.filter(d=>d.visible).length;
  $("#stagebar").textContent = n ? `${n} point${n!==1?"s":""} · ${shown} dataset${shown!==1?"s":""} · ${opts.projection}` : opts.projection;
}

