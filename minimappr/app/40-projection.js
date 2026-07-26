/* ---------------- projection + frame ---------------- */
function sizePx(size){ return Math.sqrt(size)*1.4; }
function currentProjDef(){ return PROJ_DEFS[opts.projection]; }
// A MultiPoint sampling the box edges. Used only for fitExtent: bounds of a
// point set is the plain projected coordinate extent, with none of the
// spherical-interior ambiguity a full-width lon/lat Polygon would introduce
// (which would make bounds span the whole globe and defeat continent zoom).
function boxSample(lo0,lo1,la0,la1){
  const pts=[], step=2;
  for(let x=lo0;x<=lo1;x+=step){ pts.push([x,la0]); pts.push([x,la1]); }
  for(let y=la0;y<=la1;y+=step){ pts.push([lo0,y]); pts.push([lo1,y]); }
  return {type:"MultiPoint", coordinates:pts};
}
// Object used only for fitExtent (path bounds are winding-independent, so a
// densified lon/lat rectangle is safe here even at full width).
function fitObject(){
  const pd=currentProjDef();
  if(pd.globe) return {type:"Sphere"};
  const ml=pd.maxLat;
  let [lo0,lo1,la0,la1] = CONTINENT_EXTENTS[opts.extent];
  la0=Math.max(la0,-ml); la1=Math.min(la1,ml);
  return boxSample(lo0,lo1,la0,la1);
}
// The visible earth silhouette (ocean fill + outline) is a screen rectangle for
// cropped/continent views and for Mercator's world; a projected Sphere (which
// d3 fills correctly) for the round world projections and the globe.
function silhouetteIsRect(){
  const pd=currentProjDef();
  if(pd.globe) return false;
  if(opts.extent!=="World") return true;
  if(pd.maxLat<90) return true;
  return false;
}
function drawRect(W,H){
  const pad=12;
  if(opts.orientation==="portrait"){
    const aspect=6.5/9;
    let h=H-2*pad, w=h*aspect;
    if(w>W-2*pad){ w=W-2*pad; h=w/aspect; }
    const x=(W-w)/2, y=(H-h)/2;
    return [[x,y],[x+w,y+h]];
  }
  return [[pad,pad],[W-pad,H-pad]];
}
function buildProjection(W,H){
  const pd=currentProjDef();
  const p=pd.make();
  if(pd.globe || pd.azimuthal){ p.rotate([-opts.centerLon,-opts.centerLat]); }
  else if(pd.lambert){
    p.rotate([-opts.centerLon,0]);
    if(p.center) p.center([0, opts.centerLat]);
  }
  const rect=drawRect(W,H);
  try{ p.fitExtent(rect, fitObject()); }
  catch(e){ p.fitExtent(rect, {type:"Sphere"}); }
  // guard against degenerate scale
  if(!isFinite(p.scale()) || p.scale()<=0){ p.scale(Math.min(W,H)/6).translate([W/2,H/2]); }
  return p;
}

