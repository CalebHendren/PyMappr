/* inset map (ported from geo/regions.py, decorations.inset_box_target and renderer/inset.py) */
// A small second map in a corner of the main one: either a locator, a wider
// area with a box marking what the map shows, or a close-up, a smaller area
// with its box drawn on the map instead. Which one follows from the two
// extents, so the user only picks the region. Extents are
// [lon0, lon1, lat0, lat1], as in PyMappr.

// Its look. Match INSET_LAND, INSET_LINE_SCALE, INSET_POINT_SCALE,
// INSET_FRAME_WIDTH and INSET_BOX_WIDTH in renderer/tables.py.
const INSET_LAND="#e3e3e3", INSET_LINE_SCALE=0.6, INSET_POINT_SCALE=0.3;
const INSET_FRAME_WIDTH=0.8, INSET_BOX_WIDTH=1.2;
// The gap to the frame and to a scale bar it steps around, and its width and
// height limits, as fractions of the map frame. Match _PAD, _GAP,
// _SIZE_RANGE and _MAX_HEIGHT in renderer/inset.py.
const INSET_PAD=0.02, INSET_GAP=0.015;
const INSET_SIZE_RANGE=[0.1, 0.6], INSET_MAX_HEIGHT=0.6;
// Room around a globe's disk, and points along each edge of a box so it
// bends with the projection. Match _GLOBE_MARGIN and _EDGE_POINTS.
const INSET_GLOBE_MARGIN=1.04, INSET_EDGE_POINTS=50;
// Room left around a country, and which of its parts come with it: those
// within REGION_NEARBY of the home part's span (at least REGION_NEARBY_MIN
// degrees), so the United States is its contiguous states. Match _PAD,
// _NEARBY and _NEARBY_MIN in geo/regions.py.
const REGION_PAD=0.08, REGION_NEARBY=0.1, REGION_NEARBY_MIN=2.0;
// PyMappr's "state" region needs admin-1 outlines, which MiniMappr does not
// carry; the rest are offered as there. Match decorations.INSET_PROJECTIONS
// and INSET_OCEANS.
const INSET_PROJECTIONS=["same","Equirectangular","Robinson","Globe"];
const INSET_OCEANS=["none","grey","blue"];
function insetRegionKnown(region){
  return region==="country" || region==="around" || region==="custom" || region in CONTINENT_EXTENTS;
}
// Settings from an older or hand-edited save fall back rather than leave the
// inset with nothing to show.
function normalizeInsetOpts(){
  if(!insetRegionKnown(opts.insetRegion)) opts.insetRegion="country";
  if(!INSET_PROJECTIONS.includes(opts.insetProjection)) opts.insetProjection="same";
  if(!INSET_OCEANS.includes(opts.insetOcean)) opts.insetOcean="none";
  if(!CORNERS.includes(opts.insetPos)) opts.insetPos="lower right";
  const a=opts.insetAnchor;
  if(!(a && Number.isFinite(a.x) && Number.isFinite(a.y))) opts.insetAnchor=null;
}

