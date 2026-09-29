/* rendering */
const svg = $("#map");
function setAttrs(e, attrs){ for(const k in attrs) e.setAttribute(k, attrs[k]); return e; }
function el(tag, attrs){ const e=document.createElementNS(svgNS,tag); return attrs ? setAttrs(e, attrs) : e; }
function clearNode(node){ while(node.firstChild) node.removeChild(node.firstChild); }
let sceneSize={w:0,h:0};

// Every change asks for a render, and a colour picker or a drag asks dozens of
// times a second. Coalescing those into one render per frame keeps the
// controls smooth; anything that reads the finished SVG (the exports) calls
// flushRender() first.
let renderQueued=0;
function render(){
  if(!renderQueued) renderQueued=requestAnimationFrame(()=>{ renderQueued=0; renderNow(); });
}
function flushRender(){
  if(!renderQueued) return;
  cancelAnimationFrame(renderQueued); renderQueued=0; renderNow();
}

// The map is a fixed stack of layers. The basemap and the points are rebuilt
// only when something they depend on changed, so restyling the legend or
// retitling the map leaves thousands of point paths alone.
const layers=(()=>{
  const bg=el("rect",{x:0,y:0});
  const defs=el("defs"), cp=el("clipPath",{id:"frameClip"}), clipRect=el("rect");
  cp.appendChild(clipRect); defs.appendChild(cp);
  const content=el("g",{"clip-path":"url(#frameClip)"});
  const base=el("g"), points=el("g");
  content.appendChild(base); content.appendChild(points);
  const overlay=el("g"), legend=el("g");
  for(const n of [bg,defs,content,overlay,legend]) svg.appendChild(n);
  return {bg, clipRect, base, points, overlay, legend};
})();
let baseKey=null, pointsKey=null;
// Projected basemap outlines, kept until the projection or the frame changes,
// so toggling a layer or recolouring the land costs no reprojection.
let pathCache={key:null, d:{}};
function cachedPath(projKey, name, make){
  if(pathCache.key!==projKey) pathCache={key:projKey, d:{}};
  if(!(name in pathCache.d)) pathCache.d[name]=make()||"";
  return pathCache.d[name];
}
// Stable ids for row arrays, so the points key can tell an edited dataset
// (a new array) from an unchanged one without hashing every coordinate.
const rowsIds=new WeakMap(); let nextRowsId=1;
function rowsId(rows){ let id=rowsIds.get(rows); if(!id) rowsIds.set(rows, id=nextRowsId++); return id; }

