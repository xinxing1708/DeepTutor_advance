const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const {parse} = require('@babel/parser');
const root = path.resolve(process.argv[2] || path.join(__dirname, 'patched-1.6.14'));
const source = fs.readFileSync(path.join(root, '5454-4d40eaa9bc3b8f82.js'), 'utf8');
let component;
function visit(node) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'VariableDeclarator' && node.id?.name === 'tn') {
    const fn = node.init?.arguments?.[0];
    if (fn?.type === 'FunctionExpression' && source.slice(fn.start, fn.start + 100).includes('onEdit:')) component = fn;
  }
  for (const value of Object.values(node)) Array.isArray(value) ? value.forEach(visit) : visit(value);
}
visit(parse(source));
assert(component, 'Locate actual UserMessage component');
const jsx = (type, props, key) => ({type, props: props || {}, key});
function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return null;
  if (predicate(tree)) return tree;
  const children = tree.props?.children;
  for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) {
    const match = find(child, predicate); if (match) return match;
  }
  return null;
}
function scenario(draft, blockedAfterOpen = false, submitByKey = false) {
  const state = [], calls = [];
  let cursor = 0;
  const context = {
    s:{useState(initial){const at=cursor++; if(!(at in state)) state[at]=typeof initial==='function'?initial():initial;
      return [state[at],value=>{state[at]=typeof value==='function'?value(state[at]):value;}];},useEffect(){}},
    r:{jsx,jsxs:jsx},u:{Bd:()=>({t:x=>x})},H:{S:()=>({isComposingRef:{current:false}})},
    G:{qX:()=> 'fixture'},Q:{F:()=>false},eO:{},eW:new Set(),e3:'ActionButton',A:{A:'EditIcon'},
  };
  const fn=vm.runInNewContext('('+source.slice(component.start,component.end)+')',context);
  const props={msg:{id:101,role:'user',content:'question'},index:0,onEdit:(...args)=>calls.push(args),editDisabled:false};
  const render=()=>{cursor=0; return fn(props);};
  find(render(),node=>node.props.label==='Edit').props.onClick();
  find(render(),node=>node.type==='textarea').props.onChange({target:{value:draft}});
  props.editDisabled=blockedAfterOpen;
  const tree=render();
  const send=find(tree,node=>node.type==='button'&&node.props.children==='Send');
  const expectedDisabled=!draft.trim()||blockedAfterOpen;
  assert.equal(send.props.disabled,expectedDisabled,`Send state for ${JSON.stringify(draft)}, blocked=${blockedAfterOpen}`);
  if(submitByKey) find(tree,node=>node.type==='textarea').props.onKeyDown({key:'Enter',ctrlKey:true,preventDefault(){}});
  else if(!send.props.disabled) send.props.onClick();
  assert.equal(calls.length,expectedDisabled?0:1,'Actual callback must match enabled state');
  if(calls.length) assert.deepEqual(calls[0],[101,draft.trim()]);
}
for(const draft of ['question','question changed','question ','  ','']) {
  scenario(draft);
  scenario(draft,false,true);
}
scenario('question changed',true);
scenario('question',true,true);
console.log('PASS: actual editor accepts unchanged and changed text; whitespace blocked; keyboard and in-flight guards agree');
