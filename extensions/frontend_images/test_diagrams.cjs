const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=process.argv[2]||path.join(__dirname,'../chat_continuation/patched-1.6.14');
const modules={},jsx=(type,props)=>({type,props});
const chunk=name=>fs.readFileSync(path.join(root,name),'utf8');
const sandbox={self:{webpackChunk_N_E:{push:r=>Object.assign(modules,r[1])}}};
for(const name of ['6896-441cf43825adeefb.js','9347.ef125ab74f4fc87d.js'])vm.runInNewContext(chunk(name),sandbox);
const mocks={95155:{jsx,jsxs:jsx,Fragment:'Fragment'},12115:{lazy:fn=>({lazy:fn}),Suspense:'Suspense',useState:v=>[v,()=>{}],useMemo:fn=>fn(),useEffect:()=>{}},47650:{},68929:{},52191:{oz:'Markdown'},84678:{A:()=>{}},89273:{HS:x=>x},17174:{Gm:()=>null,K9:()=>null},43766:{t9:x=>x},84559:{}};
const req=id=>mocks[id];req.r=()=>{};req.d=(t,d)=>{for(const[k,get]of Object.entries(d))Object.defineProperty(t,k,{get})};
const viewer={};modules[57306]({},viewer,req);
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'diagram-fixture.json'),'utf8'));
assert.equal(viewer.splitCharts(fixture.chart).length,5,'Historical five independent graphs must separate');
// The full chat body loads the same module from a separate webpack chunk.
// Test that deployed entry, not only the card's viewer dependency.
const bodyModules={};
vm.runInNewContext(chunk('7306.9daf7ebd715d14a3.js'),{self:{webpackChunk_N_E:{push:r=>Object.assign(bodyModules,r[1])}}});
const bodyViewer={};bodyModules[57306]({},bodyViewer,req);
assert.equal(typeof bodyViewer.splitCharts,'function','Full chat body must expose the patched viewer');
assert.equal(bodyViewer.splitCharts(fixture.chart).length,5,'Full chat body must split historical five graphs');
assert.equal(bodyViewer.Mermaid.toString(),viewer.Mermaid.toString(),'Body and card viewers must use identical implementation');
assert.equal(typeof bodyModules[68929],'function','Keep the body chunk theme module');
const connected='flowchart LR\nsubgraph S1\nA-->B\nend\nsubgraph S2\nC-->D\nend\nB-->C';
assert.equal(viewer.splitCharts(connected).length,1,'Cross-subgraph edges must stay intact');
const shared='flowchart LR\nsubgraph S1\nA-->B\nend\nsubgraph S2\nB-->C\nend';
assert.equal(viewer.splitCharts(shared).length,1,'Shared edge endpoint must stay intact');
const inline={};modules[59347]({},inline,req);
const renderer=inline.default({content:'diagram'}).props.components;
assert.equal(renderer.code({className:'language-mermaid',children:'flowchart LR\nA-->B'}).type,'Suspense');
assert.equal(renderer.code({className:'language-python',children:'print(1)'}).type,'code');
assert.equal(renderer.pre({children:{props:{className:'language-mermaid'}}}).type,'div');
assert.equal(renderer.pre({children:{props:{className:'language-python'}}}).type,'pre');
const escaped=inline.default({content:'题目\\n\\n```mermaid\\nflowchart LR\\nA[\\"实体\\"]-->B\\n```\\n公式 \\frac{1}{2}'}).props.children;
assert(escaped.includes('```mermaid\nflowchart LR\nA["实体"]-->B'));
assert(escaped.includes('\\frac{1}{2}'),'Mathematical escapes remain intact');
// XML repair: both compiled entries must parse the rendered markup as an HTML
// fragment and verify the serialised result, instead of trusting a failed strict
// parse of the raw render output.
for(const [label,src] of [['card',chunk('6896-441cf43825adeefb.js')],['body',chunk('7306.9daf7ebd715d14a3.js')]]){
  assert(src.includes('parseMermaidSvgFragment('),`${label} entry must use the HTML fragment parser`);
  assert(src.includes('assertSerializedSvgIsValid('),`${label} entry must verify serialized XML`);
  assert(!src.includes('parseFromString(svg,"image/svg+xml")'),`${label} entry must not strict-parse the raw render output`);
  assert(src.includes('securityLevel:"strict"'),`${label} entry must keep securityLevel strict`);
}
assert.equal(viewer.parseMermaidSvgFragment,undefined,'helpers stay module-internal');
console.log('PASS: real modules render Mermaid cards, split historical five graphs, preserve connected topology and ordinary code');