function renderNow(){
  const stage=$("#stage");
  const W=stage.clientWidth, H=stage.clientHeight;
  sceneSize={w:W,h:H};
  svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  svg.setAttribute("width",W); svg.setAttribute("height",H);

  const rect = drawRect(W,H);
  frameRect = rect;
  clampView();   // a resize can leave the old pan outside the new frame
  const proj = buildProjection(W,H);
  currentProjection = proj;
  const path = d3.geoPath(proj);
  const [[rx0,ry0],[rx1,ry1]] = rect;
  const rw=rx1-rx0, rh=ry1-ry0;
  const useRect = silhouetteIsRect();
  const pd = currentProjDef();
  const projKey = JSON.stringify([opts.projection, opts.extent, opts.centerLon, opts.centerLat,
    opts.orientation, W, H, view]);
  const sphereD = useRect ? "" : cachedPath(projKey, "sphere", ()=>path({type:"Sphere"}));

  // background (mat), and the clip for everything inside the map rectangle
  setAttrs(layers.bg, {width:W, height:H, fill:opts.matColor});
  setAttrs(layers.clipRect, {x:rx0, y:ry0, width:rw, height:rh});

  // basemap: ocean / earth silhouette, graticule, land, borders, coastline
  const lw=opts.lineWidth;
  const bKey=JSON.stringify([projKey, opts.ocean, opts.graticule, opts.showLand, opts.landColor,
    opts.showBorders, opts.showCoast, lw]);
  if(bKey!==baseKey){
    baseKey=bKey;
    const base=layers.base; clearNode(base);
    const oceanFill = OCEAN_COLORS[opts.ocean] || "#ffffff";
    base.appendChild(useRect
      ? el("rect",{x:rx0,y:ry0,width:rw,height:rh,fill:oceanFill,stroke:"none"})
      : el("path",{d:sphereD, fill:oceanFill, stroke:"none"}));
    if(opts.graticule>0){
      const step=opts.graticule;
      base.appendChild(el("path",{d:cachedPath(projKey, "grat"+step,
          ()=>path(d3.geoGraticule().step([step,step])())),
        fill:"none", stroke:"#9aa3ac", "stroke-width":0.5, "stroke-opacity":0.7}));
    }
    if(opts.showLand){
      base.appendChild(el("path",{d:cachedPath(projKey, "land", ()=>path(LAND)),
        fill:opts.landColor, stroke:"none"}));
    }
    if(opts.showBorders){
      base.appendChild(el("path",{d:cachedPath(projKey, "borders", ()=>path(BORDERS)),
        fill:"none", stroke:"#000000", "stroke-width":0.55*lw, "stroke-opacity":0.85,
        "stroke-linejoin":"round"}));
    }
    if(opts.showCoast){
      base.appendChild(el("path",{d:cachedPath(projKey, "coast", ()=>path(LAND_MESH)),
        fill:"none", stroke:"#333333", "stroke-width":0.7*lw, "stroke-linejoin":"round"}));
    }
  }

  // points: one <g> per style carries the colour, opacity and stroke, and the
  // marker outline is built once per group; each point is a translated path.
  const visible=datasets.filter(d=>d.visible);
  const resolved=visible.map(ds=>({ds, res:resolveGroups(ds)}));
  const pKey=JSON.stringify([projKey, opts.labels, resolved.map(({ds,res})=>[
    rowsId(ds.rows), ds.rows.length, ds.groupBy, ds.colorBy, ds.symbolBy, ds.opacity ?? 1,
    res.groups.map(g=>[g.rows.length, g.style.color, g.style.marker, g.style.size])])]);
  if(pKey!==pointsKey){
    pointsKey=pKey;
    const ptsG=layers.points; clearNode(ptsG);
    const labelsG=el("g",{"font-family":"sans-serif","font-size":10,fill:"#222"});
    const onGlobe=!!pd.globe, centre=[opts.centerLon,opts.centerLat];
    for(const {ds,res} of resolved){
      const op=ds.opacity ?? 1;
      for(const grp of res.groups){
        const st=grp.style, r_=sizePx(st.size), d=markerPath(st.marker,r_);
        const g=el("g", isOpen(st.marker)
          ? {fill:"none", stroke:st.color, "stroke-width":Math.max(1.1,r_*0.22), "stroke-opacity":op}
          : {fill:st.color, "fill-opacity":op, stroke:"none"});
        for(const r of grp.rows){
          if(onGlobe && d3.geoDistance([r.lon,r.lat],centre)>Math.PI/2) continue;
          const xy=proj([r.lon, r.lat]);
          if(!xy || !isFinite(xy[0]) || !isFinite(xy[1])) continue;
          // Zoomed in, most points fall outside the frame; skip them rather
          // than draw them under the clip.
          if(xy[0]<rx0-r_ || xy[0]>rx1+r_ || xy[1]<ry0-r_ || xy[1]>ry1+r_) continue;
          g.appendChild(el("path",{d, transform:`translate(${xy[0].toFixed(2)},${xy[1].toFixed(2)})`}));
          if(opts.labels && r.label){
            const t=el("text",{x:(xy[0]+r_+2).toFixed(2), y:(xy[1]+3).toFixed(2)});
            t.textContent=r.label; labelsG.appendChild(t);
          }
        }
        if(g.firstChild) ptsG.appendChild(g);
      }
    }
    if(labelsG.firstChild) ptsG.appendChild(labelsG);
  }

  // legend rows
  const legendEntries=[]; // {title, rows:[{label, style}]}
  const attrLegends=[];
  const manyDatasets=visible.length>1;
  for(const {ds,res} of resolved){
    if(res.mode==="attr"){
      attrLegends.push({ds,res});
      continue;
    }
    // Counts belong on the row text here too - reading opts.legCounts only
    // in the attribute branch is what used to make "Show point counts" do
    // nothing at all in plain Group-by mode.
    const total=res.groups.reduce((a,g)=>a+g.rows.length,0);
    const sizes={}, place={}, first={};
    let rows=res.groups.map((grp,i)=>{
      const o=ds.overrides[rowKey("group",grp.label)];
      // Hidden rows keep their points on the map but leave the legend.
      if(isHidden(o)) return null;
      const label=legendLabel(overrideLabel(o)||grp.label, grp.rows.length, total);
      sizes[label]=grp.rows.length;
      place[label]=manualOrder(o);
      if(!(label in first)) first[label]=i;
      return {label, style:grp.style};
    }).filter(Boolean);
    const labels=rows.map(r=>r.label);
    const order = opts.legOrder==="manual"
      ? [...labels].sort((a,b)=>(place[a]-place[b])||(first[a]-first[b]))
      : orderLabels(labels, opts.legOrder, l=>sizes[l]||0);
    const rank={}; order.forEach((l,i)=>{ rank[l]=i; });
    rows=rows.sort((a,b)=>(rank[a.label]??0)-(rank[b.label]??0));
    const prefix=(manyDatasets && opts.legDatasetPrefix) ? ds.name+": " : "";
    legendEntries.push({title:prefix+(ds.groupBy||ds.name||""), rows});
  }

  // frame outline (unclipped, crisp), title and compass. Zoomed in, a round
  // silhouette runs past the frame, so the frame itself is the outline.
  const overlay=layers.overlay; clearNode(overlay);
  overlay.appendChild(useRect || isZoomed()
    ? el("rect",{x:rx0,y:ry0,width:rw,height:rh,fill:"none",stroke:"#5a6068","stroke-width":1})
    : el("path",{d:sphereD, fill:"none", stroke:"#5a6068","stroke-width":1}));
  if(opts.title){
    const t=el("text",{x:W/2, y:26, "text-anchor":"middle","font-family":"sans-serif",
      "font-size":19,"font-weight":700,fill:"#1d2127"});
    t.textContent=opts.title; overlay.appendChild(t);
  }
  if(opts.compass) drawCompass(overlay, rect);

  // legend
  clearNode(layers.legend);
  if(opts.legShow && (legendEntries.length || attrLegends.length)){
    drawLegend(layers.legend, W, H, legendEntries, attrLegends);
  }

  updateSwatches(resolved);
  $("#emptyHint").style.display = visible.some(d=>d.rows.length) ? "none":"block";
  updateStagebar();
  scheduleSave();
}

