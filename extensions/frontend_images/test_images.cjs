// Exercise the installed webpack modules, with only React hooks/JSX mocked.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {parse}=require('@babel/parser');
const root=process.argv[2]||path.join(__dirname,'../chat_continuation/patched-1.6.14');
const chunk=name=>fs.readFileSync(fs.existsSync(path.join(root,name))?path.join(root,name):path.join(root,'.next/static/chunks',name),'utf8');
const modules={};const sandbox={self:{webpackChunk_N_E:{push(row){Object.assign(modules,row[1]);}}}};
for(const name of ['9797-994ed73175354c60.js','9347.ef125ab74f4fc87d.js'])vm.runInNewContext(chunk(name),sandbox);
const jsx=(type,props)=>({type,props});let activeContext=null,states=[],cursor=0;
const React={createContext:()=>({Provider:'Provider'}),useContext:()=>activeContext,
  lazy:fn=>({lazy:fn}),Suspense:'Suspense',
  useState(initial){const index=cursor++;if(!(index in states))states[index]=typeof initial==='function'?initial():initial;return[states[index],value=>{states[index]=typeof value==='function'?value(states[index]):value}]},
  useMemo:fn=>fn(),useCallback:fn=>fn,useEffect:()=>{}};
const gfm=()=>{};const mocks={95155:{jsx,jsxs:jsx,Fragment:'Fragment'},12115:React,52191:{oz:'ReactMarkdown'},84678:{A:gfm},89273:{HS:x=>x},89513:{},25385:{xb:()=>({Icon:'File'})},84559:{},43766:{t9:x=>x}};
function req(id){if(id in mocks)return mocks[id];throw Error('Unexpected module '+id)}
req.d=(target,defs)=>{for(const[key,get]of Object.entries(defs))Object.defineProperty(target,key,{get,enumerable:true})};req.r=()=>{};
const files={};modules[17174]({},files,req);mocks[17174]=files;
const inline={};modules[59347]({},inline,req);
const fixtures=[{type:'image',origin:'workspace',generated:true,relative_path:'outputs/中文图.svg',filename:'中文图.svg',url:'/files/workspace-items/ws/wsi?dt_workspace=',mime_type:'image/svg+xml'},
  {type:'image',origin:'workspace',generated:true,relative_path:'outputs/unused.svg',filename:'unused.svg',url:'/files/workspace-items/ws/unused',mime_type:'image/svg+xml'}];
const provider=()=>{cursor=0;const tree=files.Vy({attachments:fixtures,events:[],onOpen:file=>opened.push(file),children:[]});activeContext=tree.props.value;return tree};
const opened=[];provider();cursor=1;
const renderer=inline.default({content:'题干\n![diagram](outputs/中文图.svg)'});
const ast={type:'root',children:[{type:'paragraph',children:[{type:'image',url:'outputs/中文图.svg',alt:'diagram'}]}]};
assert(renderer.props.remarkPlugins.some(plugin=>plugin!==gfm),'Question must include attachment path resolver');
renderer.props.remarkPlugins.filter(plugin=>plugin!==gfm).forEach(plugin=>plugin()(ast));
assert(ast.children[0].children[0].url.startsWith('attachment:'),'Question image path must resolve to registered attachment');
const imageElement=renderer.props.components.img({src:ast.children[0].children[0].url,alt:'diagram'});
assert.equal(imageElement.type,files.E_,'Question must use existing workspace image component');
const imageTree=files.E_(imageElement.props),image=imageTree.props.children;
assert.equal(image.props.src,fixtures[0].url,'Image must request canonical file endpoint');
imageTree.props.onClick();assert.equal(opened[0],fixtures[0],'Click opens correct file');
const source=chunk('5454-4d40eaa9bc3b8f82.js'),astMain=parse(source);let cardsNode;
function walk(node){if(!node||typeof node!=='object')return;if(node.type==='FunctionDeclaration'&&node.id?.name==='e5')cardsNode=node;for(const item of Object.values(node))Array.isArray(item)?item.forEach(walk):item&&typeof item==='object'&&walk(item)}walk(astMain);
assert(cardsNode);const cards=vm.runInNewContext('('+source.slice(cardsNode.start,cardsNode.end)+')',{u:{Bd:()=>({t:x=>x})},s:React,z:files,r:{jsx,jsxs:jsx},e1:file=>file.url,e2:x=>x,P:mocks[25385]});
const cardCount=()=>{const tree=cards({attachments:fixtures,events:[],onOpen:()=>{}});return tree?tree.props.children.length:0};
assert.equal(cardCount(),2,'Unloaded and unused images retain fallback');
image.props.onLoad({currentTarget:{naturalWidth:1100}});provider();assert.equal(cardCount(),1,'Successful inline image removed from trailing attachments');
image.props.onError();provider();assert.equal(cardCount(),2,'Failed inline image restores fallback');
image.props.onLoad({currentTarget:{naturalWidth:0}});provider();assert.equal(cardCount(),2,'Broken image never hides fallback');
const providerCall=[];walkProvider(astMain);
function walkProvider(node){if(!node||typeof node!=='object')return;if(node.type==='CallExpression'&&node.arguments?.[0]?.type==='MemberExpression'&&node.arguments[0].object?.name==='z'&&node.arguments[0].property?.name==='Vy')providerCall.push(source.slice(node.start,node.end));for(const item of Object.values(node))Array.isArray(item)?item.forEach(walkProvider):item&&typeof item==='object'&&walkProvider(item)}
assert(providerCall.some(call=>call.includes('(e4,')&&call.includes('(e5,')),'Body and fallback cards share attachment context');
// Run the deployed bootstrap too: Next's URL helper must receive real filenames.
const bootName='webpack-b9a1eccb0c94dba8-diagrams20261015r3.js';
assert.equal(chunk('webpack-b9a1eccb0c94dba8-images20261014r2.js'),chunk(bootName),'Legacy bootstrap name serves current bytes');
assert.equal(chunk('5454-4d40eaa9bc3b8f82-images20261014.js'),chunk('5454-4d40eaa9bc3b8f82.js'),'Legacy 5454 name serves current bytes');
const bootSandbox={self:{webpackChunk_N_E:[]},URL};
vm.runInNewContext(chunk(bootName),bootSandbox);
let deployedRequire;
bootSandbox.self.webpackChunk_N_E.push([[999999],{},req=>{deployedRequire=req}]);
for(const [id,name] of [[5454,'5454-4d40eaa9bc3b8f82.js'],[9347,'9347.ef125ab74f4fc87d.js'],[9797,'9797-994ed73175354c60.js'],[7306,'7306.9daf7ebd715d14a3.js'],[6896,'6896-441cf43825adeefb.js']]){
  const alias=name.slice(0,-3)+(id===5454?'-continue20261015.js':id===7306?'-diagrams20261015r3.js':id===9347||id===6896?'-diagrams20261015r2.js':'-images20261014.js');
  assert.equal(deployedRequire.u(id),'static/chunks/'+alias,'Lazy loader must use cache-busting filename');
  assert.equal(deployedRequire.tu(deployedRequire.p+deployedRequire.u(id)),'/_next/static/chunks/'+alias,'Script URL must not contain an encoded query');
  assert.equal(chunk(alias),chunk(name),'Alias must contain the deployed patch');
}
assert.equal(chunk(bootName),chunk('webpack-b9a1eccb0c94dba8.js'));
console.log('PASS: question path resolution, canonical image URL, zoom, loaded-image dedup, unused-image preservation, error fallback, shared context, bootstrap/lazy cache aliases');
