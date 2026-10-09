/* export (ported from ui/save_image.py) */
// The image is the map frame and what is drawn around it - title, legend,
// scale bar, grid labels - cropped out of the window, so a portrait map
// loses its side bars as PyMappr's export does. Its print width is the
// export width: the frame, the degree labels and a margin, laid out in
// points by the print scale (PT), so the image is exactly that wide unless a
// legend or inset was dragged out past the frame. The pixels follow from the
// width and the DPI.
const PUBLICATION_DPI=600;
// A journal page, Zootaxa's and Phytotaxa's. Matches save_image.JOURNAL_PAGE_WIDTH.
const PUBLICATION_WIDTH=[17, "cm"];
const MAX_EXPORT_SIDE=16384, MAX_EXPORT_AREA=120e6;
const EXPORT_TYPES={
  png:{mime:"image/png", ext:"png"}, jpeg:{mime:"image/jpeg", ext:"jpg"},
  webp:{mime:"image/webp", ext:"webp"}, tiff:{ext:"tif"}, pdf:{ext:"pdf"}, svg:{ext:"svg"},
};

// The part of the scene the export keeps, in scene pixels: the frame with
// its label margins, grown to take in anything drawn past them, plus the
// margin all round.
function exportBox(){
  const [[x0,y0],[x1,y1]]=frameRect, [L,B]=gridMarginsPt();
  let bx0=x0-L*PT, by0=y0, bx1=x1, by1=y1+B*PT;
  for(const g of [layers.overlay, layers.inset, layers.legend]){
    if(!g.firstChild) continue;
    const b=g.getBBox();
    if(!b.width && !b.height) continue;
    bx0=Math.min(bx0,b.x); by0=Math.min(by0,b.y);
    bx1=Math.max(bx1,b.x+b.width); by1=Math.max(by1,b.y+b.height);
  }
  const pad=EXPORT_MARGIN_PT*PT;
  return {x:bx0-pad, y:by0-pad, w:bx1-bx0+2*pad, h:by1-by0+2*pad};
}
// Print size and pixel size of the export.
function exportSize(box){
  const inches=box.w/PT/72;
  const dpi=Math.max(Number(opts.exportDpi)||0, 1);
  const px=Math.max(1, Math.round(inches*dpi));
  const py=Math.max(1, Math.round(px*box.h/box.w));
  return {inches, heightIn:inches*box.h/box.w, dpi, px, py,
    tooBig: px>MAX_EXPORT_SIDE || py>MAX_EXPORT_SIDE || px*py>MAX_EXPORT_AREA};
}
// The live readout under the controls, as in PyMappr's save dialog.
function updateExportReadout(){
  if(!sceneSize.w || !frameRect) return;
  const box=exportBox(), s=exportSize(box);
  const unit=opts.exportUnit==="cm" ? "cm" : "in", k=unit==="cm" ? 2.54 : 1;
  const print=`${fmtNum(s.inches*k)} × ${fmtNum(s.heightIn*k)} ${unit}`;
  $("#exportSize").textContent = opts.exportFormat==="svg"
    ? `${print}, vector (scales without pixels)`
    : `${s.px.toLocaleString("en-US")} × ${s.py.toLocaleString("en-US")} px, ${print} at ${fmtNum(s.dpi)} DPI`;
  $("#exportErr").textContent = s.tooBig && opts.exportFormat!=="svg"
    ? "Too large for a browser to draw. Lower the width or the DPI." : "";
}
function fmtNum(v){ return String(Number(v.toFixed(2))); }

