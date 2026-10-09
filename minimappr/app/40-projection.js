/* print scale */
// Every size on the map - line widths, markers, text, gaps - is set in
// points, as PyMappr's are, and drawn at PT screen pixels per point. PT
// comes from the print width the export is set to, so the preview is the
// printed figure scaled to the window and the export comes out at its true
// size whatever the window. The print width covers the frame, the degree
// labels left of it and the export margin on both sides.
let PT=1;
// Screen gap around the figure, in pixels: window chrome, not print.
const SCREEN_PAD=12;
// The export's margin around the figure, in points.
const EXPORT_MARGIN_PT=6;
function printWidthPt(){
  const inches=Math.max(Number(opts.exportWidth)||0, 0.5)/(opts.exportUnit==="cm" ? 2.54 : 1);
  return inches*72;
}
// Room the degree labels take left of and below the frame, in points.
function gridMarginsPt(){ return gridLabelsShown() ? [GRID_LABEL_W, GRID_LABEL_H] : [0, 0]; }
// Screen pixels per point for a W x H map area. Across the window the label
// margin and the frame share the print width less its margins; a portrait
// frame may instead run out of height first.
function printScale(W, H){
  const P=printWidthPt(), [L,B]=gridMarginsPt(), E=EXPORT_MARGIN_PT;
  const aw=W-2*SCREEN_PAD, ah=H-2*SCREEN_PAD;
  let pt=aw/(P-2*E);
  if(opts.orientation==="portrait") pt=Math.min(pt, PORTRAIT_ASPECT*ah/(P-L-2*E+PORTRAIT_ASPECT*B));
  return pt>0 && Number.isFinite(pt) ? pt : 1;
}
// The font the map's text is set in: DejaVu Sans, matplotlib's and so
// PyMappr's, where it is installed, and the usual sans-serifs elsewhere.
const FONT_STACKS={"sans-serif":"'DejaVu Sans', Arial, Helvetica, sans-serif",
  "serif":"'DejaVu Serif', 'Times New Roman', Times, serif",
  "monospace":"'DejaVu Sans Mono', Consolas, 'Courier New', monospace"};
const MAP_FONT=FONT_STACKS["sans-serif"];
function fontStack(family){ return FONT_STACKS[family] || MAP_FONT; }
// A marker's size across, in pixels. Sizes are areas in points squared, as
// matplotlib's scatter takes them, so a size 30 point is sqrt(30) pt across.
function markerPx(size){ return Math.sqrt(Math.max(Number(size)||0, 0))*PT; }
// PyMappr's look, in points. Match the countries row of LINE_LAYERS in
// renderer/tables.py, the grid and tick settings in renderer/view.py and
// matplotlib's 0.8 pt axes frame.
const BORDER_COLOR="#000000", BORDER_WIDTH=0.8;
const FRAME_COLOR="#000000", FRAME_WIDTH=0.8;
const GRID_COLOR="#787878", GRID_WIDTH=0.4, GRID_ALPHA=0.7;
const TICK_LABEL_SIZE=7, TICK_LENGTH=2.5;
// Open markers are outlined at PyMappr's 1.2 pt (points._marker_paint).
const OPEN_EDGE_WIDTH=1.2;
// The white halo under text on the map. Matches LABEL_HALO's width.
const HALO_WIDTH=2.2;
// MiniMappr's own: point labels, and the map title at matplotlib's "large".
const POINT_LABEL_SIZE=7, TITLE_SIZE=12;
// Room the title takes at the top of the frame, for what sits under it.
function titleBand(){ return opts.title ? TITLE_SIZE*1.6*PT : 0; }

/* projection + frame */
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
// Degree labels along the left and bottom edges, as PyMappr's axis ticks
// are: only on the plain lon/lat projection, where a meridian is a straight
// vertical line. They sit outside the frame, which gives up room for them.
function gridLabelsShown(){
  return opts.graticule>0 && !opts.gridHideLabels && opts.projection==="Equirectangular";
}
// The label margins, in points: room for "100°W" and "40°S" at 7 pt beside
// their ticks.
const GRID_LABEL_W=28, GRID_LABEL_H=13;
const PORTRAIT_ASPECT=6.5/9;
function drawRect(W,H){
  const pad=SCREEN_PAD, [L,B]=gridMarginsPt();
  const left=pad+L*PT, bottom=pad+B*PT;
  const aw=W-left-pad, ah=H-pad-bottom;
  if(opts.orientation==="portrait"){
    let h=ah, w=h*PORTRAIT_ASPECT;
    if(w>aw){ w=aw; h=w/PORTRAIT_ASPECT; }
    const x=left+(aw-w)/2, y=pad+(ah-h)/2;
    return [[x,y],[x+w,y+h]];
  }
  return [[left,pad],[W-pad,H-bottom]];
}
// Turn a fresh projection to the map's centre, for the projections that
// have one. The inset's "same as map" projection goes through here too.
function orientProjection(p, pd){
  if(pd.globe || pd.azimuthal){ p.rotate([-opts.centerLon,-opts.centerLat]); }
  else if(pd.lambert){
    p.rotate([-opts.centerLon,0]);
    if(p.center) p.center([0, opts.centerLat]);
  }
  return p;
}
function buildProjection(W,H){
  const pd=currentProjDef();
  const p=orientProjection(pd.make(), pd);
  const rect=drawRect(W,H);
  try{ p.fitExtent(rect, fitObject()); }
  catch(e){ p.fitExtent(rect, {type:"Sphere"}); }
  // guard against degenerate scale
  if(!isFinite(p.scale()) || p.scale()<=0){ p.scale(Math.min(W,H)/6).translate([W/2,H/2]); }
  // Zoom and pan: scaling the scale and the translate by k is exact for d3
  // projections, centre included, since a projected point is
  // translate + scale * (raw - raw centre).
  if(isZoomed()){
    const [tx,ty]=p.translate();
    p.scale(p.scale()*view.k).translate([tx*view.k+view.x, ty*view.k+view.y]);
  }
  // Clip paths to the frame, so a zoomed map (and its export) carries only
  // the visible geometry.
  p.clipExtent(rect);
  return p;
}