function drawCompass(parent, rect){
  const [[x0,y0],[x1]] = rect;
  const cx=x1-26, cy=y0+34;
  const g=el("g");
  g.appendChild(el("line",{x1:cx,y1:cy+16,x2:cx,y2:cy-14,stroke:"#1a1a1a","stroke-width":1.6}));
  g.appendChild(el("path",{d:poly([[cx,cy-20],[cx-4,cy-11],[cx+4,cy-11]]),fill:"#1a1a1a"}));
  const t=el("text",{x:cx,y:cy-24,"text-anchor":"middle","font-family":"sans-serif",
    "font-size":13,"font-weight":700,fill:"#1a1a1a"}); t.textContent="N";
  g.appendChild(t); parent.appendChild(g);
}

function legendItems(entries, attrLegends){
  // returns array of sections: {title, rows:[{label, style, symbolOnly, colorOnly}]}
  const sections=[];
  for(const group of entries){
    // Group-mode datasets each get their own section, so several datasets on
    // one map stay tellable apart instead of merging into a single list.
    const title = opts.legSectionTitles ? (group.title || "") : "";
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
    const lab=(v,key,o)=>legendLabel(overrideLabel(o)||v, counts?counts[key]:null, total);
    const ov=key=>ds.overrides[key];
    // Rows in display order; manual ordering is whatever the user dragged
    // them into, with rows they never touched falling to the end.
    const ordered=(values, keyOf, countKeyOf)=>{
      if(opts.legOrder!=="manual")
        return orderLabels(values, opts.legOrder, v=>countOf(countKeyOf(v)));
      const at=new Map(values.map((v,i)=>[v,i]));
      return [...values].sort((a,b)=>
        (manualOrder(ov(keyOf(a)))-manualOrder(ov(keyOf(b))))
        || (at.get(a)-at.get(b)));
    };
    if(res.nested){
      // The two columns form a hierarchy, so list each symbol value under the
      // colour group it belongs to, drawn in the marker and colour it has on
      // the map. Two independent keys would imply colours x symbols
      // combinations when only `symbols` of them exist, and leave the reader
      // to work out which colour each symbol goes with by hunting the map.
      const kidsOf=childrenByOwner(res);
      const rows=[];
      // Every colour group is listed. MiniMappr has no filter, so the only
      // way a group ends up childless is forced nesting, where each symbol
      // is claimed by the first group it appears under - and dropping those
      // would take colours off the legend that are still drawn on the map.
      const parents=ordered(Object.keys(res.colorMap),
        cv=>rowKey("color",cv), v=>countKey("c",v));
      for(const cv of parents){
        const color=res.colorMap[cv];
        const parentOverride=ov(rowKey("color",cv));
        // Hiding a group hides the block it heads: its children are drawn in
        // its colour, so leaving them behind would orphan them.
        if(isHidden(parentOverride)) continue;
        const kids=ordered(
          kidsOf.get(cv)||[],
          sv=>rowKey("pair",cv,sv), k=>countKey("p",cv,k))
          .filter(sv=>!isHidden(ov(rowKey("pair",cv,sv))));
        rows.push({label:lab(cv,countKey("c",cv),parentOverride), depth:0,
          style:applyOverride(groupSwatch(color, kids, res.symbolMap, ds.base.size),
                              parentOverride)});
        for(const sv of kids) rows.push({label:lab(sv,countKey("p",cv,sv),ov(rowKey("pair",cv,sv))), depth:1,
          style:applyOverride({color, marker:res.symbolMap[sv], size:ds.base.size},
                              ov(rowKey("pair",cv,sv)))});
      }
      if(rows.length) sections.push({title:sectionTitle(prefix,res.colorKey,res.symbolKey),
        rows, nested:true});
      continue;
    }
    // Genuinely crossed: a shape really does appear in every colour here, so
    // the neutral symbol swatches are honest and the two keys stay separate.
    if(Object.keys(res.colorMap).length){
      const values=ordered(Object.keys(res.colorMap), v=>rowKey("color",v), v=>countKey("c",v))
        .filter(v=>!isHidden(ov(rowKey("color",v))));
      const rows=values.map(v=>({label:lab(v,countKey("c",v),ov(rowKey("color",v))), colorOnly:true,
        style:applyOverride({color:res.colorMap[v],marker:"Circle",size:ds.base.size},
                            ov(rowKey("color",v)))}));
      if(rows.length) sections.push({title:sectionTitle(prefix,res.colorKey||"Colour"), rows});
    }
    if(Object.keys(res.symbolMap).length){
      const values=ordered(Object.keys(res.symbolMap), v=>rowKey("symbol",v), v=>countKey("s",v))
        .filter(v=>!isHidden(ov(rowKey("symbol",v))));
      const rows=values.map(v=>({label:lab(v,countKey("s",v),ov(rowKey("symbol",v))), symbolOnly:true,
        style:applyOverride({color:opts.legSymbolColor,marker:res.symbolMap[v],size:ds.base.size},
                            ov(rowKey("symbol",v)))}));
      if(rows.length) sections.push({title:sectionTitle(prefix,res.symbolKey||"Symbol"), rows});
    }
  }
  // A typed legend title names the whole key, whatever built it: it replaces
  // the heading of a one-section legend, and heads a legend of several
  // sections, which keep their own headings.
  if(opts.legTitle && sections.length){
    if(sections.length===1) sections[0].title=opts.legTitle;
    else sections.unshift({title:opts.legTitle, rows:[]});
  }
  return sections;
}

