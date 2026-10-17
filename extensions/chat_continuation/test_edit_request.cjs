'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {parse} = require('@babel/parser');

// Execute the deployed edit callback itself, without loading React or a server.
const chunkRoot = path.resolve(process.argv[2] || path.join(__dirname, 'patched-1.6.14'));
const chunk = path.join(chunkRoot, '5750-4bc9c47d51f58f2e.js');
const source = fs.readFileSync(chunk, 'utf8');
const candidates = [];
const resolvers = [];
function walk(node) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'FunctionDeclaration' && node.id?.name === 'Y') resolvers.push(node);
  if (node.type === 'VariableDeclarator' && node.id.name === 'ej' &&
      node.init?.type === 'CallExpression' &&
      source.slice(node.init.start, node.init.end).includes('useCallback')) candidates.push(node.init);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(walk);
    else if (value && typeof value === 'object') walk(value);
  }
}
walk(parse(source));
assert.equal(candidates.length, 1, 'Identify exactly one real ej edit callback');
assert.equal(resolvers.length, 1, 'Identify exactly one real Y message resolver');
const callbackSource = source.slice(candidates[0].start, candidates[0].end);
const resolver = vm.runInNewContext('(' + source.slice(resolvers[0].start, resolvers[0].end) + ')');
const normalize = value => JSON.parse(JSON.stringify(value));
async function edit(message, content) {
  const sent = [];
  const messages = [message];
  const context = {
    R: {useCallback: fn => fn},
    o: {current: 1},
    r: {current: {selectedKey: 'session', sessions: {session: {sessionId: 'id', messages, isStreaming: false}}}},
    F: async () => messages,
    Y: async (rows, id, role) => {
      assert.equal(rows, messages);
      assert.equal(id, message.id);
      assert.equal(role, 'user');
      const resolved = await resolver(rows, id, role, async () => messages);
      assert.equal(resolved, message, 'Real Y must return the original message');
      assert.equal(resolved.requestSnapshot, message.requestSnapshot, 'Real Y must retain the complete original snapshot');
      return resolved;
    },
    V: (...args) => sent.push(args),
  };
  const callback = vm.runInNewContext(callbackSource, context, {filename: chunk});
  await callback(message.id, content);
  assert.equal(sent.length, 1, 'Edit must send exactly once');
  return sent[0];
}
async function main() {
  const quizSnapshot = {
    content: '原测验请求', capability: 'deep_question', config: {num_questions: 10, difficulty: 'medium'},
    llmSelection: {profile_id: 'original-provider', model_id: 'original-model'},
    knowledgeBases: ['original-kb'], enabledTools: ['web_search'],
    attachments: [{id: 'original-attachment'}], masteryAnswer: {answer: 'A'}, masterySkip: true,
  };
  const message = {id: 42, role: 'user', content: quizSnapshot.content, parentMessageId: 40, requestSnapshot: quizSnapshot};
  const before = JSON.stringify(message);
  const sent = await edit(message, '  改为关于数据库的题目  ');
  assert.equal(sent[0], '改为关于数据库的题目');
  assert.equal(sent[5].parentMessageId, 40, 'Original branch parent must survive editing');
  assert.ok(sent[5].requestSnapshotOverride, 'Edited quiz must pass the original request snapshot to V');
  assert.deepEqual(normalize(sent[5].requestSnapshotOverride), {
    ...quizSnapshot, content: sent[0], masteryAnswer: null, masterySkip: null,
  }, 'Preserve quiz count, capability, model, KB, tools and attachments while replacing content');
  assert.equal(JSON.stringify(message), before, 'Editing must not mutate the original message snapshot');

  const chatSnapshot = {...quizSnapshot, capability: 'chat', config: {}};
  const chat = await edit({...message, requestSnapshot: chatSnapshot, parentMessageId: null}, '普通聊天编辑');
  assert.deepEqual(normalize(chat[5].requestSnapshotOverride), {...chatSnapshot, content: '普通聊天编辑', masteryAnswer: null, masterySkip: null});
  assert.equal(chat[5].parentMessageId, null);

  const sameText = await edit(message, message.content);
  assert.equal(sameText[0], message.content, 'Unchanged text must still permit regeneration');
  assert.equal(sameText[5].requestSnapshotOverride.config.num_questions, 10);

  const legacy = await edit({id: 43, role: 'user', content: 'legacy'}, 'legacy edited');
  assert.equal(legacy[5].parentMessageId, null);
  assert.equal(legacy[5].requestSnapshotOverride, undefined, 'Legacy messages without snapshots retain the normal-send fallback');
  console.log('PASS: real ej callback preserves edited quiz/chat snapshots, same-text resends and legacy fallback');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