/* the area it shows */
// Planar lon/lat bounds of a ring, as shapely's .bounds.
function planarBounds(ring, lonOf){
  let x0=Infinity, x1=-Infinity, y0=Infinity, y1=-Infinity;
  for(const [lon,y] of ring){ const x=lonOf(lon);
    if(x<x0) x0=x; if(x>x1) x1=x; if(y<y0) y0=y; if(y>y1) y1=y; }
  return [x0,x1,y0,y1];
}
// A part drawn across the antimeridian (Russia's mainland in the 110m
// outlines) spans every longitude; it is measured eastward instead and cut
// at 180, where PyMappr's outlines are split.
function ringBounds(ring){
  const b=planarBounds(ring, x=>x);
  if(b[1]-b[0]<=180) return b;
  const east=planarBounds(ring, x=>x<0 ? x+360 : x);
  return [east[0], Math.min(east[1],180), east[2], east[3]];
}
function unionBounds(list){
  return [Math.min(...list.map(b=>b[0])), Math.max(...list.map(b=>b[1])),
          Math.min(...list.map(b=>b[2])), Math.max(...list.map(b=>b[3]))];
}
function inBounds(b, lon, lat){ return lon>=b[0] && lon<=b[1] && lat>=b[2] && lat<=b[3]; }
// The gap between two bounds; never more than the gap between what they hold.
function boundsGap(a, b){
  return Math.hypot(Math.max(0, a[0]-b[1], b[0]-a[1]), Math.max(0, a[2]-b[3], b[2]-a[3]));
}
function segmentDistance(px, py, ax, ay, bx, by){
  const dx=bx-ax, dy=by-ay, len=dx*dx+dy*dy;
  const t=len ? clamp(((px-ax)*dx+(py-ay)*dy)/len, 0, 1) : 0;
  return Math.hypot(px-ax-t*dx, py-ay-t*dy);
}
// Planar distance between two outer rings that do not overlap, as shapely
// measures it between the parts of one country.
function ringDistance(a, b){
  let best=Infinity;
  for(const [r,s] of [[a,b],[b,a]])
    for(const [px,py] of r)
      for(let i=1;i<s.length;i++){
        const d=segmentDistance(px, py, s[i-1][0], s[i-1][1], s[i][0], s[i][1]);
        if(d<best) best=d;
      }
  return best;
}
// The countries as polygon parts with their bounds, built on first use. Each
// keeps the extents already worked out per home part, since the inset asks
// again on every pan.
let countryIndex=null;
function countryParts(){
  if(countryIndex) return countryIndex;
  const fc=topojson.feature(CTRY_TOPO, CTRY_TOPO.objects.countries);
  countryIndex=fc.features.filter(f=>f.geometry).map(f=>{
    const g=f.geometry;
    const polygons=g.type==="Polygon" ? [g.coordinates] : g.type==="MultiPolygon" ? g.coordinates : [];
    const parts=polygons.map(rings=>({rings, bounds:ringBounds(rings[0])}));
    return {parts, bounds:parts.length ? unionBounds(parts.map(p=>p.bounds)) : [0,-1,0,-1],
            extents:new Map()};
  });
  return countryIndex;
}
function padExtent([lon0,lon1,lat0,lat1], fraction=REGION_PAD){
  // At least a little room, so a tiny island still gets some sea.
  const dx=Math.max((lon1-lon0)*fraction, 0.05), dy=Math.max((lat1-lat0)*fraction, 0.05);
  return [Math.max(lon0-dx,-180), Math.min(lon1+dx,180), Math.max(lat0-dy,-90), Math.min(lat1+dy,90)];
}
// The padded extent of the home part and the parts close to it. Mirrors
// regions._extent_near.
function extentNear(parts, home){
  const [hx0,hx1,hy0,hy1]=home.bounds;
  const reach=Math.max(Math.max(hx1-hx0, hy1-hy0)*REGION_NEARBY, REGION_NEARBY_MIN);
  const kept=parts.filter(p=>p===home
    || (boundsGap(p.bounds, home.bounds)<=reach && ringDistance(p.rings[0], home.rings[0])<=reach));
  return padExtent(unionBounds(kept.map(p=>p.bounds)));
}
// The padded extent of the country holding (lon, lat), or null at sea.
// Mirrors regions.containing_extent.
function containingExtent(lon, lat){
  for(const country of countryParts()){
    if(!inBounds(country.bounds, lon, lat)) continue;
    const home=country.parts.findIndex(p=>inBounds(p.bounds, lon, lat)
      && d3.geoContains({type:"Polygon", coordinates:p.rings}, [lon, lat]));
    if(home<0) continue;
    if(!country.extents.has(home))
      country.extents.set(home, extentNear(country.parts, country.parts[home]));
    return country.extents.get(home);
  }
  return null;
}
// The view grown `factor` times about its centre, kept on the globe.
// Mirrors regions.around_extent.
function aroundExtent(view, factor){
  let [lon0,lon1,lat0,lat1]=view;
  factor=Math.max(Number(factor)||1, 1);
  const cx=(lon0+lon1)/2, cy=(lat0+lat1)/2;
  const halfW=Math.min((lon1-lon0)*factor/2, 180), halfH=Math.min((lat1-lat0)*factor/2, 90);
  lon0=cx-halfW; lon1=cx+halfW;
  if(lon0< -180){ lon0=-180; lon1=Math.min(-180+2*halfW, 180); }
  else if(lon1>180){ lon0=Math.max(180-2*halfW, -180); lon1=180; }
  lat0=cy-halfH; lat1=cy+halfH;
  if(lat0< -90){ lat0=-90; lat1=Math.min(-90+2*halfH, 90); }
  else if(lat1>90){ lat0=Math.max(90-2*halfH, -90); lat1=90; }
  return [lon0,lon1,lat0,lat1];
}
// The typed-in extent, or null until all four sides are set and make a box.
function insetCustomExtent(){
  const sides=[opts.insetLonMin, opts.insetLonMax, opts.insetLatMin, opts.insetLatMax]
    .map(v=>String(v??"").trim()==="" ? NaN : Number(v));
  if(!sides.every(Number.isFinite)) return null;
  const [lon0,lon1,lat0,lat1]=sides;
  if(lon1<=lon0 || lat1<=lat0) return null;
  return [lon0, lon1, Math.max(lat0,-90), Math.min(lat1,90)];
}
// The extent the inset shows. A country that cannot be found (the map is
// centred on the sea) falls back to the area around the view, and a custom
// extent that is not complete yet to the whole world. Mirrors
// regions.inset_extent.
function insetExtent(view, centre){
  const region=opts.insetRegion;
  if(region in CONTINENT_EXTENTS) return CONTINENT_EXTENTS[region];
  if(region==="custom") return insetCustomExtent() || CONTINENT_EXTENTS["World"];
  if(region==="country"){
    const [lon,lat]=centre;
    if(Number.isFinite(lon) && Number.isFinite(lat)){
      const found=containingExtent(lon, lat);
      if(found) return found;
    }
  }
  return aroundExtent(view, opts.insetZoomOut);
}
// A screen point's lon/lat on `proj`, or null off the map: outside a
// Robinson ellipse or off the globe's disk, where invert returns nonsense.
function screenLonLat(proj, px, py){
  const ll=proj.invert && proj.invert([px,py]);
  if(!ll || !Number.isFinite(ll[0]) || !Number.isFinite(ll[1]) || Math.abs(ll[1])>90) return null;
  const back=proj(ll);
  return back && Math.hypot(back[0]-px, back[1]-py)<0.5 ? ll : null;
}
// The map's view as a lon/lat extent, and its centre. Sampled over a grid,
// as on a curved projection the corners of the view may be off the map
// entirely. Mirrors InsetMixin.view_lonlat.
function viewLonLat(proj, rect){
  const [[x0,y0],[x1,y1]]=rect, n=25;
  let lo0=Infinity, lo1=-Infinity, la0=Infinity, la1=-Infinity, sumLon=0, sumLat=0, count=0;
  for(let i=0;i<n;i++) for(let j=0;j<n;j++){
    const ll=screenLonLat(proj, x0+(x1-x0)*i/(n-1), y0+(y1-y0)*j/(n-1));
    if(!ll) continue;
    lo0=Math.min(lo0,ll[0]); lo1=Math.max(lo1,ll[0]); la0=Math.min(la0,ll[1]); la1=Math.max(la1,ll[1]);
    sumLon+=ll[0]; sumLat+=ll[1]; count++;
  }
  if(!count) return {extent:[-180,180,-90,90], centre:[0,0]};
  if(lo1-lo0>300){ lo0=-180; lo1=180; }
  const c=screenLonLat(proj, (x0+x1)/2, (y0+y1)/2) || [sumLon/count, sumLat/count];
  return {extent:[lo0,lo1,la0,la1], centre:[((c[0]+180)%360+360)%360-180, c[1]]};
}

