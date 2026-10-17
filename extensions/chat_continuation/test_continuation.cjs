const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {parse} = require('@babel/parser');
const core = require('./continuation.cjs');
const sourceRoot = path.resolve(process.argv[2] || path.join(__dirname, 'patched-1.6.14'));
const source = name => fs.readFileSync(path.join(sourceRoot, name), 'utf8');
const snapshots = {llmSelection: {provider: 'fixture', model: 'fixture'}, knowledgeBases: ['original-kb']};
const error = {type:'error',content:'Disconnected',metadata:{turn_terminal:true,status:'failed',retryable:true}};
const text = content => ({type:'content',content,metadata:{}});
const done = {type:'done',metadata:{status:'completed'}};
const messages = [
  {id:1,role:'user',content:'Write 5 items',requestSnapshot:snapshots,parentMessageId:null},
  {id:2,role:'assistant',content:'Item 1\nItem 2\n',events:[text('Item 1\nItem 2\n'),error],capability:'chat',parentMessageId:1},
  {id:3,role:'user',content:core.instruction(2),parentMessageId:2},
  {id:4,role:'assistant',content:'Item 3\n',events:[text('Item 3\n'),{type:'progress',metadata:{assistant_content_offset:7}},error],capability:'chat',parentMessageId:3},
  {id:5,role:'user',content:core.instruction(4),parentMessageId:4},
  {id:6,role:'assistant',content:'Item 4\nItem 5',events:[text('Item 4\nItem 5'),done],capability:'chat',parentMessageId:5},
];
const before = JSON.stringify(messages);
const merged = core.merge(messages);
assert.equal(merged.length,2);
assert.equal(merged[1].content,'Item 1\nItem 2\nItem 3\nItem 4\nItem 5');
assert.equal(merged[1].id,6);
assert.equal(merged[1].parentMessageId,1);
assert.equal(merged[1].events.filter(event=>event.type==='error').length,0);
assert.equal(merged[1].events.find(event=>event.type==='progress').metadata.assistant_content_offset,21);
assert.equal(JSON.stringify(messages),before,'Must not overwrite original answer or trace');
assert.deepEqual(core.merge(JSON.parse(before)),merged,'Reloaded persisted rows must merge identically');
assert.equal(core.target(messages),null,'A continuation chain that completed normally offers no continue button');
assert.equal(core.target(messages.slice(0,4)).answer.id,4);
assert.equal(core.target(messages.slice(0,4)).user.requestSnapshot,snapshots);
const completed = [messages[0],{...messages[1],events:[text('Item 1\nItem 2\n'),{type:'result',metadata:{completed:true}},done]}];
assert.equal(core.target(completed),null,'Normally completed answer (persisted done) is not continuable');
assert.equal(core.target([messages[0],{...messages[1],events:[text('Item 1\nItem 2\n')]}]),null,'Live completed answer without terminal error is not continuable');
const cancelled = {type:'error',metadata:{turn_terminal:true,status:'cancelled',retryable:false}};
assert.equal(core.target([messages[0],{...messages[1],events:[text('Item 1'),cancelled,{type:'done',metadata:{status:'cancelled'}}]}]).answer.id,2,'Stopped answer remains continuable');
assert.equal(core.target([messages[0],{...messages[1],events:[text('Item 1'),{type:'done',metadata:{status:'failed'}}]}]).answer.id,2,'Failed done without error row remains continuable');
const failedAgain = [...messages.slice(0,4),{...messages[4]}, {...messages[5],content:'',events:[error]}];
assert.equal(core.target(failedAgain).answer.content,'Item 1\nItem 2\nItem 3\n');
assert.equal(core.merge(failedAgain)[1].events.at(-1),error,'Current failure remains visible');
assert.equal(core.target([{id:1,role:'user',content:'a'},{id:2,role:'assistant',content:'',events:[error]}]),null);
assert.equal(core.target([{...messages[0]},{...messages[1],id:-2}]),null,'Unreconciled turn cannot be continued');
assert.equal(core.target([{...messages[0]},{...messages[1],capability:'deep_research'}]),null);
assert.deepEqual(core.merge(messages.slice(0,2)),messages.slice(0,2),'Ordinary messages are unchanged');
const persistedBoundary = [
  {id:1,role:'user',content:'items'},
  {id:2,role:'assistant',content:'第1项\n第2项'},
  {id:3,role:'user',content:core.instruction(2)},
  {id:4,role:'assistant',content:'第3项\n第4项'},
];
assert.equal(core.merge(persistedBoundary)[1].content,'第1项\n第2项\n\n第3项\n第4项','Persisted blocks must not run together when backend trims leading whitespace');
assert.equal(core.merge(persistedBoundary.map(row=>row.id===2?{...row,content:'这句话尚未'}:row.id===4?{...row,content:'写完。'}:row))[1].content,'这句话尚未写完。','Mid-sentence continuation remains seamless');

