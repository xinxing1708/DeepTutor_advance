// Persist the continuation instruction through the existing durable turn API.
// The marker associates immutable answer segments across reloads and branches.
const marker = /^\[DeepTutor continue v1:([1-9]\d*)\]\n/;
const quizMarker = /^\[DeepTutor quiz continue v1:([1-9]\d*):([1-9]\d*)\]\n/;

function continuationInfo(message) {
  if (message?.role !== 'user') return null;
  const quiz = quizMarker.exec(message.content || '');
  if (quiz) return {id:Number(quiz[1]),kind:'quiz',total:Number(quiz[2])};
  const chat = marker.exec(message.content || '');
  return chat ? {id:Number(chat[1]),kind:'chat'} : null;
}

function continuationId(message) {
  return continuationInfo(message)?.id ?? null;
}

function instruction(id) {
  if (!Number.isSafeInteger(id) || id <= 0) throw Error('Invalid continuation target');
  return `[DeepTutor continue v1:${id}]\nContinue the preceding answer from exactly where it stopped. Preserve the original task, language and format. Output only the remaining content, without repeating the existing answer, restarting it, or adding a preamble. If it stopped mid-sentence, complete that sentence. Include any needed leading punctuation, spacing or newline. Do not repeat tool actions that have already completed. The first line of this instruction is an internal continuation marker; never include it in your answer.`;
}

function historicalEvents(events) {
  return (events || []).filter(event => event.type !== 'done' &&
    !(event.type === 'error' && event.metadata?.turn_terminal));
}

// Only a chat turn that ended without completing (provider failure, worker
// loss, user stop) has remaining content to continue. Live failures receive a
// terminal error from STREAM_END; persisted previews keep the terminal events.
function interrupted(message) {
  return (message.events || []).some(event =>
    (event.type === 'error' && event.metadata?.turn_terminal) ||
    (event.type === 'done' && ['failed','cancelled','rejected'].includes(event.metadata?.status)));
}