// A copy of the map showing just `box`, at the given size.
function exportSvg(box, width, height){
  const copy=svg.cloneNode(true);
  copy.removeAttribute("class");
  setAttrs(copy, {viewBox:`${box.x} ${box.y} ${box.w} ${box.h}`, width, height,
                  version:"1.1", "xmlns:xlink":"http://www.w3.org/1999/xlink"});
  for(const n of copy.querySelectorAll("[style]")) n.removeAttribute("style");
  return copy;
}
async function renderCanvas(box, px, py){
  const text=new XMLSerializer().serializeToString(exportSvg(box, px, py));
  const img=new Image();
  await new Promise((ok,fail)=>{ img.onload=ok; img.onerror=fail;
    img.src="data:image/svg+xml;charset=utf-8,"+encodeURIComponent(text); });
  const cv=document.createElement("canvas"); cv.width=px; cv.height=py;
  const ctx=cv.getContext("2d");
  ctx.fillStyle=opts.matColor; ctx.fillRect(0,0,px,py);
  ctx.drawImage(img,0,0,px,py);
  return cv;
}
const canvasBlob=(cv,type,quality)=>new Promise(ok=>cv.toBlob(ok,type,quality));

async function exportMap(){
  flushRender();
  const fmt=EXPORT_TYPES[opts.exportFormat] ? opts.exportFormat : "png";
  const box=exportBox(), s=exportSize(box);
  if(fmt==="svg"){
    const unit=opts.exportUnit==="cm" ? "cm" : "in", k=unit==="cm" ? 2.54 : 1;
    const copy=exportSvg(box, `${fmtNum(s.inches*k)}${unit}`, `${fmtNum(s.heightIn*k)}${unit}`);
    const text='<?xml version="1.0" encoding="UTF-8"?>\n'+new XMLSerializer().serializeToString(copy);
    downloadBlob(new Blob([text],{type:"image/svg+xml"}), "minimappr.svg");
    return;
  }
  if(s.tooBig){ updateExportReadout(); return; }
  const button=$("#btnExport"); button.disabled=true;
  try{
    const cv=await renderCanvas(box, s.px, s.py);
    let blob, ext=EXPORT_TYPES[fmt].ext;
    if(fmt==="tiff") blob=tiffBlob(cv, s.dpi);
    else if(fmt==="pdf") blob=await pdfBlob(cv, s);
    else {
      blob=await canvasBlob(cv, EXPORT_TYPES[fmt].mime, 0.95);
      if(!blob) throw new Error("no image");
      if(fmt==="webp" && blob.type!=="image/webp"){
        // Browsers that cannot write WebP hand back a PNG instead.
        ext="png"; flashStage("This browser cannot write WebP; saved a PNG instead.");
      }
      if(blob.type==="image/png") blob=await pngWithDpi(blob, s.dpi);
      else if(blob.type==="image/jpeg") blob=await jpegWithDpi(blob, s.dpi);
    }
    downloadBlob(blob, "minimappr."+ext);
  }catch(e){
    $("#exportErr").textContent="The browser could not make this image. Try a smaller size, or SVG.";
  }finally{ button.disabled=false; }
}
function downloadBlob(blob,name){ const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download=name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000); }

/* resolution metadata, so the file opens at its print size */
const CRC_TABLE=(()=>{ const t=new Uint32Array(256);
  for(let n=0;n<256;n++){ let c=n; for(let k=0;k<8;k++) c=c&1 ? 0xedb88320^(c>>>1) : c>>>1; t[n]=c>>>0; }
  return t; })();