/* which map the box goes on */
function extentArea([lon0,lon1,lat0,lat1]){ return Math.max(lon1-lon0,0)*Math.max(lat1-lat0,0); }
function extentOverlap(a, b){
  return extentArea([Math.max(a[0],b[0]), Math.min(a[1],b[1]), Math.max(a[2],b[2]), Math.min(a[3],b[3])]);
}
// "inset" when the inset shows a wider area around the map (a locator),
// "main" when it shows a smaller area inside it (a close-up), and null when
// the two hardly overlap. Mirrors decorations.inset_box_target.
function insetBoxTarget(insetExt, viewExt){
  const insetArea=extentArea(insetExt), viewArea=extentArea(viewExt);
  if(insetArea<=0 || viewArea<=0) return null;
  const shared=extentOverlap(insetExt, viewExt);
  // Two areas about the same size would only box each other's edges.
  if(insetArea>=1.5*viewArea && shared>=0.5*viewArea) return "inset";
  if(insetArea*1.5<=viewArea && shared>=0.5*insetArea) return "main";
  return null;
}

/* projection and frame */
// The inset's projection, at d3's own scale. "same" follows the map, except
// that a globe map gets a flat inset and a Lambert conic one whose area lies
// outside its continent gets Equirectangular, where the cone would tear.
// Mirrors InsetMixin._inset_projection.
function insetProjection(region, centre){
  const choice=opts.insetProjection, pd=currentProjDef();
  if(choice==="Globe"){
    // Whole degrees: the globe follows the map's centre, and a new
    // projection for every pixel of a pan would rebuild it each time.
    return {p:d3.geoOrthographic().clipAngle(90).rotate([-Math.round(centre[0]), -Math.round(centre[1])]),
            globe:true, maxLat:90};
  }
  if(choice==="Robinson") return {p:d3.geoRobinson(), maxLat:90};
  if(choice==="Equirectangular" || pd.globe) return {p:d3.geoEquirectangular(), maxLat:90};
  if(pd.lambert && !pd.azimuthal && pd.region){
    const [a0,a1,b0,b1]=CONTINENT_EXTENTS[pd.region];
    const [lon0,lon1,lat0,lat1]=region;
    if(lon0<a0 || lon1>a1 || lat0<b0 || lat1>b1) return {p:d3.geoEquirectangular(), maxLat:90};
  }
  return {p:orientProjection(pd.make(), pd), maxLat:pd.maxLat};
}
// A lon/lat rectangle's outline, densified so it bends with a projection.
function boxRing(lon0, lon1, lat0, lat1, n=INSET_EDGE_POINTS){
  const ring=[];
  for(let i=0;i<n;i++) ring.push([lon0+(lon1-lon0)*i/n, lat0]);
  for(let i=0;i<n;i++) ring.push([lon1, lat0+(lat1-lat0)*i/n]);
  for(let i=0;i<n;i++) ring.push([lon1-(lon1-lon0)*i/n, lat1]);
  for(let i=0;i<=n;i++) ring.push([lon0, lat1-(lat1-lat0)*i/n]);
  return ring;
}
// The inset's limits [x0, x1, y0, y1] in its projection, before fitting.
function insetLimits(ip, region){
  const p=ip.p;
  if(ip.globe){
    const [[a,b],[c,d]]=d3.geoPath(p).bounds({type:"Sphere"});
    const cx=(a+c)/2, cy=(b+d)/2, half=Math.max(c-a, d-b)/2*INSET_GLOBE_MARGIN;
    return [cx-half, cx+half, cy-half, cy+half];
  }
  const [lon0,lon1,lat0,lat1]=region;
  let x0=Infinity, x1=-Infinity, y0=Infinity, y1=-Infinity;
  for(const pt of boxRing(lon0, lon1, Math.max(lat0,-ip.maxLat), Math.min(lat1,ip.maxLat))){
    const xy=p(pt);
    if(!xy || !Number.isFinite(xy[0]) || !Number.isFinite(xy[1])) continue;
    x0=Math.min(x0,xy[0]); x1=Math.max(x1,xy[0]); y0=Math.min(y0,xy[1]); y1=Math.max(y1,xy[1]);
  }
  return Number.isFinite(x0) ? [x0,x1,y0,y1] : [0,1,0,1];
}
// The inset's size in pixels, sized to its region's shape and no taller than
// INSET_MAX_HEIGHT, with the limits widened to the box so map units stay
// square. Mirrors InsetMixin._fit_inset.
function fitInset(limits, fw, fh){
  let [x0,x1,y0,y1]=limits;
  const w=clamp(Number(opts.insetSize)||0.3, INSET_SIZE_RANGE[0], INSET_SIZE_RANGE[1])*fw;
  const spanX=Math.max(x1-x0,1e-9), spanY=Math.max(y1-y0,1e-9);
  let h=w*spanY/spanX;
  if(h>INSET_MAX_HEIGHT*fh){
    h=INSET_MAX_HEIGHT*fh;
    const wide=spanY*w/h, cx=(x0+x1)/2;
    x0=cx-wide/2; x1=cx+wide/2;
  }
  return {w, h, limits:[x0,x1,y0,y1]};
}
// How far in from the frame's edge a scale bar in `corner` reaches, so the
// inset can step beyond it; 0 when no bar sits there. The bar's own layout
// in 55-decorations.js, worked out ahead of drawing it.
function scaleBarReach(corner, fh){
  const a=opts.scaleAnchor;
  if(!opts.scaleBar || opts.scalePos!==corner || (a && Number.isFinite(a.x) && Number.isFinite(a.y))) return 0;
  const units=opts.scaleUnits==="both" ? 2 : 1;
  const stack=units*BAR_H+(units-1)*BAR_GAP;
  if(corner.startsWith("upper")) return 0.03*fh+stack+(units>1 ? LABEL_GAP+SCALE_FONT : 0);
  return Math.max(0.03*fh, 24)+(units>1 ? LABEL_ROOM : 0)+stack+LABEL_GAP+SCALE_FONT;
}
// The inset's screen box: in its corner, stepping beyond a scale bar there
// and under the title, or where it was dragged. The drag is kept as the
// lower left corner in frame fractions, as PyMappr stores it. Mirrors
// InsetMixin._place_inset.
function placeInset(w, h, rect){
  const [[fx0,fy0],[fx1,fy1]]=rect, fw=fx1-fx0, fh=fy1-fy0;
  const a=opts.insetAnchor;
  if(a && Number.isFinite(a.x) && Number.isFinite(a.y)){
    const x=clamp(a.x, 0, Math.max(0, 1-w/fw)), y=clamp(a.y, 0, Math.max(0, 1-h/fh));
    return {x:fx0+x*fw, y:fy1-y*fh-h, w, h};
  }
  const corner=CORNERS.includes(opts.insetPos) ? opts.insetPos : "lower right";
  const [vertical, horizontal]=corner.split(" ");
  const x=horizontal==="right" ? fx1-INSET_PAD*fw-w : fx0+INSET_PAD*fw;
  let y=vertical==="upper" ? fy0+INSET_PAD*fh+(opts.title ? 30 : 0) : fy1-INSET_PAD*fh-h;
  const reach=scaleBarReach(corner, fh);
  if(reach){
    if(vertical==="upper") y=Math.max(y, fy0+reach+INSET_GAP*fh);
    else y=Math.min(y, fy1-reach-INSET_GAP*fh-h);
  }
  return {x, y, w, h};
}

