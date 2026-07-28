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
      // Counts belong on the row text here too - reading opts.legCounts only
      // in the attribute branch is what used to make "Show point counts" do
      // nothing at all in plain Group-by mode.
      const total=res.groups.reduce((a,g)=>a+g.rows.length,0);
      const sizes={};
      let rows=res.groups.map(grp=>{
        const label=legendLabel(grp.label, grp.rows.length, total);
        sizes[label]=grp.rows.length;
        return {label, style:grp.style};
      });
      const order=orderLabels(rows.map(r=>r.label), opts.legOrder, l=>sizes[l]||0);
      const rank={}; order.forEach((l,i)=>{ rank[l]=i; });
      rows=rows.sort((a,b)=>(rank[a.label]??0)-(rank[b.label]??0));
      const prefix=(datasets.filter(d=>d.visible).length>1 && opts.legDatasetPrefix)
        ? ds.name+": " : "";
      legendEntries.push({title:prefix+(ds.groupBy||ds.name||""), rows});
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
  for(const group of entries){
    // Group-mode datasets each get their own section, so several datasets on
    // one map stay tellable apart instead of merging into a single list.
    const title = opts.legSectionTitles ? (opts.legTitle || group.title || "") : "";
    const rows = group.rows.map(e=>({label:e.label, style:e.style}));
    if(rows.length) sections.push({title, rows});
  }
  const manyDatasets=datasets.filter(d=>d.visible).length>1;
  for(const {ds,res} of attrLegends){
    const prefix=(manyDatasets && opts.legDatasetPrefix) ? ds.name+": " : "";
    // Ordering by count needs the numbers even when they are not shown.
    const counts=(opts.legCounts||ordersByCount())
      ? legendCounts(ds.rows,res.colorKey,res.symbolKey) : null;
    const total=counts?counts["_total"]:0;
    const countOf=key=>(counts&&counts[key])||0;
    const lab=(v,key)=>legendLabel(v, counts?counts[key]:null, total);
    if(resolveNesting(ds.rows, res.colorKey, res.symbolKey, opts.legHierarchy)){
      // The two columns form a hierarchy, so list each symbol value under the
      // colour group it belongs to, drawn in the marker and colour it has on
      // the map. Two independent keys would imply colours x symbols
      // combinations when only `symbols` of them exist, and leave the reader
      // to work out which colour each symbol goes with by hunting the map.
      const owner=ownerMap(ds.rows, res.symbolKey, res.colorKey);
      const rows=[];
      // Every colour group is listed. MiniMappr has no filter, so the only
      // way a group ends up childless is forced nesting, where each symbol
      // is claimed by the first group it appears under - and dropping those
      // would take colours off the legend that are still drawn on the map.
      const parents=orderLabels(Object.keys(res.colorMap), opts.legOrder,
        v=>countOf("c "+v));
      for(const cv of parents){
        const color=res.colorMap[cv];
        const kids=orderLabels(
          Object.keys(res.symbolMap).filter(sv=>(owner[sv]??"")===cv),
          opts.legOrder, k=>countOf("p "+cv+" "+k));
        rows.push({label:lab(cv,"c "+cv), depth:0,
          style:groupSwatch(color, kids, res.symbolMap, ds.base.size)});
        for(const sv of kids) rows.push({label:lab(sv,"p "+cv+" "+sv), depth:1,
          style:{color, marker:res.symbolMap[sv], size:ds.base.size}});
      }
      if(rows.length) sections.push({title:sectionTitle(prefix,res.colorKey,res.symbolKey),
        rows, nested:true});
      continue;
    }
    // Genuinely crossed: a shape really does appear in every colour here, so
    // the neutral symbol swatches are honest and the two keys stay separate.
    if(Object.keys(res.colorMap).length){
      const values=orderLabels(Object.keys(res.colorMap), opts.legOrder, v=>countOf("c "+v));
      sections.push({title:sectionTitle(prefix,res.colorKey||"Colour"), rows:values.map(v=>
        ({label:lab(v,"c "+v), style:{color:res.colorMap[v],marker:"Circle",size:ds.base.size}, colorOnly:true}))});
    }
    if(Object.keys(res.symbolMap).length){
      const values=orderLabels(Object.keys(res.symbolMap), opts.legOrder, v=>countOf("s "+v));
      sections.push({title:sectionTitle(prefix,res.symbolKey||"Symbol"), rows:values.map(v=>
        ({label:lab(v,"s "+v), style:{color:opts.legSymbolColor,marker:res.symbolMap[v],size:ds.base.size}, symbolOnly:true}))});
    }
  }
  return sections;
}

