function v({attachments:e,events:t,onOpen:r,children:a}){
  const s=n.useMemo(()=>m(e,t),[e,t]);
  const [loadedImages,setLoadedImages]=n.useState(()=>new Set());
  const markImageLoaded=n.useCallback((url,loaded)=>{
    setLoadedImages(previous=>{
      if(previous.has(url)===loaded)return previous;
      const next=new Set(previous);
      if(loaded)next.add(url);else next.delete(url);
      return next;
    });
  },[]);
  const o=n.useMemo(()=>{
    const exact=new Map(),folded=new Map(),basename=new Map();
    for(const file of s){
      const name=file.origin==="workspace"?file.relative_path:file.filename;
      if(name){
        if(!exact.has(name))exact.set(name,file);
        if(!folded.has(b(name)))folded.set(b(name),file);
        if(file.origin!=="workspace"&&!basename.has(b(g(name))))basename.set(b(g(name)),file);
      }
    }
    return {files:s,resolve:name=>exact.get(name)??folded.get(b(name))??basename.get(b(g(name))),onOpen:r,loadedImages,markImageLoaded};
  },[s,r,loadedImages,markImageLoaded]);
  return l.jsx(f.Provider,{value:o,children:a});
}
