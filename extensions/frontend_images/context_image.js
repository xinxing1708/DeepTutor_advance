function j({name:e,alt:t,className:r}){
  const context=n.useContext(f),file=context?.resolve(e);
  if(!file?.url)return l.jsx(l.Fragment,{children:t||file?.filename||e});
  const image=l.jsx("img",{
    src:file.url,alt:t||file.title||file.filename||e,loading:"lazy",className:r,
    style:{display:"block",maxWidth:"100%",height:"auto"},
    onLoad:event=>{if(event.currentTarget.naturalWidth>0)context.markImageLoaded?.(file.url,true)},
    onError:()=>context.markImageLoaded?.(file.url,false)
  });
  return context.onOpen?l.jsx("button",{
    type:"button",onClick:()=>context.onOpen(file),
    className:"block max-w-full cursor-zoom-in text-left",
    style:{display:"block",maxWidth:"100%",margin:"12px 0"},
    "aria-label":`Open ${file.filename||e}`,children:image
  }):image;
}