// A nested key's group row swatch: a plain circle, the shape of its first
// child, or nothing at all.
function groupSwatch(color, kids, symbolMap, size){
  if(opts.legGroupSwatch==="none") return null;
  let marker="Circle";
  if(opts.legGroupSwatch==="child" && kids.length) marker=symbolMap[kids[0]]||"Circle";
  return {color, marker, size};
}

// A section's heading, or "" when headings are switched off. The dataset
// prefix rides on the heading, so with headings off it has nothing to attach
// to and goes too - a section titled "beetles: " would be nonsense.
function sectionTitle(prefix, ...parts){
  if(!opts.legSectionTitles) return "";
  return prefix + (parts.filter(Boolean).join(opts.legTitleSeparator)||"Key");
}

// Point counts for legend rows: by column value, and by "colour symbol" for
// the leaf rows of a nested key. "_total" is what percentages divide by.
function legendCounts(rows, colorKey, symbolKey){
  const counts={_total:rows.length};
  const bump=k=>{ counts[k]=(counts[k]||0)+1; };
  for(const r of rows){
    const c=r._attr[colorKey]??"", s=r._attr[symbolKey]??"";
    if(colorKey) bump("c "+c);
    if(symbolKey) bump("s "+s);
    if(colorKey&&symbolKey) bump("p "+c+" "+s);
  }
  return counts;
}