/* drawing */
let insetKey=null;      // what the inset body was last built from
let insetPlaced=null;   // its screen box, for dragging
// Draw the inset into layers.inset and a close-up's box into
// layers.insetMainBox, or clear both. Returns the inset's screen box, for
// the legend and the compass to keep clear of, or null.
function drawInset(resolved, mainProj, rect){
  const g=layers.inset, onMain=layers.insetMainBox;
  clearNode(onMain);
  insetPlaced=null;
  const [[fx0,fy0],[fx1,fy1]]=rect;
  // Before the page is laid out the frame has no size, and nothing fits.
  if(!opts.insetShow || fx1<=fx0 || fy1<=fy0){ clearNode(g); insetKey=null; return null; }
  const {extent:view, centre}=viewLonLat(mainProj, rect);
  const region=insetExtent(view, centre);
  const ip=insetProjection(region, centre);
  const fit=fitInset(insetLimits(ip, region), fx1-fx0, fy1-fy0);
  const box=placeInset(fit.w, fit.h, rect);
  // Scale the projection so its limits fill the box: a projected point is
  // translate + scale * raw, so scaling both about the limits' corner is exact.
  const p=ip.p, [x0,,y0]=fit.limits, s=box.w/(fit.limits[1]-x0), [tx,ty]=p.translate();
  p.scale(p.scale()*s).translate([box.x+s*(tx-x0), box.y+s*(ty-y0)]);
  p.clipExtent([[box.x,box.y],[box.x+box.w,box.y+box.h]]);
  const path=d3.geoPath(p);

  const key=JSON.stringify([opts.insetLand, opts.insetCountries, opts.insetOcean, opts.insetPoints,
    opts.insetProjection, opts.projection, region, p.scale(), p.translate(), p.rotate(), box, pointsKey]);
  if(key!==insetKey || !g.firstChild){
    insetKey=key;
    clearNode(g);
    const body=el("g");
    const shape=()=>ip.globe ? el("path",{d:path({type:"Sphere"})})
                             : el("rect",{x:box.x, y:box.y, width:box.w, height:box.h});
    // A globe reads as a disk: no square frame, and paper only inside its horizon.
    body.appendChild(setAttrs(shape(), {fill:OCEAN_COLORS[opts.insetOcean] || "#ffffff", stroke:"none"}));
    if(opts.insetLand) body.appendChild(el("path",{d:path(LAND)||"", fill:INSET_LAND, stroke:"none"}));
    // Without country borders the coast is still drawn, as on the map.
    if(opts.insetCountries)
      body.appendChild(el("path",{d:path(BORDERS)||"", fill:"none", stroke:"#000000",
        "stroke-width":Math.max(0.55*INSET_LINE_SCALE, 0.2), "stroke-opacity":0.85, "stroke-linejoin":"round"}));
    body.appendChild(el("path",{d:path(LAND_MESH)||"", fill:"none", stroke:"#333333",
      "stroke-width":Math.max(0.7*INSET_LINE_SCALE, 0.2), "stroke-linejoin":"round"}));
    if(opts.insetPoints) drawInsetPoints(body, resolved, p, ip, box);
    body.appendChild(setAttrs(shape(), {fill:"none", stroke:"#000000", "stroke-width":INSET_FRAME_WIDTH}));
    g.appendChild(body);
    g.appendChild(el("g"));   // the box, redrawn on every render
  }
  const boxG=g.lastChild; clearNode(boxG);
  drawInsetBox(boxG, onMain, ip, path, mainProj, rect, view, region);
  insetPlaced=box;
  return box;
}
function drawInsetPoints(parent, resolved, p, ip, box){
  const edge=opts.pointEdgeWidth>0 ? opts.pointEdgeColor : null;
  const rot=p.rotate(), centre=[-rot[0], -rot[1]];
  for(const {ds,res} of resolved){
    const op=ds.opacity ?? 1;
    for(const grp of res.groups){
      const st=grp.style, r_=sizePx(Math.max(st.size*INSET_POINT_SCALE, 3)), d=markerPath(st.marker, r_);
      const g=el("g", isOpen(st.marker)
        ? {fill:"none", stroke:st.color, "stroke-width":Math.max(0.8, r_*0.22), "stroke-opacity":op}
        : edge ? {fill:st.color, "fill-opacity":op, stroke:edge, "stroke-width":opts.pointEdgeWidth*0.6,
                  "stroke-opacity":op, "stroke-linejoin":"round"}
               : {fill:st.color, "fill-opacity":op, stroke:"none"});
      for(const r of grp.rows){
        if(ip.globe && d3.geoDistance([r.lon,r.lat], centre)>Math.PI/2) continue;
        const xy=p([r.lon, r.lat]);
        if(!xy || !Number.isFinite(xy[0]) || !Number.isFinite(xy[1])) continue;
        if(xy[0]<box.x || xy[0]>box.x+box.w || xy[1]<box.y || xy[1]>box.y+box.h) continue;
        g.appendChild(el("path",{d, transform:`translate(${xy[0].toFixed(2)},${xy[1].toFixed(2)})`}));
      }
      if(g.firstChild) parent.appendChild(g);
    }
  }
}
// The box linking the two maps: the map's view outlined on a locator inset,
// or the inset's area outlined on the map for a close-up. A globe inset
// always marks the view. Mirrors InsetMixin.inset_box_xy.
function drawInsetBox(onInset, onMain, ip, insetPath, mainProj, rect, view, region){
  if(!opts.insetBox) return;
  const target=ip.globe ? "inset" : insetBoxTarget(region, view);
  const stroke={fill:"none", stroke:opts.insetBoxColor || "#d62728", "stroke-width":INSET_BOX_WIDTH,
    "stroke-linejoin":"round"};
  if(target==="inset"){
    // The frame's outline taken back to lon/lat, split where it leaves the map.
    const [[x0,y0],[x1,y1]]=rect, lines=[]; let run=[];
    for(const [fx,fy] of boxRing(0,1,0,1)){
      const ll=screenLonLat(mainProj, x0+(x1-x0)*fx, y1-(y1-y0)*fy);
      if(ll) run.push(ll);
      else if(run.length){ if(run.length>1) lines.push(run); run=[]; }
    }
    if(run.length>1) lines.push(run);
    if(lines.length)
      onInset.appendChild(el("path",{d:insetPath({type:"MultiLineString", coordinates:lines})||"", ...stroke}));
  } else if(target==="main"){
    onMain.appendChild(el("path",{d:d3.geoPath(mainProj)({type:"LineString", coordinates:boxRing(...region)})||"",
      ...stroke}));
  }
}

