'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {parse}=require('@babel/parser');
const core=require('./continuation.cjs');
const root=path.resolve(process.argv[2]||path.join(__dirname,'patched-1.6.14'));
function extract(file,predicate,initializer=false){
 const code=fs.readFileSync(path.join(root,file),'utf8'),found=[];
 function walk(node){if(!node||typeof node!=='object')return;if(predicate(node,code))found.push(initializer?node.init:node);for(const value of Object.values(node))Array.isArray(value)?value.forEach(walk):walk(value);}
 walk(parse(code));assert.equal(found.length,1,'Uniquely locate real patched expression');return code.slice(found[0].start,found[0].end);
}
const main='3450-849cf5416215cc1f.js';
const initializer=name=>extract(main,node=>node.type==='VariableDeclarator'&&node.id.name===name,true);
const targetCode=initializer('dtTarget'),sendCode=initializer('dtSendContinuation');
const renderCode=extract('5454-4d40eaa9bc3b8f82.js',(node,code)=>node.type==='CallExpression'&&node.callee.type==='MemberExpression'&&node.callee.property.name==='map'&&code.slice(node.callee.start,node.callee.end)==='dtContinueLib.quizSegments(e).map');
const qa=question=>({question_id:'q_1',question,question_type:'single_choice',options:['A','B'],correct_answer:'A'});
const first=qa('Original question'),second=qa('Additional question');
const emitted=(question,turn)=>({type:'content',turn_id:turn,metadata:{call_kind:'quiz_question_emitted',question_index:0,qa_pair:question}});
const snapshot={content:'Generate quiz',capability:'deep_question',config:{mode:'custom',num_questions:1,difficulty:'medium'},llmSelection:{profile_id:'original',model_id:'original-model'},knowledgeBases:['original-kb'],enabledTools:['web_search'],attachments:[{filename:'original.pdf',type:'file'}]};
const user={id:1,role:'user',content:snapshot.content,requestSnapshot:snapshot,parentMessageId:null};
const firstAnswer={id:2,role:'assistant',capability:'deep_question',content:'',events:[emitted(first,'turn-one')],parentMessageId:1};
const performance={id:5,role:'user',content:'[Quiz Performance]\nSaved score',parentMessageId:2};
const normalize=value=>JSON.parse(JSON.stringify(value));
async function send(rows){
 const calls=[];
 const context={p:{useMemo:fn=>fn(),useCallback:fn=>fn},dtContinue:core,dtBranches:{a:messages=>({messages})},W:{messages:rows,selectedBranches:{},isStreaming:false,sessionKey:'test'},ag:true,ar:{num_questions:10},n3:false,tg:{current:null},nY:{current:false},Z:async(...args)=>calls.push(args),I:text=>text,eC:{notify:error=>{throw Error(error)}}};
 context.dtTarget=vm.runInNewContext(targetCode,context);
 await vm.runInNewContext(sendCode,context)();
 assert.equal(calls.length,1);return {call:calls[0],target:context.dtTarget};
}
(async()=>{
 const original=JSON.stringify(snapshot);
 const {call,target}=await send([user,firstAnswer,performance]);
 assert.equal(target.remaining,9);assert.equal(call[2],undefined,'Do not override snapshot config with positional config');
 const options=call[5],saved=options.requestSnapshotOverride;
 assert.equal(options.parentMessageId,5,'Continue after persisted performance row');
 assert.equal(saved.capability,'deep_question');assert.equal(saved.config.num_questions,9);
 for(const key of ['llmSelection','knowledgeBases','enabledTools','attachments'])assert.deepEqual(normalize(saved[key]),snapshot[key],key+' must survive');
 assert.equal(saved.content,call[0]);assert.match(call[0],/^\[DeepTutor quiz continue v1:2:10\]\n/);
 assert.notEqual(options.persistUserMessage,false,'Marker must persist');assert.notEqual(options.displayUserMessage,false,'Marker must enter message history');
 assert.equal(JSON.stringify(snapshot),original);
 const control={id:3,role:'user',content:call[0],requestSnapshot:saved,parentMessageId:2};
 const next={id:4,role:'assistant',capability:'deep_question',content:'',parentMessageId:3,events:[{type:'result',turn_id:'turn-two',metadata:{summary:{results:[{qa_pair:second}]}}}]};
 const reloaded=normalize([user,firstAnswer,control,next]);
 const resumed=await send(reloaded);
 assert.equal(resumed.target.questions.length,2,'Duplicate q_1 belongs to independent turns');
 assert.equal(resumed.call[5].requestSnapshotOverride.config.num_questions,8);
 assert.match(resumed.call[0],/^\[DeepTutor quiz continue v1:4:10\]\n/);
 const merged=core.merge(reloaded).at(-1),rendered=[];
 // Stubs preserve the native parsers' input contracts; the real injected map chooses each segment's data.
 vm.runInNewContext(renderCode,{dtContinueLib:core,e:merged,W:{i_:metadata=>metadata.summary.results.map(row=>row.qa_pair??row),Ul:events=>events.filter(event=>event.metadata?.call_kind==='quiz_question_emitted').map(event=>event.metadata.qa_pair),Ld:events=>events.find(event=>event.type==='result'&&event.turn_id)?.turn_id??events.find(event=>event.turn_id)?.turn_id??null},r:{jsx:(component,props,key)=>{rendered.push({component,props,key});return props;}},eV:'QuizViewer',a:'session',i:'zh'});
 assert.equal(rendered.length,2);
 assert.deepEqual(rendered.map(row=>row.key),[2,4]);
 assert.deepEqual(rendered.map(row=>row.props.turnId),['turn-one','turn-two']);
 assert.deepEqual(rendered.map(row=>row.props.questions[0].question),[first.question,second.question]);
 assert(rendered.every(row=>row.component==='QuizViewer'&&row.props.questions.length===1));
 console.log('PASS: real quiz target/send callbacks preserve settings, request 9 then 8 remaining, persist markers and render two isolated QuizViewer segments');
})().catch(error=>{console.error(error);process.exitCode=1;});
