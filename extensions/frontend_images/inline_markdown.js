59347:(module,exports,require)=>{
  "use strict";
  require.r(exports); require.d(exports,{default:()=>InlineMarkdown});
  const jsx=require(95155), React=require(12115), Markdown=require(52191);
  const gfm=require(84678), math=require(89273), files=require(17174), urls=require(43766);
  const Mermaid=React.lazy(()=>require.e(6896).then(()=>require(57306)).then(module=>({default:module.Mermaid})));
  require(84559);
  function normalizeDiagrams(content){
    // Some models double-escape newlines in question tool arguments. Repair
    // only explicit Mermaid fences; mathematical backslashes stay untouched.
    return String(content).replace(/(?:\\n)*```mermaid\\n([\s\S]*?)```(?:\\n)*/g,(_,source)=>'\n\n```mermaid\n'+source.replace(/\\n/g,'\n').replace(/\\"/g,'"')+'\n```\n\n');
  }
  const components={
    p:({children})=>jsx.jsx(jsx.Fragment,{children}),
    h1:({children})=>jsx.jsx("strong",{children}),
    h2:({children})=>jsx.jsx("strong",{children}),
    h3:({children})=>jsx.jsx("strong",{children}),
    code:({children,className})=>/\blanguage-mermaid\b/.test(className||"")
      ?jsx.jsx(React.Suspense,{fallback:jsx.jsx("span",{children:"正在绘图…"}),children:jsx.jsx(Mermaid,{chart:String(children).replace(/\n$/,"")})})
      :jsx.jsx("code",{className:className||"rounded bg-[color-mix(in_srgb,var(--foreground)_8%,transparent)] px-1 py-px font-mono text-[0.92em]",children}),
    pre:({children})=>jsx.jsx((Array.isArray(children)?children:[children]).some(child=>/\blanguage-mermaid\b/.test(child?.props?.className||""))?"div":"pre",{style:{margin:"12px 0",whiteSpace:"pre-wrap",overflowX:"auto"},children}),
    a:({href,children})=>{
      const name=files.Ah(href);
      return name?jsx.jsx(files.M7,{name,fallback:children}):jsx.jsx("span",{className:"underline underline-offset-2",children});
    },
    img:({src,alt})=>{
      const name=files.Ah(src);
      return name?jsx.jsx(files.E_,{name,alt:alt||"",className:"block h-auto max-w-full rounded-lg border border-[var(--border)]"}):jsx.jsx("img",{src,alt:alt||"",loading:"lazy",style:{display:"block",maxWidth:"100%",height:"auto",margin:"12px 0"}});
    },
    br:()=>jsx.jsx("span",{children:" "})
  };
  function InlineMarkdown({content}){
    const [plugins,setPlugins]=React.useState({});
    const context=files.Gm();
    const attachmentPlugin=React.useMemo(()=>files.K9(context?.files??[]),[context?.files]);
    React.useEffect(()=>{
      let cancelled=false;
      (async()=>{
        const [remark,rehype]=await Promise.all([require.e(9365).then(require.bind(require,49365)),Promise.all([require.e(7330),require.e(6202)]).then(require.bind(require,46202))]);
        if(!cancelled)setPlugins({remarkMath:remark.default,rehypeKatex:rehype.default});
      })();
      return()=>{cancelled=true};
    },[]);
    const remarkPlugins=[gfm.A];
    if(plugins.remarkMath)remarkPlugins.push(plugins.remarkMath);
    if(attachmentPlugin)remarkPlugins.push(attachmentPlugin);
    return jsx.jsx(Markdown.oz,{remarkPlugins,rehypePlugins:plugins.rehypeKatex?[plugins.rehypeKatex]:[],components,urlTransform:urls.t9,children:math.HS(normalizeDiagrams(content))});
  }
}
