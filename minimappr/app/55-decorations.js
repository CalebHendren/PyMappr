/* compass and scale bar (ported from decorations.py and renderer/overlays.py) */
// Where a decoration can sit. Matches decorations.CORNERS.
const CORNERS=["lower left","lower right","upper left","upper right"];
const DECOR_COLOR="#1a1a1a";

// Text with a white halo underneath (a stroked copy, which every SVG editor
// draws, unlike paint-order), so it reads over any fill.
function haloText(parent, text, attrs){
  for(const halo of [true,false]){
    const t=el("text", attrs);
    if(halo) setAttrs(t, {fill:"#ffffff", stroke:"#ffffff", "stroke-width":HALO_WIDTH*PT,
      "stroke-opacity":0.85, "stroke-linejoin":"round"});
    t.textContent=text; parent.appendChild(t);
  }
}

// The north arrow, in a corner of the frame; it moves to the other side when
// the legend is in that corner. It always points up the page: PyMappr's
// arrow runs from the "N" to its corner, which in a lower corner points
// south, and that is not carried over.
function drawCompass(parent, rect, avoid){
  const [[x0,y0],[x1,y1]]=rect;
  // `size` scales the whole arrow; `k` is its drawing unit in pixels, 0.75 pt
  // (one CSS pixel) at size 1. The "N" is PyMappr's 11 pt (10 pt under the
  // triangle) and the arrow's shaft its 1.4 pt.
  const size=clamp(Number(opts.compassSize)||1, 0.5, 3), k=0.75*size*PT;
  const triangle=opts.compassStyle==="triangle";
  const w=24*k, h=(triangle?44:56)*k;
  const padX=Math.max(0.025*(x1-x0),9*PT), padY=Math.max(0.025*(y1-y0),9*PT);
  const [vertical, horizontal]=(CORNERS.includes(opts.compassPos) ? opts.compassPos : "upper right").split(" ");
  const at=side=>({x:side==="left" ? x0+padX : x1-padX-w,
                   y:vertical==="upper" ? y0+padY : y1-padY-h, w, h});
  let box=at(horizontal);
  if(boxesMeet(box, avoid)){
    const other=at(horizontal==="left" ? "right" : "left");
    if(!boxesMeet(other, avoid)) box=other;
  }
  const cx=box.x+w/2, top=box.y;
  const g=el("g");
  const N={x:cx, "text-anchor":"middle", "font-family":MAP_FONT, "font-weight":700, fill:DECOR_COLOR};
  if(triangle){
    // a filled triangle pointing north, with the "N" under its base
    g.appendChild(el("path",{d:poly([[cx,top+2*k],[cx-9*k,top+26*k],[cx+9*k,top+26*k]]),
      fill:DECOR_COLOR, stroke:"#ffffff", "stroke-width":0.8*size*PT, "stroke-linejoin":"round"}));
    haloText(g, "N", {...N, y:top+41*k, "font-size":10*size*PT});
  } else {
    haloText(g, "N", {...N, y:top+13*k, "font-size":11*size*PT});
    g.appendChild(el("line",{x1:cx, y1:top+54*k, x2:cx, y2:top+24*k,
      stroke:DECOR_COLOR, "stroke-width":1.4*size*PT}));
    g.appendChild(el("path",{d:poly([[cx,top+17*k],[cx-4*k,top+27*k],[cx+4*k,top+27*k]]),
      fill:DECOR_COLOR}));
  }
  parent.appendChild(g);
}

