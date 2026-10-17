"""Recover complete quiz cards and attempts independently of prose history."""
from __future__ import annotations

from typing import Any


def format_question_detail(entry: dict[str, Any], *, include_solution: bool = True) -> str:
    """Keep option labels and their text together; never render letters alone."""
    lines = [
        f"### [{entry.get('id') or entry.get('question_id') or '?'}] Question",
        f"session_id: {entry.get('session_id', '')} | turn_id: {entry.get('turn_id', '')} | question_id: {entry.get('question_id', '')}",
        str(entry.get('question') or ''),
    ]
    options = entry.get('options') or {}
    if isinstance(options, dict):
        lines.extend(f"{key}. {value}" for key, value in options.items())
    answer = str(entry.get('user_answer') or '').strip()
    if answer:
        answer_text = options.get(answer, '') if isinstance(options, dict) else ''
        lines.append(f"User answer: {answer}" + (f" — {answer_text}" if answer_text else ''))
        lines.append(f"Result: {'correct' if entry.get('is_correct') else 'incorrect'}")
    else:
        lines.append('User answer: not recorded; do not assume this question was answered.')
    if include_solution:
        correct = str(entry.get('correct_answer') or '')
        correct_text = options.get(correct, '') if isinstance(options, dict) else ''
        lines.append(f"Reference answer: {correct}" + (f" — {correct_text}" if correct_text else ''))
        if entry.get('explanation'):
            lines.append('Explanation: ' + str(entry['explanation']))
    return '\n'.join(lines)


def _branch(rows: list[dict[str, Any]], leaf_message_id: int | str | None) -> list[dict[str, Any]]:
    if leaf_message_id is None:
        leaf_message_id = rows[-1]['id'] if rows else None
    by_id = {str(row['id']): row for row in rows}
    path, seen = [], set()
    current = str(leaf_message_id)
    while current in by_id and current not in seen:
        seen.add(current)
        row = by_id[current]
        path.append(row)
        current = str(row.get('parent_message_id'))
    return list(reversed(path))


def _questions(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    questions = {}
    for event in events:
        meta = event.get('metadata') or {}
        pairs = [meta['qa_pair']] if isinstance(meta.get('qa_pair'), dict) else []
        summary = meta.get('summary') or {}
        pairs.extend(
            item['qa_pair'] for item in summary.get('results', [])
            if isinstance(item, dict) and isinstance(item.get('qa_pair'), dict)
        )
        for pair in pairs:
            qid = str(pair.get('question_id') or '').strip()
            if qid and pair.get('question'):
                questions[qid] = dict(pair)
    return questions


async def resolve_quiz_result_parent(store: Any, session_id: str, parent_id: int | str) -> int | str:
    """An old client can submit its next chat against the pre-assessment tip."""
    rows = await store.get_messages(session_id)
    parent = next((r for r in rows if str(r['id']) == str(parent_id)), None)
    if not parent or parent.get('role') != 'assistant' or parent.get('capability') != 'deep_question':
        return parent_id
    # An existing substantive follow-up means this is a deliberate sibling
    # edit/branch. Preserve the caller's explicit parent in that case.
    if any(str(r.get('parent_message_id')) == str(parent_id) and r.get('role') == 'user'
           and not str(r.get('content') or '').startswith('[Quiz Performance]') for r in rows):
        return parent_id
    results = [
        r for r in rows if str(r.get('parent_message_id')) == str(parent_id)
        and r.get('role') == 'user' and str(r.get('content') or '').startswith('[Quiz Performance]')
    ]
    return results[-1]['id'] if results else parent_id


async def build_active_quiz_context(store: Any, session_id: str, leaf_message_id: int | str | None = None, *, parent_explicit: bool = False) -> str:
    """Use the latest quiz on this branch, with attempts scoped to its turn."""
    if parent_explicit and leaf_message_id is None:
        return ''
    rows = await store.get_messages(session_id)
    path = _branch(rows, leaf_message_id)
    quiz = next((r for r in reversed(path) if r.get('role') == 'assistant' and r.get('capability') == 'deep_question'), None)
    if not quiz:
        return ''
    turn_id = str((quiz.get('trace') or {}).get('turn_id') or (quiz.get('metadata') or {}).get('turn_id') or '')
    events = list(quiz.get('events') or [])
    if not turn_id:
        trace = await store.get_message_trace(session_id, quiz['id'], limit=1)
        turn_id = str((trace or {}).get('turn_id') or '')
    if not turn_id:
        return ''
    questions = _questions(events)
    if not questions:
        questions = _questions(await store.get_turn_events(turn_id))
    attempts, offset = {}, 0
    while True:
        result = await store.list_notebook_entries(session_id=session_id, limit=100, offset=offset)
        entries = result.get('items') or []
        for entry in entries:
            if str(entry.get('turn_id') or '') == turn_id:
                attempts[str(entry.get('question_id') or '')] = entry
        offset += len(entries)
        if not entries or offset >= int(result.get('total') or offset):
            break
    # Older records can lack result events but still have their saved cards.
    if not questions:
        questions = {qid: dict(entry) for qid, entry in attempts.items()}
    if not questions:
        return ''
    answered = sum(bool(str(attempts.get(qid, {}).get('user_answer') or '').strip()) for qid in questions)
    lines = [
        '[Active Quiz Context]',
        f'session_id: {session_id} | turn_id: {turn_id}',
        f'Recorded answers: {answered}/{len(questions)}. Question ids are scoped to this turn; do not mix earlier rounds.',
        'Use these exact saved options when reviewing answers. Do not ask the learner to paste options already included here.',
    ]
    for qid, question in questions.items():
        entry = {**question, **attempts.get(qid, {}), 'session_id': session_id, 'turn_id': turn_id, 'question_id': qid}
        # Generated cards are authoritative; partial attempts cannot erase
        # options or replace the text shown when the learner answered.
        if isinstance(question.get('options'), dict):
            attempt_options = attempts.get(qid, {}).get('options') or {}
            entry['options'] = {
                **(attempt_options if isinstance(attempt_options, dict) else {}),
                **question['options'],
            }
        lines.append(format_question_detail(entry, include_solution=bool(str(entry.get('user_answer') or '').strip())))
    return '\n\n'.join(lines)
