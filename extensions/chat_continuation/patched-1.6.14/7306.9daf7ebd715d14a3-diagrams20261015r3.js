"use strict";(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[7306],{57306:(module,exports,require)=>{
  "use strict";
  require.r(exports);require.d(exports,{Mermaid:()=>Mermaid,default:()=>Mermaid,splitCharts:()=>splitCharts});
  const J=require(95155),R=require(12115),portal=require(47650),theme=require(68929);
  let engine=null,serial=0;
  const load=()=>engine||(engine=Promise.all([require.e(5958),require.e(3716),require.e(1812)]).then(require.bind(require,28776)).then(m=>m.default));
  const css=(name,fallback)=>getComputedStyle(document.documentElement).getPropertyValue(name).trim()||fallback;
  function splitCharts(chart){
    const lines=chart.trim().split(/\r?\n/);
    if(!/^\s*(flowchart|graph)\s+(TB|TD|LR|RL|BT)\s*$/.test(lines[0]||""))return[chart];
    let groups=[],outside=[],group=null,depth=0;
    for(const line of lines.slice(1)){
      if(/^\s*subgraph\b/.test(line)){
        if(depth===0)group=[];
        depth++;group.push(line);
      }else if(/^\s*end\s*$/.test(line)&&depth){
        group.push(line);if(--depth===0){groups.push(group);group=null;}
      }else if(depth)group.push(line);else outside.push(line);
    }
    if(depth||groups.length<2||outside.some(line=>line.trim()&&!/^\s*(%%|classDef\s|class\s)/.test(line)))return[chart];
    // Conservative: every edge endpoint belongs to just one group. Shared
    // endpoints or an outside edge mean the graph must retain its topology.
    const identifiers=groups.map(group=>{
      const ids=new Set();
      for(const line of group){
        if(/^\s*(subgraph|end|direction|classDef|class|%%)\b/.test(line))continue;
        const clean=line.replace(/"[^"]*"|\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|\|[^|]*\|/g," ").replace(/:::[\w-]+/g,"");
        for(const word of clean.matchAll(/\b[A-Za-z_][\w-]*\b/g))ids.add(word[0]);
      }
      return ids;
    });
    for(let i=0;i<identifiers.length;i++)for(let j=i+1;j<identifiers.length;j++)
      if([...identifiers[i]].some(id=>identifiers[j].has(id)))return[chart];
    return groups.map((group,index)=>{
      const suffix=outside.map(line=>{
        const match=line.match(/^\s*class\s+([\w, -]+)\s+([\w-]+)\s*;?$/);
        if(!match)return line;
        const ids=match[1].split(",").map(s=>s.trim()).filter(s=>identifiers[index].has(s));
        return ids.length?`class ${ids.join(",")} ${match[2]}`:"";
      });
      return[lines[0],...group,...suffix].join("\n");
    });
  }
  function readable(svg){
    const doc=new DOMParser().parseFromString(svg,"image/svg+xml"),root=doc.documentElement;
    const box=(root.getAttribute("viewBox")||"").split(/\s+/).map(Number);
    if(box.length===4&&box.every(Number.isFinite)){
      root.setAttribute("width",String(Math.ceil(box[2])));root.setAttribute("height",String(Math.ceil(box[3])));
      root.style.maxWidth="none";root.style.width=`${Math.ceil(box[2])}px`;root.style.height=`${Math.ceil(box[3])}px`;
    }
    for(const node of root.querySelectorAll("g.node")){
      const shape=node.querySelector("rect,circle,ellipse,polygon,path");
      const fill=shape?.style.fill||shape?.getAttribute("fill")||"";
      const hex=fill.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i),rgb=fill.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/);
      if(!hex&&!rgb)continue;
      let values;
      if(hex){let value=hex[1];if(value.length===3)value=[...value].map(c=>c+c).join("");values=[0,2,4].map(i=>parseInt(value.slice(i,i+2),16));}
      else values=rgb.slice(1).map(Number);
      const channels=values.map(c=>c/255).map(c=>c<=0.04045?c/12.92:((c+0.055)/1.055)**2.4);
      const luminance=channels[0]*0.2126+channels[1]*0.7152+channels[2]*0.0722;
      const color=luminance>0.179?"#171717":"#ffffff";
      for(const label of node.querySelectorAll("text,tspan,.nodeLabel,.nodeLabel *")){label.style.setProperty("fill",color,"important");label.style.setProperty("color",color,"important");}
    }
    return{svg:new XMLSerializer().serializeToString(root),width:box[2]||800,height:box[3]||500};
  }
  function cleanup(id){document.getElementById(id)?.remove();document.getElementById(`d${id}`)?.remove();}
  function Mermaid({chart,className=""}){
    const [diagrams,setDiagrams]=R.useState([]),[error,setError]=R.useState(null),[revision,setRevision]=R.useState(0);
    const [opened,setOpened]=R.useState(false),[zoom,setZoom]=R.useState(1),viewport=R.useRef(null),drag=R.useRef(null);
    const [base]=R.useState(()=>`dt-mermaid-${++serial}`);
    R.useEffect(()=>theme.GO(()=>setRevision(n=>n+1)),[]);
    R.useEffect(()=>{
      let cancelled=false;
      const timeout=window.setTimeout(async()=>{
        if(!chart?.trim()){setDiagrams([]);return;}
        try{
          const api=await load();
          api.initialize({startOnLoad:false,theme:"base",securityLevel:"strict",fontFamily:"ui-sans-serif, system-ui, sans-serif",
            flowchart:{useMaxWidth:false,htmlLabels:false,curve:"basis"},
            themeVariables:{primaryColor:css("--card","#ffffff"),primaryTextColor:css("--foreground","#1f1d1b"),primaryBorderColor:css("--border","#dbd4c8"),lineColor:css("--muted-foreground","#6b655f"),secondaryColor:css("--muted","#ece7dd"),tertiaryColor:css("--background","#faf9f6"),textColor:css("--foreground","#1f1d1b"),mainBkg:css("--card","#ffffff")}});
          const results=[];
          for(const [index,source] of splitCharts(chart).entries()){
            const id=`${base}-${revision}-${index}`;
            try{const result=await api.render(id,source);results.push(readable(result.svg));}finally{cleanup(id);}
          }
          if(!cancelled){setDiagrams(results);setError(null);}
        }catch(e){if(!cancelled){setDiagrams([]);setError(e instanceof Error?e.message:String(e));}}
      },350);
      return()=>{cancelled=true;window.clearTimeout(timeout);};
    },[chart,base,revision]);
    R.useEffect(()=>{
      if(!opened)return;
      const onKey=e=>{if(e.key==="Escape")setOpened(false);};
      document.addEventListener("keydown",onKey);
      return()=>document.removeEventListener("keydown",onKey);
    },[opened]);
    const button=(label,onClick)=>J.jsx("button",{type:"button",onClick,style:{border:"1px solid var(--border,#ccc)",borderRadius:6,padding:"5px 10px",background:"var(--card,#fff)",color:"var(--foreground,#222)",cursor:"pointer"},children:label});
    const draw=(diagram,index,scale)=>J.jsx("div",{style:{width:diagram.width*scale,height:diagram.height*scale,margin:"16px auto",position:"relative"},children:J.jsx("div",{style:{transform:`scale(${scale})`,transformOrigin:"top left",width:diagram.width,height:diagram.height},dangerouslySetInnerHTML:{__html:diagram.svg}})},index);
    const fit=()=>{const v=viewport.current;if(v&&diagrams.length)setZoom(Math.min(1,(v.clientWidth-48)/Math.max(...diagrams.map(d=>d.width))));};
    const modal=opened?portal.createPortal(J.jsxs("div",{role:"dialog","aria-modal":true,"aria-label":"图形查看器",style:{position:"fixed",inset:0,zIndex:10000,background:"var(--background,#fff)",color:"var(--foreground,#222)",display:"flex",flexDirection:"column"},children:[
      J.jsxs("div",{style:{display:"flex",gap:8,alignItems:"center",padding:12,borderBottom:"1px solid var(--border,#ccc)",flexWrap:"wrap"},children:[
        button("缩小",()=>setZoom(z=>Math.max(0.15,z/1.25))),button("放大",()=>setZoom(z=>Math.min(4,z*1.25))),button("适应宽度",fit),button("原始大小",()=>setZoom(1)),
        J.jsx("span",{children:`${Math.round(zoom*100)}% · 拖动查看 · Esc 关闭`}),button("关闭",()=>setOpened(false))]}),
      J.jsx("div",{ref:viewport,style:{overflow:"auto",flex:1,padding:24,cursor:"grab",touchAction:"pan-x pan-y"},
        onPointerDown:e=>{if(e.pointerType!=="mouse")return;drag.current={x:e.clientX,y:e.clientY,left:e.currentTarget.scrollLeft,top:e.currentTarget.scrollTop};e.currentTarget.setPointerCapture(e.pointerId);},
        onPointerMove:e=>{if(drag.current){e.currentTarget.scrollLeft=drag.current.left-(e.clientX-drag.current.x);e.currentTarget.scrollTop=drag.current.top-(e.clientY-drag.current.y);}},
        onPointerUp:()=>{drag.current=null;},onPointerCancel:()=>{drag.current=null;},children:diagrams.map((d,i)=>draw(d,i,zoom))})]}),document.body):null;
    if(error)return J.jsxs("div",{className,style:{padding:12,border:"1px solid #dc2626",borderRadius:8,whiteSpace:"normal"},children:[J.jsx("p",{children:"图形渲染失败"}),J.jsx("pre",{style:{whiteSpace:"pre-wrap",fontSize:12},children:error}),J.jsxs("details",{children:[J.jsx("summary",{children:"查看源码"}),J.jsx("pre",{style:{whiteSpace:"pre-wrap",overflow:"auto"},children:chart})]})]});
    return J.jsxs("div",{className,style:{display:"block",width:"100%",minWidth:0,margin:"16px 0",whiteSpace:"normal"},"data-diagram-viewer":true,children:[
      diagrams.length?button("放大查看图形",()=>{setZoom(1);setOpened(true);}):J.jsx("span",{children:"正在绘图…"}),
      ...diagrams.map((d,i)=>J.jsx("div",{style:{display:"block",maxWidth:"100%",overflowX:"auto",marginTop:12,border:"1px solid var(--border,#ddd)",borderRadius:8},children:draw(d,i,1)},i)),modal]});
  }
},68929:(e,r,t)=>{t.d(r,{$b:()=>i,GO:()=>o,VD:()=>l,Yl:()=>u});var a=t(90006);let n="deeptutor-theme",s=new Set;function o(e){return s.add(e),()=>s.delete(e)}function i(){try{let e=a.gr.readRaw("local",n);if("light"===e||"dark"===e||"glass"===e||"snow"===e)return e}catch(e){}return null}function l(){return window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"snow"}function u(e){!function(e){if("u"<typeof document)return;let r=document.documentElement;r.classList.remove("dark","theme-glass","theme-snow"),"dark"===e?r.classList.add("dark"):"glass"===e?r.classList.add("dark","theme-glass"):"snow"===e&&r.classList.add("theme-snow")}(e),function(e){try{a.gr.writeRaw("local",n,e)}catch(e){return!1}}(e),s.forEach(r=>r(e))}},90006:(e,r,t)=>{t.d(r,{gr:()=>u});let a="deeptutor:v2:";function n(e){return`${a}${e.scope}:${e.name}`}function s(e,r){var t;let a;try{a=JSON.parse(r)}catch{return{ok:!1,reason:"corrupt"}}if(!((t=a)&&"object"==typeof t&&!Array.isArray(t))||"number"!=typeof a.version)return{ok:!1,reason:"invalid"};if(a.version===e.version)return e.validate(a.value)?{ok:!0,value:a.value,migrated:!1}:{ok:!1,reason:"invalid"};let n=e.migrate?.(a.value,a.version)??null;return null!==n&&e.validate(n)?{ok:!0,value:n,migrated:!0}:{ok:!1,reason:"version"}}class o{constructor(e,r){this.providers=e,this.events=r}provider(e){return this.providers[e]}read(e){let r=this.provider(e.scope);if(!r)return e.fallback;try{let t=r.getItem(n(e));if(null===t)return e.fallback;let a=s(e,t);if(!a.ok)return e.fallback;return a.migrated&&this.write(e,a.value),a.value}catch{return e.fallback}}write(e,r){let t=this.provider(e.scope);if(!t||!e.validate(r))return!1;try{return t.setItem(n(e),function(e,r,t=Date.now()){return JSON.stringify({version:e.version,value:r,writtenAt:t})}(e,r)),!0}catch{return!1}}remove(e){let r=this.provider(e.scope);if(!r)return!1;try{return r.removeItem(n(e)),!0}catch{return!1}}readRaw(e,r){try{return this.provider(e)?.getItem(r)??null}catch{return null}}listRaw(e,r){let t=this.provider(e);if(!t)return[];try{let e=[];for(let a=0;a<t.length;a+=1){let n=t.key(a);n?.startsWith(r)&&e.push(n)}return e.flatMap(e=>{let r=t.getItem(e);return null===r?[]:[[e,r]]})}catch{return[]}}writeRaw(e,r,t){try{let a=this.provider(e);if(!a)return!1;return a.setItem(r,t),!0}catch{return!1}}removeRaw(e,r){try{let t=this.provider(e);if(!t)return!1;return t.removeItem(r),!0}catch{return!1}}clearNamespace(e,r=""){let t=this.provider(e);if(!t)return 0;let n=`${a}${e}:${r}`,s=[];try{for(let e=0;e<t.length;e+=1){let r=t.key(e);r?.startsWith(n)&&s.push(r)}for(let e of s)t.removeItem(e);return s.length}catch{return 0}}subscribe(e,r){let t=this.events;if(!t)return()=>void 0;let a=n(e),o=this.provider(e.scope),i=t=>{if(t.key!==a||t.storageArea&&o&&t.storageArea!==o)return;if(null===t.newValue)return void r(e.fallback);let n=s(e,t.newValue);n.ok&&r(n.value)};return t.addEventListener("storage",i),()=>t.removeEventListener("storage",i)}}function i(){let e,r;try{e=window.localStorage}catch{}try{r=window.sessionStorage}catch{}return new o({local:e,session:r},window)}class l extends o{constructor(){super({})}read(e){return i().read(e)}write(e,r){return i().write(e,r)}remove(e){return i().remove(e)}readRaw(e,r){return i().readRaw(e,r)}listRaw(e,r){return i().listRaw(e,r)}writeRaw(e,r,t){return i().writeRaw(e,r,t)}removeRaw(e,r){return i().removeRaw(e,r)}clearNamespace(e,r=""){return i().clearNamespace(e,r)}subscribe(e,r){return i().subscribe(e,r)}}let u=new l}}]);