// Round lengths a scale bar may show: 1, 2, 3 or 5 x 10^n, snapped down so
// the bar stays inside the width it was budgeted. Matches decorations.py.
const NICE_LENGTHS=[1,2,3,5];
const METRES_PER_MILE=1609.344;
const SCALE_WIDTH=0.22, SCALE_SEGMENTS=4;
function unitMetres(units){ return units==="mi" ? METRES_PER_MILE : 1000; }
function niceLength(metres, units){
  const per=unitMetres(units), value=metres/per;
  if(!Number.isFinite(value) || value<=0) return 0;
  const decade=10**Math.floor(Math.log10(value));
  for(const c of [...NICE_LENGTHS].reverse()) if(c*decade<=value) return c*decade*per;
  return NICE_LENGTHS[NICE_LENGTHS.length-1]*decade/10*per;
}
// "500 km"; a metric bar under a kilometre reads in metres, as a reader
// zoomed in on one locality expects.
function formatLength(metres, units){
  const fmt=v=>Number(v.toPrecision(6)).toLocaleString("en-US",{maximumFractionDigits:6});
  if(units!=="mi" && metres<1000) return `${fmt(metres)} m`;
  const value=metres/unitMetres(units);
  return `${value>=1 ? fmt(value) : Number(value.toPrecision(3))} ${units==="mi"?"mi":"km"}`;
}

// Metres between two lon/lat points on the WGS84 ellipsoid (Vincenty's
// inverse formula), which is what PyMappr measures with. Nearly antipodal
// points, where the iteration does not settle, fall back to the sphere.
const EARTH_KM=6371.0088;
function geodesicMetres(p, q){
  const a=6378137, f=1/298.257223563, b=a*(1-f), rad=Math.PI/180;
  const L=(q[0]-p[0])*rad;
  const U1=Math.atan((1-f)*Math.tan(p[1]*rad)), U2=Math.atan((1-f)*Math.tan(q[1]*rad));
  const sinU1=Math.sin(U1), cosU1=Math.cos(U1), sinU2=Math.sin(U2), cosU2=Math.cos(U2);
  let lambda=L, sinSigma, cosSigma, sigma, cosSqAlpha, cos2SigmaM, settled=false;
  for(let i=0;i<200;i++){
    const sinL=Math.sin(lambda), cosL=Math.cos(lambda);
    sinSigma=Math.hypot(cosU2*sinL, cosU1*sinU2-sinU1*cosU2*cosL);
    if(sinSigma===0) return 0;   // the same point
    cosSigma=sinU1*sinU2+cosU1*cosU2*cosL;
    sigma=Math.atan2(sinSigma, cosSigma);
    const sinAlpha=cosU1*cosU2*sinL/sinSigma;
    cosSqAlpha=1-sinAlpha*sinAlpha;
    cos2SigmaM=cosSqAlpha ? cosSigma-2*sinU1*sinU2/cosSqAlpha : 0;   // 0 on the equator
    const C=f/16*cosSqAlpha*(4+f*(4-3*cosSqAlpha));
    const prev=lambda;
    lambda=L+(1-C)*f*sinAlpha*(sigma+C*sinSigma*(cos2SigmaM+C*cosSigma*(-1+2*cos2SigmaM*cos2SigmaM)));
    if(Math.abs(lambda-prev)<1e-12){ settled=true; break; }
  }
  if(!settled) return d3.geoDistance(p,q)*EARTH_KM*1000;
  const uSq=cosSqAlpha*(a*a-b*b)/(b*b);
  const A=1+uSq/16384*(4096+uSq*(-768+uSq*(320-175*uSq)));
  const B=uSq/1024*(256+uSq*(-128+uSq*(74-47*uSq)));
  const dSigma=B*sinSigma*(cos2SigmaM+B/4*(cosSigma*(-1+2*cos2SigmaM*cos2SigmaM)
    -B/6*cos2SigmaM*(-3+4*sinSigma*sinSigma)*(-3+4*cos2SigmaM*cos2SigmaM)));
  return b*A*(sigma-dSigma);
}

// Heights are in pixels so the bar reads the same in a small window; its
// placement and length are fractions of the frame, as in PyMappr. Frame
// fractions here run up from the bottom, as matplotlib's axes do, so the
// code below follows overlays.py line for line.
// In points. The label size is ScaleBarOptions.fontsize.
const BAR_H=5, BAR_GAP=3, LABEL_GAP=3, LABEL_ROOM=14, SCALE_FONT=8, SCALE_EDGE=0.8;
let scaleBarNote=null;   // why the bar is missing, for the status line