function separator(before, after) {
  if (!before || !after || /\s$/.test(before) || /^\s/.test(after)) return '';
  // AgentLoop trims final output. Restore a boundary for a new Markdown block
  // or a completed sentence while allowing interrupted sentences to join.
  return /^(?:#{1,6} |[-*+] |\d+[.)] |```|\| |第[\d一二三四五六七八九十百]+[项条节章])/.test(after) ||
    /(?:[。！？!?]|[^\d]\.)[”"')）]*$/.test(before) ? '\n\n' : '';
}

function merge(messages) {
  const output = [];
  const segmentPositions = new Map();
  for (let index = 0; index < messages.length; index++) {
    const message = messages[index];
    const info = continuationInfo(message);
    const target = info?.id ?? null;
    const next = messages[index + 1];
    const position = target === null ? undefined : segmentPositions.get(target);
    if (position !== undefined && next?.role === 'assistant' &&
        (next.parentMessageId == null || next.parentMessageId === message.id)) {
      const previous = output[position];
      const boundary = separator(previous.content || '', next.content || '');
      const offset = (previous.content || '').length + boundary.length;
      const events = (next.events || []).map(event => {
        const value = event.metadata?.assistant_content_offset;
        return typeof value === 'number' ? {
          ...event, metadata: {...event.metadata, assistant_content_offset: value + offset},
        } : event;
      });
      output[position] = {
        ...next,
        content: (previous.content || '') + boundary + (next.content || ''),
        rawContent: (previous.rawContent ?? previous.content ?? '') + boundary +
          (next.rawContent ?? next.content ?? ''),
        events: [...historicalEvents(previous.events), ...events],
        attachments: [...previous.attachments || [], ...next.attachments || []],
        parentMessageId: previous.parentMessageId,
        continuationRootId: previous.continuationRootId ?? previous.id,
        continuationSegmentIds: [...previous.continuationSegmentIds || [previous.id], next.id],
        ...(info.kind === 'quiz' ? {
          capability:'deep_question',
          continuationQuizTotal:info.total,
          continuationQuizSegments:[...quizSegments(previous), next],
        } : {}),
      };
      segmentPositions.set(next.id, position);
      index++;
      continue;
    }
    // A submitted control may briefly precede its streaming assistant row.
    if (position !== undefined && !next) continue;
    output.push(message);
    if (message.role === 'assistant') segmentPositions.set(message.id, output.length - 1);
  }
  return output;
}

function quizSegments(message) {
  return message.continuationQuizSegments || [message];
}

function quizQuestions(message) {
  const events = message.events || [];
  const result = events.find(event => event.type === 'result' && event.metadata?.summary);
  if (result) return (result.metadata.summary.results || []).map(row => row.qa_pair || row).filter(qa => qa?.question);
  const questions = new Map();
  for (const event of events) {
    const meta = event.metadata || {};
    if (event.type !== 'content' || meta.call_kind !== 'quiz_question_emitted' || !meta.qa_pair?.question) continue;
    questions.set(meta.qa_pair.question_id || String(meta.question_index), meta.qa_pair);
  }
  return [...questions.values()];
}

function target(messages, confirmedQuizConfig) {
  const visible = merge(messages);
  let index = visible.length - 1;
  while (index >= 0 && visible[index].role === 'user' && visible[index].content?.startsWith('[Quiz Performance]\n')) index--;
  const answer = visible[index];
  if (answer?.role !== 'assistant' || !Number.isSafeInteger(answer.id) || answer.id <= 0) return null;
  const user = [...visible.slice(0, index)].reverse().find(message => message.role === 'user' && !message.content?.startsWith('[Quiz Performance]\n'));
  if (!user || continuationId(user) !== null) return null;
  if (answer.capability === 'deep_question') {
    const originalConfig = user.requestSnapshot?.config || {};
    if ((originalConfig.mode || 'custom') !== 'custom') return null;
    const questions = quizSegments(answer).flatMap(quizQuestions);
    if (!questions.length) return null;
    const batch = Math.max(1, Math.min(50, Number(confirmedQuizConfig?.num_questions || originalConfig.num_questions || 1)));
    let total = answer.continuationQuizTotal || batch;
    if (questions.length >= total) total = questions.length + batch;
    return {answer,user,kind:'quiz',questions,total,remaining:Math.min(50,total-questions.length),parentMessageId:visible.at(-1).id};
  }
  if ((answer.capability && answer.capability !== 'chat') || !answer.content?.trim() || !interrupted(answer)) return null;
  return {answer,user,kind:'chat',parentMessageId:answer.id};
}

function request(value) {
  const original = value.user.requestSnapshot;
  if (value.kind !== 'quiz') {
    const text = instruction(value.answer.id);
    return {text,snapshot:original?{...original,content:text,attachments:[],capability:'chat',capabilityOnce:false,masteryAnswer:null,masterySkip:null}:undefined};
  }
  const text = `[DeepTutor quiz continue v1:${value.answer.id}:${value.total}]\nContinue the same quiz. Generate exactly ${value.remaining} additional questions to reach ${value.total} questions in total. Preserve the original topic, language, sources and constraints. Keep all existing questions unchanged and do not repeat them. Output the additional questions through the quiz workflow, not a prose explanation.\n\nOriginal request:\n${value.user.content}\n\nAlready generated questions (including unanswered ones; exclude these):\n${value.questions.map((qa,index)=>`${index+1}. ${qa.question}`).join('\n')}\n\nThe first line is an internal association marker; never reproduce it.`;
  const config = {...original?.config,mode:'custom',topic:'',num_questions:value.remaining};
  const counts = {...config.per_type_counts};
  for (const qa of value.questions) if (counts[qa.question_type] > 0) counts[qa.question_type]--;
  config.per_type_counts = Object.fromEntries(Object.entries(counts).filter(([,count])=>count>0));
  if (Object.values(config.per_type_counts).reduce((sum,count)=>sum+count,0) !== value.remaining) config.per_type_counts = {};
  return {text,snapshot:{...original,content:text,capability:'deep_question',capabilityOnce:false,config,masteryAnswer:null,masterySkip:null}};
}

module.exports = {continuationId, instruction, merge, target, request, quizSegments, quizQuestions};