// Symbol values under each colour value of a nested key, in symbol order.
function childrenByOwner(res){
  const kids=new Map();
  for(const sv of Object.keys(res.symbolMap)){
    const cv=res.owner[sv]??""; let list=kids.get(cv);
    if(!list) kids.set(cv, list=[]);
    list.push(sv);
  }
  return kids;
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

// Point counts for legend rows: by column value ("c"/"s"), and by colour +
// symbol ("p") for the leaf rows of a nested key. The parts are joined with
// ROW_SEP, like rowKey, so a value holding spaces cannot collide with another
// pair. "_total" is what percentages divide by.
function countKey(...parts){ return parts.join(ROW_SEP); }
function legendCounts(rows, colorKey, symbolKey){
  const counts={_total:rows.length};
  const bump=k=>{ counts[k]=(counts[k]||0)+1; };
  for(const r of rows){
    const c=r._attr[colorKey]??"", s=r._attr[symbolKey]??"";
    if(colorKey) bump(countKey("c",c));
    if(symbolKey) bump(countKey("s",s));
    if(colorKey&&symbolKey) bump(countKey("p",c,s));
  }
  return counts;
}

// Split legend items into at most `cols` columns of about equal height. A
// heading stays with the row it heads, and no column starts or ends on a gap.
function splitColumns(items, cols, heightOf){
  const trim=col=>{ while(col.length && col[col.length-1].type==="gap") col.pop(); return col; };
  const total=items.reduce((a,it)=>a+heightOf(it),0);
  if(cols<=1) return [trim([...items])];
  // What must fit before a column may break: a run of headings plus the
  // first thing under them.
  const needAt=i=>{
    let h=0, j=i;
    while(j<items.length && items[j].type==="title") h+=heightOf(items[j++]);
    return h+(j<items.length ? heightOf(items[j]) : 0);
  };
  const pack=limit=>{
    const out=[[]]; let h=0;
    for(let i=0;i<items.length;i++){
      const it=items[i]; let col=out[out.length-1];
      if(it.type==="gap" && !col.length) continue;
      if(it.type!=="gap" && col.length && h+needAt(i)>limit){
        if(out.length===cols) return null;
        trim(col); out.push(col=[]); h=0;
      }
      col.push(it); h+=heightOf(it);
    }
    return out.map(trim).filter(col=>col.length);
  };
  const step=Math.max(1, Math.min(...items.map(heightOf))/4);
  for(let limit=total/cols;; limit+=step){ const cols_=pack(limit); if(cols_) return cols_; }
}

// Text width from an offscreen canvas. Measuring an SVG <text> instead forces
// a layout of the whole map, thousands of freshly drawn points included.
const measureCtx=document.createElement("canvas").getContext("2d");
function textWidth(text, size, family, bold, italic){
  measureCtx.font=`${italic?"italic ":""}${bold?700:400} ${size}px ${family}`;
  return measureCtx.measureText(text).width;
}

function drawLegend(parent, W, H, entries, attrLegends){
  const sections=legendItems(entries, attrLegends);
  if(!sections.length) return;
  const fs=opts.legFont, scale=opts.legScale;
  const font=opts.legFontFamily||"sans-serif";
  const titleFs=opts.legTitleFont||fs;
  const pad=opts.legPad, gap=opts.legSwatchGap;
  const rowH=fs*(1.05+opts.legRowSpacing), swW=fs*1.7*scale;
  const g=el("g"); g.style.cursor="move";

  // A nested key's group rows head a block of children, so they take the
  // title weight on top of their swatch - indenting alone reads too weakly
  // when every swatch sits in the same column.
  const indent=fs*0.3*opts.legIndent;
  const titleH=Math.max(rowH, titleFs*(1.05+opts.legRowSpacing));
  const gapH=rowH*0.4, colGap=16;
  const cols=Math.max(1,Math.round(opts.legCols));
  const titleW=text=>textWidth(text, titleFs, font, opts.legTitleBold, opts.legTitleItalic);
  // Across several columns, a title that names the whole legend (the typed
  // title, or the heading of the only section) spans them instead of
  // widening the first.
  const whole=cols>1 && sections[0].title && (sections.length===1 || !sections[0].rows.length);
  const header=whole ? {text:sections[0].title, w:titleW(sections[0].title)} : null;
  const flat=[];
  let prevRows=false;
  for(const [si,sec] of sections.entries()){
    if(flat.length && prevRows) flat.push({type:"gap"});
    if(sec.title && !(header && si===0)) flat.push({type:"title", text:sec.title, w:titleW(sec.title)});
    sec.rows.forEach((r,i)=>{
      const depth=r.depth||0;
      const head=!!sec.nested&&depth===0&&opts.legBoldGroups;
      if(sec.nested && depth===0 && i && opts.legGroupSpacer) flat.push({type:"gap"});
      // Measured in the weight and slant it is drawn in.
      const w=depth*indent + swW + gap + textWidth(r.label, fs, font,
        head?opts.legTitleBold:opts.legLabelBold, head?opts.legTitleItalic:opts.legLabelItalic);
      flat.push({type:"row",...r,depth,head,w});
    });
    prevRows=sec.rows.length>0;
  }
  const heightOf=it=>it.type==="title"?titleH:it.type==="row"?rowH:gapH;
  const colItems=flat.length ? splitColumns(flat, cols, heightOf) : [];
  const contentW=Math.max(0,...flat.filter(it=>it.w).map(it=>it.w));
  const colW=contentW+colGap;
  const colH=colItems.map(col=>col.reduce((a,it)=>a+heightOf(it),0));
  const headerH=header ? titleH : 0;
  const innerW=Math.max(colItems.length*contentW + Math.max(0,colItems.length-1)*colGap,
                        header ? header.w : 0);
  const boxW=pad*2 + innerW;
  const boxH=pad*2 + headerH + Math.max(0,...colH);

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
  // Alignment is over the width the title heads - its column, or the whole
  // legend for a spanning title - which is as much as a hand-laid-out SVG
  // legend can honestly offer.
  const drawTitle=(text, x0, width, top)=>{
    const tx = opts.legTitleAlign==="right" ? x0+width
             : opts.legTitleAlign==="center" ? x0+width/2 : x0;
    const t=el("text",{x:tx, y:top+titleH/2+titleFs*0.34,"font-family":font,"font-size":titleFs,
      "text-anchor":opts.legTitleAlign==="right"?"end":opts.legTitleAlign==="center"?"middle":"start",
      "font-weight":opts.legTitleBold?700:400,fill:opts.legTitleColor});
    if(opts.legTitleItalic) t.setAttribute("font-style","italic");
    if(opts.legTitleUnderline) t.setAttribute("text-decoration","underline");
    t.textContent=text; g.appendChild(t);
  };
  if(header) drawTitle(header.text, bx+pad, innerW, by+pad);
  colItems.forEach((items,c)=>{
    let yy=by+pad+headerH;
    const cx0=bx+pad+c*colW;
    for(const item of items){
      if(item.type==="title"){
        drawTitle(item.text, cx0, contentW, yy);
        yy+=titleH;
      } else if(item.type==="row"){
        const dx=(item.depth||0)*indent;
        const mx=cx0+dx+swW/2, my=yy+rowH/2;
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
      } else { yy+=gapH; }
    }
  });
  // Dragging only slides the drawn legend; the map is rendered once, on release.
  g.addEventListener("mousedown",ev=>{
    ev.preventDefault(); ev.stopPropagation(); // don't also start a map pan
    const startX=ev.clientX, startY=ev.clientY;
    let dx=0, dy=0;
    function mv(e){
      dx=clamp(bx+e.clientX-startX, 2, W-boxW-2)-bx;
      dy=clamp(by+e.clientY-startY, 2, H-boxH-2)-by;
      g.setAttribute("transform",`translate(${dx},${dy})`);
    }
    function up(){ window.removeEventListener("mousemove",mv); window.removeEventListener("mouseup",up);
      if(dx||dy){ legendDrag={x:(bx+dx)/W, y:(by+dy)/H}; render(); } }
    window.addEventListener("mousemove",mv); window.addEventListener("mouseup",up);
  });
  g.addEventListener("dblclick",ev=>{ ev.stopPropagation(); legendDrag=null; render(); });
  parent.appendChild(g);
}

function updateStagebar(){
  const n=datasets.reduce((a,d)=>a+(d.visible?d.rows.length:0),0);
  const shown=datasets.filter(d=>d.visible).length;
  $("#stagebar").textContent = n ? `${n} point${n!==1?"s":""} · ${shown} dataset${shown!==1?"s":""} · ${opts.projection}` : opts.projection;
}