// The scale bar: a round length measured on the row it stands on, refined
// against its own endpoints, in one or two units. Mirrors
// OverlaysMixin._apply_scale_bar and its helpers.
function drawScaleBar(parent, proj, rect, avoid){
  scaleBarNote=null;
  if(!proj.invert) return;
  const [[x0,y0],[x1,y1]]=rect, fw=x1-x0, fh=y1-y0;
  const sx=fx=>x0+fx*fw, sy=fy=>y1-fy*fh;
  // A screen point's lon/lat, or null off the map: outside a Robinson
  // ellipse or off the globe's disk, where invert returns nonsense or NaN.
  const lonLat=(px,py)=>{
    const ll=proj.invert([px,py]);
    if(!ll || !Number.isFinite(ll[0]) || !Number.isFinite(ll[1])) return null;
    const back=proj(ll);
    return back && Math.hypot(back[0]-px, back[1]-py)<0.5 ? ll : null;
  };
  const span=(fa,fb,fy)=>{
    const a=lonLat(sx(fa),sy(fy)), b=lonLat(sx(fb),sy(fy));
    return a && b ? geodesicMetres(a,b) : NaN;
  };
  // The bar's own row whenever the scale can be measured there; otherwise
  // step towards the middle, since the corners of a Robinson map or the
  // globe lie off the map altogether.
  const referenceRow=fy=>{
    for(const row of [fy, ...[0.25,0.5,0.75,1].map(step=>fy+(0.5-fy)*step)])
      if(Number.isFinite(span(0.45,0.55,row))) return row;
    return 0.5;
  };
  // Ground metres per unit of frame width near fx: a first guess only.
  const estimate=(fx,fy)=>{
    const left=clamp(fx-0.05, 0, 0.9);
    let metres=span(left, left+0.1, fy);
    if(!(metres>0)) metres=span(0.45,0.55,fy);
    return metres>0 ? metres/0.1 : NaN;
  };
  // The width a bar of `metres` needs, refined until the drawing really is
  // as long as its label says; null when no honest bar of it fits.
  const fitWidth=(metres, x, row, rightAnchored)=>{
    const per=estimate(x,row);
    if(!(per>0)) return null;
    let width=metres/per;
    for(let i=0;i<6;i++){
      if(!(width>0) || width>0.95) return null;
      const left=rightAnchored ? x-width : x;
      let actual=span(left, left+width, row);
      if(!(actual>0)) actual=span(0.5-width/2, 0.5+width/2, row);
      if(!(actual>0)) break;   // nothing measurable: keep the estimate
      const adjust=metres/actual;
      if(Math.abs(adjust-1)<0.001) break;
      width*=adjust;
    }
    return width>0 && width<=0.95 ? width : null;
  };

  const units=opts.scaleUnits==="both" ? ["km","mi"] : [opts.scaleUnits==="mi" ? "mi" : "km"];
  const anchor=opts.scaleAnchor;
  const dragged=!!(anchor && Number.isFinite(anchor.x) && Number.isFinite(anchor.y));
  const height=BAR_H*PT/fh, gap=BAR_GAP*PT/fh, font=SCALE_FONT*PT, labelGap=LABEL_GAP*PT;
  const [vertical, horizontal]=(CORNERS.includes(opts.scalePos) ? opts.scalePos : "lower left").split(" ");
  // The lower pad also keeps the bar clear of the on-screen status line.
  const y=dragged ? anchor.y : vertical==="upper" ? 1-0.03 : Math.max(0.03, 24/fh);

  const layout=x=>{
    const rightAnchored=x>0.5 && !dragged, topAnchored=y>0.5 && !dragged;
    const stack=units.length*height+(units.length-1)*gap;
    let baseY=topAnchored ? y-stack : y;
    // a second unit is labelled underneath, so lift the stack clear of it
    if(units.length>1 && !topAnchored && !dragged) baseY+=LABEL_ROOM*PT/fh;
    const bars=[], last=units.length-1;
    for(const [i,unit] of units.entries()){
      const yb=baseY+(last-i)*(height+gap);
      const row=referenceRow(yb+height/2);
      let metres;
      if(i===0 && opts.scaleLengthMode==="fixed" && opts.scaleFixed>0){
        metres=opts.scaleFixed*unitMetres(opts.scaleUnits);
      } else {
        const per=estimate(x,row);
        if(!(per>0)) return {note:"Scale bar: the map scale cannot be measured at this view."};
        metres=niceLength(per*SCALE_WIDTH, unit);
      }
      if(!(metres>0)) return {note:null};
      const width=fitWidth(metres, x, row, rightAnchored);
      if(width==null) return {note:"Scale bar: scale varies too much across this view to draw "
        + "an accurate bar - zoom in, or move the bar away from the poles."};
      const left=rightAnchored ? x-width : x;
      bars.push({unit, metres, width, yb, left, label:formatLength(metres, unit)});
    }
    // screen box, labels included, for dodging the legend and for dragging
    let bx0=Infinity, bx1=-Infinity;
    for(const b of bars){
      const lw=textWidth(b.label, font, MAP_FONT, false, false);
      const mid=sx(b.left+b.width/2);
      bx0=Math.min(bx0, sx(b.left), mid-lw/2); bx1=Math.max(bx1, sx(b.left+b.width), mid+lw/2);
    }
    const top=sy(bars[0].yb+height)-labelGap-font;
    const bottom=bars.length>1 ? sy(bars[last].yb)+labelGap+font : sy(bars[0].yb);
    return {bars, baseY, box:{x:bx0, y:top, w:bx1-bx0, h:bottom-top}};
  };

  let x=dragged ? anchor.x : horizontal==="right" ? 1-0.03 : 0.03;
  let result=layout(x);
  if(result.bars && !dragged && boxesMeet(result.box, avoid)){
    const other=layout(1-x);
    if(other.bars && !boxesMeet(other.box, avoid)){ result=other; x=1-x; }
  }
  if(!result.bars){ scaleBarNote=result.note; return; }

  const g=el("g"); g.style.cursor="move";
  const segments=opts.scaleStyle==="plain" ? 1 : SCALE_SEGMENTS;
  result.bars.forEach((b,i)=>{
    const top=sy(b.yb+height), bottom=sy(b.yb);
    for(let s=0;s<segments;s++){
      const left=sx(b.left+b.width*s/segments), right=sx(b.left+b.width*(s+1)/segments);
      g.appendChild(el("rect",{x:left.toFixed(2), y:top.toFixed(2), width:(right-left).toFixed(2),
        height:(bottom-top).toFixed(2), fill:s%2===0 ? DECOR_COLOR : "#ffffff",
        stroke:DECOR_COLOR, "stroke-width":SCALE_EDGE*PT}));
    }
    // the first unit is labelled above the stack, a second one below it
    haloText(g, b.label, {x:sx(b.left+b.width/2).toFixed(2),
      y:(i===0 ? top-labelGap : bottom+labelGap+font*0.8).toFixed(2),
      "text-anchor":"middle", "font-family":MAP_FONT, "font-size":font, fill:DECOR_COLOR});
  });
  // Drag to place it anywhere; the drop point is kept as the stack's lower
  // left corner in frame fractions, as PyMappr stores it. Double-click
  // snaps it back to its corner.
  const left=Math.min(...result.bars.map(b=>b.left));
  g.addEventListener("pointerdown",ev=>{
    if(ev.button!==0 || !ev.isPrimary) return;
    ev.preventDefault(); ev.stopPropagation();   // don't also start a map pan
    const startX=ev.clientX, startY=ev.clientY; let dx=0, dy=0;
    trackPointer(g, ev, e=>{
      dx=e.clientX-startX; dy=e.clientY-startY;
      g.setAttribute("transform",`translate(${dx},${dy})`);
    }, ()=>{
      if(!dx && !dy) return;
      opts.scaleAnchor={x:clamp(left+dx/fw,0,1), y:clamp(result.baseY-dy/fh,0,1)};
      render();
    });
  });
  g.addEventListener("dblclick",ev=>{ ev.stopPropagation(); opts.scaleAnchor=null; render(); });
  parent.appendChild(g);
}