function crc32(bytes){ let c=0xffffffff; for(const b of bytes) c=CRC_TABLE[(c^b)&255]^(c>>>8); return (c^0xffffffff)>>>0; }
// A pHYs chunk (pixels per metre) after the header chunk, replacing any.
async function pngWithDpi(blob, dpi){
  const src=new Uint8Array(await blob.arrayBuffer());
  const chunk=new Uint8Array(21), view=new DataView(chunk.buffer), ppm=Math.round(dpi/0.0254);
  view.setUint32(0,9); chunk.set([0x70,0x48,0x59,0x73],4);   // "pHYs"
  view.setUint32(8,ppm); view.setUint32(12,ppm); chunk[16]=1;   // unit: metre
  view.setUint32(17, crc32(chunk.subarray(4,17)));
  const parts=[src.subarray(0,33), chunk];   // signature + IHDR, then pHYs
  for(let at=33; at<src.length;){
    const len=new DataView(src.buffer, at, 4).getUint32(0), end=at+12+len;
    if(String.fromCharCode(...src.subarray(at+4,at+8))!=="pHYs") parts.push(src.subarray(at,end));
    at=end;
  }
  return new Blob(parts,{type:"image/png"});
}
// The JFIF header's density, in dots per inch; one is added if missing.
async function jpegWithDpi(blob, dpi){
  const src=new Uint8Array(await blob.arrayBuffer());
  const d=Math.min(65535, Math.round(dpi));
  const jfif=src[2]===0xff && src[3]===0xe0 && String.fromCharCode(...src.subarray(6,10))==="JFIF";
  if(jfif){
    const out=src.slice(); out[13]=1; out[14]=d>>8; out[15]=d&255; out[16]=d>>8; out[17]=d&255;
    return new Blob([out],{type:"image/jpeg"});
  }
  const app0=new Uint8Array([0xff,0xe0,0,16,0x4a,0x46,0x49,0x46,0,1,1,1,d>>8,d&255,d>>8,d&255,0,0]);
  return new Blob([src.subarray(0,2), app0, src.subarray(2)],{type:"image/jpeg"});
}

/* TIFF: baseline RGB, PackBits-compressed, with its resolution in inches */
function packBitsRow(src, start, end, out, at){
  let i=start;
  while(i<end){
    let j=i+1;
    while(j<end && j-i<128 && src[j]===src[i]) j++;
    if(j-i>=2){ out[at++]=257-(j-i); out[at++]=src[i]; i=j; continue; }
    let k=i;
    while(k<end && k-i<128 && !(k+2<end && src[k]===src[k+1] && src[k]===src[k+2])) k++;
    out[at++]=k-i-1;
    while(i<k) out[at++]=src[i++];
  }
  return at;
}
function tiffBlob(cv, dpi){
  const w=cv.width, h=cv.height;
  const rgba=cv.getContext("2d").getImageData(0,0,w,h).data;
  const rowLen=w*3, rowsPerStrip=Math.max(1, Math.floor(65536/rowLen));
  const row=new Uint8Array(rowLen), packed=new Uint8Array(rowLen+Math.ceil(rowLen/128)+2);
  const strips=[], counts=[];
  for(let y=0;y<h;y+=rowsPerStrip){
    const pieces=[]; let size=0;
    for(let r=y;r<Math.min(h,y+rowsPerStrip);r++){
      for(let x=0, s=r*w*4, d=0; x<w; x++, s+=4){ row[d++]=rgba[s]; row[d++]=rgba[s+1]; row[d++]=rgba[s+2]; }
      const n=packBitsRow(row, 0, rowLen, packed, 0);
      pieces.push(packed.slice(0,n)); size+=n;
    }
    strips.push(pieces); counts.push(size);
  }
  const n=strips.length, dataLen=counts.reduce((a,b)=>a+b,0);
  // header, strip data, then the directory and the values too big for it
  const tags=[[256,4,1,w],[257,4,1,h],[258,3,3,null],[259,3,1,32773],[262,3,1,2],
    [273,4,n,null],[277,3,1,3],[278,4,1,rowsPerStrip],[279,4,n,null],
    [282,5,1,null],[283,5,1,null],[284,3,1,1],[296,3,1,2]];
  let ifd=8+dataLen; if(ifd%2) ifd++;
  const extra=ifd+2+tags.length*12+4;
  const bps=extra, offs=bps+6, cnts=offs+(n>1?4*n:0), xres=cnts+(n>1?4*n:0), yres=xres+8;
  const buf=new ArrayBuffer(yres+8), v=new DataView(buf), bytes=new Uint8Array(buf);
  v.setUint16(0,0x4949); v.setUint16(2,42,true); v.setUint32(4,ifd,true);
  let at=8; const stripOffsets=[];
  for(const pieces of strips){ stripOffsets.push(at); for(const p of pieces){ bytes.set(p,at); at+=p.length; } }
  v.setUint16(ifd,tags.length,true);
  const res=Math.round(dpi*100);
  tags.forEach(([tag,type,count,value],i)=>{
    const e=ifd+2+i*12;
    v.setUint16(e,tag,true); v.setUint16(e+2,type,true); v.setUint32(e+4,count,true);
    if(tag===258) v.setUint32(e+8,bps,true);
    else if(tag===273) v.setUint32(e+8, n>1 ? offs : stripOffsets[0], true);
    else if(tag===279) v.setUint32(e+8, n>1 ? cnts : counts[0], true);
    else if(tag===282) v.setUint32(e+8,xres,true);
    else if(tag===283) v.setUint32(e+8,yres,true);
    else if(type===3) v.setUint16(e+8,value,true);
    else v.setUint32(e+8,value,true);
  });
  v.setUint32(ifd+2+tags.length*12,0,true);   // no next directory
  for(let i=0;i<3;i++) v.setUint16(bps+2*i,8,true);
  if(n>1) for(let i=0;i<n;i++){ v.setUint32(offs+4*i,stripOffsets[i],true); v.setUint32(cnts+4*i,counts[i],true); }
  for(const at_ of [xres,yres]){ v.setUint32(at_,res,true); v.setUint32(at_+4,100,true); }
  return new Blob([buf],{type:"image/tiff"});
}