function initializer(file,name) {
  const code=source(file),ast=parse(code);
  let found;
  function walk(node) {
    if (!node || typeof node!=='object') return;
    if(node.type==='VariableDeclarator'&&(node.id?.name===name||node.id?.type==='ObjectPattern'&&node.id.properties.some(property=>property.value?.name===name))&&
       (name!=='R'||code.slice(node.init.start,node.init.end).includes('dtContinueLib')))found=node.init;
    for(const value of Object.values(node))Array.isArray(value)?value.forEach(walk):walk(value);
  }
  walk(ast);
  assert(found,`Missing real deployed initializer ${name}`);
  return code.slice(found.start,found.end);
}
const composer='1551-18d1afe69149078f.js';
const dispatchCode=initializer(composer,'rS');
for(const mode of ['continue','retry',null]) {
  const calls=[];
  const dispatch=vm.runInNewContext(dispatchCode,{n:{useCallback:fn=>fn},dtRecovery:mode,dtOnContinue:()=>calls.push('continue'),dtOnRetry:()=>calls.push('retry'),rk:false,e1:()=>calls.push('config'),rN:mode===null,rf:text=>calls.push(text),rn:{current:{getValue:()=> 'new question'}}});
  dispatch();
  assert.deepEqual(calls,[mode??'new question']);
}
const code=source(composer);
assert(code.includes("dtRecovery=!t8&&!et.length&&!eG"),'Text, new attachments and running turns must override recovery');
assert(code.includes("'data-continuation-action':r_"));
assert(code.includes("d:'M7 4v16l13-8z',fill:'currentColor'"),'Continuation uses filled play triangle');
const listCode=initializer('5454-4d40eaa9bc3b8f82.js','R');
const list=vm.runInNewContext(listCode,{s:{useMemo:fn=>fn()},e:messages,b:{},n:'fixture-session-id',V:{a:rows=>({messages:rows,siblingsByMessageId:new Map()})},dtContinueLib:core});
assert.equal(list.messages.length,2,'Actual MessageList memo must merge persisted rows');
assert.equal(list.messages[1].content,merged[1].content);

const main='3450-849cf5416215cc1f.js';
const sendCode=initializer(main,'dtSendContinuation');
(async()=>{
  const calls=[];
  const W={isStreaming:false,sessionKey:'fixture'};
  const context={p:{useCallback:fn=>fn},dtTarget:core.target(messages.slice(0,2)),dtContinue:core,W,n3:false,tg:{current:null},Z:async(...args)=>calls.push(args),nY:{current:false},eC:{notify:error=>{throw Error(error)}},I:x=>x};
  const send=vm.runInNewContext(sendCode,context);
  await send();
  assert.equal(calls.length,1);
  assert.equal(calls[0][0],core.instruction(2));
  const options=calls[0][5];
  assert.equal(options.parentMessageId,2);
  assert.deepEqual(options.requestSnapshotOverride.llmSelection,snapshots.llmSelection);
  assert.deepEqual(options.requestSnapshotOverride.knowledgeBases,snapshots.knowledgeBases);
  assert.equal(options.requestSnapshotOverride.content,calls[0][0]);
  assert.equal(options.persistUserMessage,undefined,'Continuation association must be durable');
  W.isStreaming=true;
  await send();
  assert.equal(calls.length,1,'A running turn must not be duplicated');
  console.log('PASS: persisted continuation merge, failed/empty continuation, prefix immutability, reload, real composer dispatch, real send callback and original request settings');
})().catch(error=>{console.error(error);process.exitCode=1});