function drawLegend(svg, W, H, entries, attrLegends){
  const sections=legendItems(entries, attrLegends);
  if(!sections.length) return;
  const fs=opts.legFont, scale=opts.legScale, cols=Math.max(1,opts.legCols);
  const font=opts.legFontFamily||"sans-serif";
  const titleFs=opts.legTitleFont||fs;
  const pad=opts.legPad, gap=opts.legSwatchGap;
  const rowH=fs*(1.05+opts.legRowSpacing), swW=fs*1.7*scale;
  const g=el("g"); g.style.cursor="move";
  // measure
  const measure=el("text",{"font-family":font,"font-size":fs,visibility:"hidden"});
  svg.appendChild(measure);
  const textW=s=>{ measure.textContent=s; return measure.getComputedTextLength(); };

  let maxLabel=0;
  const flat=[];
  // A nested key's group rows head a block of children, so they take the
  // title weight on top of their swatch - indenting alone reads too weakly
  // when every swatch sits in the same column.
  const indent=fs*0.3*opts.legIndent;
  let maxIndent=0;
  for(const sec of sections){
    if(sec.title){ flat.push({type:"title",text:sec.title}); }
    sec.rows.forEach((r,i)=>{
      const depth=r.depth||0;
      if(sec.nested && depth===0 && i && opts.legGroupSpacer) flat.push({type:"gap"});
      flat.push({type:"row",...r,depth,
                 head:!!sec.nested&&depth===0&&opts.legBoldGroups});
      maxLabel=Math.max(maxLabel,textW(r.label));
      maxIndent=Math.max(maxIndent,depth*indent);
    });
    flat.push({type:"gap"});
  }
  // layout in columns
  const perCol=Math.ceil(flat.length/cols);
  const colW=swW+gap+maxLabel+maxIndent+16;
  let maxColRows=0;
  const colItems=[];
  for(let c=0;c<cols;c++){ colItems.push(flat.slice(c*perCol,(c+1)*perCol)); maxColRows=Math.max(maxColRows,colItems[c].length); }
  const boxW=pad*2 + cols*colW;
  const boxH=pad*2 + maxColRows*rowH;

  // position
  let bx,by;
  if(legendDrag){ bx=legendDrag.x*W; by=legendDrag.y*H; }
  else {
    const m=14, p=opts.legPos;
    // Second character picks the horizontal edge, first the vertical one;
    // "c" centres on that axis.
    const hx=p[1], vy=p[0];
    bx = hx==="r" ? W-boxW-m : hx==="l" ? m : (W-boxW)/2;
    by = vy==="t" ? m+(opts.title?30:0) : vy==="b" ? H-boxH-m : (H-boxH)/2;
  }
  bx=Math.max(2,Math.min(bx,W-boxW-2)); by=Math.max(2,Math.min(by,H-boxH-2));

  if(opts.legShadow){
    g.appendChild(el("rect",{x:bx+3,y:by+3,width:boxW,height:boxH,rx:opts.legRadius,
      fill:"rgba(0,0,0,0.18)"}));
  }
  g.appendChild(el("rect",{x:bx,y:by,width:boxW,height:boxH,rx:opts.legRadius,
    fill:opts.legFrameColor,
    "fill-opacity":opts.legFrame?opts.legFrameAlpha:0,
    stroke:opts.legFrame?opts.legFrameEdge:"none",
    "stroke-width":opts.legFrameWidth}));
  for(let c=0;c<cols;c++){
    let yy=by+pad+rowH*0.5;
    const cx0=bx+pad+c*colW;
    for(const item of colItems[c]){
      if(item.type==="title"){
        // Alignment is over the column the title heads, which is as much as
        // a hand-laid-out SVG legend can honestly offer.
        const inner=colW-16;
        const tx = opts.legTitleAlign==="right" ? cx0+inner
                 : opts.legTitleAlign==="center" ? cx0+inner/2 : cx0;
        const t=el("text",{x:tx, y:yy+fs*0.34,"font-family":font,"font-size":titleFs,
          "text-anchor":opts.legTitleAlign==="right"?"end":opts.legTitleAlign==="center"?"middle":"start",
          "font-weight":opts.legTitleBold?700:400,fill:opts.legTitleColor});
        if(opts.legTitleItalic) t.setAttribute("font-style","italic");
        if(opts.legTitleUnderline) t.setAttribute("text-decoration","underline");
        t.textContent=item.text; g.appendChild(t);
        yy+=rowH;
      } else if(item.type==="row"){
        const dx=(item.depth||0)*indent;
        const mx=cx0+dx+swW/2, my=yy;
        // A null style is a row that takes no swatch.
        if(item.style){
          const r_=Math.min(sizePx(item.style.size)*scale, fs*0.8*scale);
          const rr=Math.max(3.2, r_);
          const p=el("path",{d:markerPath(item.style.marker,rr),
            transform:`translate(${mx.toFixed(2)},${my.toFixed(2)})`});
          if(isOpen(item.style.marker)){ p.setAttribute("fill","none");
            p.setAttribute("stroke",item.style.color); p.setAttribute("stroke-width",Math.max(1,rr*0.24)); }
          else { p.setAttribute("fill",item.style.color); p.setAttribute("stroke","none"); }
          g.appendChild(p);
        }
        const bold=item.head?opts.legTitleBold:opts.legLabelBold;
        const t=el("text",{x:cx0+dx+swW+gap, y:my+fs*0.34,"font-family":font,"font-size":fs,
          fill:item.head?opts.legTitleColor:opts.legLabelColor,
          "font-weight":bold?700:400});
        if(item.head?opts.legTitleItalic:opts.legLabelItalic) t.setAttribute("font-style","italic");
        if(item.head?opts.legTitleUnderline:opts.legLabelUnderline) t.setAttribute("text-decoration","underline");
        t.textContent=item.label; g.appendChild(t);
        yy+=rowH;
      } else { yy+=rowH*0.4; }
    }
  }
  svg.removeChild(measure);
  // drag
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