/* PDF: one page at the print size holding the map as an image */
async function pdfBlob(cv, s){
  const w=cv.width, h=cv.height;
  let data, filter;
  if(typeof CompressionStream==="function"){
    const rgba=cv.getContext("2d").getImageData(0,0,w,h).data, rgb=new Uint8Array(w*h*3);
    for(let i=0,j=0;i<rgba.length;i+=4){ rgb[j++]=rgba[i]; rgb[j++]=rgba[i+1]; rgb[j++]=rgba[i+2]; }
    const zipped=new Blob([rgb]).stream().pipeThrough(new CompressionStream("deflate"));
    data=new Uint8Array(await new Response(zipped).arrayBuffer()); filter="FlateDecode";
  } else {
    data=new Uint8Array(await (await canvasBlob(cv,"image/jpeg",0.95)).arrayBuffer()); filter="DCTDecode";
  }
  const pw=fmtNum(s.inches*72), ph=fmtNum(s.heightIn*72);
  const content=`q ${pw} 0 0 ${ph} 0 0 cm /Im0 Do Q`;
  const enc=new TextEncoder(), parts=[], offsets=[];
  let size=0;
  const put=p=>{ const b=typeof p==="string" ? enc.encode(p) : p; parts.push(b); size+=b.length; };
  const obj=(n,body)=>{ offsets[n]=size; put(`${n} 0 obj\n${body}\nendobj\n`); };
  put("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n");
  obj(1,"<< /Type /Catalog /Pages 2 0 R >>");
  obj(2,"<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  obj(3,`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pw} ${ph}] `
    +"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>");
  offsets[4]=size;
  put(`4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${w} /Height ${h} /ColorSpace /DeviceRGB `
    +`/BitsPerComponent 8 /Filter /${filter} /Length ${data.length} >>\nstream\n`);
  put(data); put("\nendstream\nendobj\n");
  obj(5,`<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  const xref=size;
  put("xref\n0 6\n0000000000 65535 f \n"
    +offsets.slice(1).map(o=>String(o).padStart(10,"0")+" 00000 n \n").join(""));
  put(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(parts,{type:"application/pdf"});
}

$("#btnExport").addEventListener("click", exportMap);