/* dragging */
// Drag the inset anywhere in the frame; the drop point is kept, and a
// double-click snaps it back to its corner. Dragging only slides the drawn
// inset; the map is rendered once, on release.
layers.inset.style.cursor="move";
layers.inset.addEventListener("pointerdown",ev=>{
  if(ev.button!==0 || !ev.isPrimary || !insetPlaced) return;
  ev.preventDefault(); ev.stopPropagation();   // don't also start a map pan
  const b=insetPlaced, [[fx0,fy0],[fx1,fy1]]=frameRect;
  const startX=ev.clientX, startY=ev.clientY; let dx=0, dy=0;
  trackPointer(layers.inset, ev, e=>{
    dx=clamp(b.x+e.clientX-startX, fx0, Math.max(fx0, fx1-b.w))-b.x;
    dy=clamp(b.y+e.clientY-startY, fy0, Math.max(fy0, fy1-b.h))-b.y;
    layers.inset.setAttribute("transform",`translate(${dx},${dy})`);
  }, ()=>{
    layers.inset.removeAttribute("transform");
    if(!dx && !dy) return;
    opts.insetAnchor={x:(b.x+dx-fx0)/(fx1-fx0), y:(fy1-(b.y+dy)-b.h)/(fy1-fy0)};
    render();
  });
});
layers.inset.addEventListener("dblclick",ev=>{ ev.stopPropagation(); opts.insetAnchor=null; render(); });
