"""Evidence-backed review state, separate from the original question grades."""
from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from deeptutor.services.session.quiz_context import _branch, _questions


def ledger_path() -> Path:
    from deeptutor.services.path_service import get_path_service
    return get_path_service().get_user_root() / "learning_review.db"


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reviews (
                identity TEXT PRIMARY KEY, source_session TEXT NOT NULL,
                entry_id INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'unknown',
                evidence_session TEXT NOT NULL DEFAULT '', evidence_message INTEGER,
                evidence TEXT NOT NULL DEFAULT '', pending_turn TEXT NOT NULL DEFAULT '',
                pending_session TEXT NOT NULL DEFAULT '', pending_evidence TEXT NOT NULL DEFAULT '',
                confirmed_message INTEGER, confirmed_session TEXT NOT NULL DEFAULT '')""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, identity: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM reviews WHERE identity=?", (identity,)).fetchone()
        return dict(row) if row else {"state": "unknown"}

    def stage(self, entry: dict, session_id: str, turn_id: str, evidence: str):
        with self.connect() as db:
            db.execute("""INSERT INTO reviews(identity,source_session,entry_id,pending_turn,pending_session,pending_evidence)
                VALUES(?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET
                pending_turn=excluded.pending_turn,pending_session=excluded.pending_session,pending_evidence=excluded.pending_evidence""",
                (identity(entry), entry['session_id'], entry['id'], turn_id, session_id, evidence))

    async def reconcile(self, store):
        with self.connect() as db:
            pending = [dict(r) for r in db.execute("SELECT * FROM reviews WHERE pending_turn<>''")]
        for row in pending:
            turn = await store.get_turn(row['pending_turn'])
            if not turn or turn.get('status') in ('queued', 'running', 'waiting_input'):
                continue
            mid = turn.get('assistant_message_id')
            messages = await store.get_messages(row['pending_session']) if mid else []
            message = next((m for m in messages if str(m['id']) == str(mid)), {})
            complete = turn.get('status') == 'completed' and row['pending_evidence'] in str(message.get('content') or '')
            with self.connect() as db:
                if complete:
                    db.execute("""UPDATE reviews SET state='explained',evidence_session=?,evidence_message=?,evidence=?,
                        confirmed_message=NULL,confirmed_session='' WHERE identity=? AND pending_turn=?""",
                        (row['pending_session'], mid, row['pending_evidence'], row['identity'], row['pending_turn']))
                db.execute("""UPDATE reviews SET pending_turn='',pending_session='',pending_evidence=''
                    WHERE identity=? AND pending_turn=?""", (row['identity'], row['pending_turn']))

    def confirm(self, entry, session_id, message_id):
        with self.connect() as db:
            db.execute("UPDATE reviews SET state='confirmed',confirmed_session=?,confirmed_message=? WHERE identity=? AND state IN ('explained','confirmed')",
                       (session_id, message_id, identity(entry)))

    def reopen(self, entry):
        with self.connect() as db:
            db.execute("UPDATE reviews SET state='needs_review',pending_turn='',confirmed_message=NULL,confirmed_session='' WHERE identity=?", (identity(entry),))


def identity(entry):
    return json.dumps([entry['session_id'], str(entry.get('turn_id') or ''), str(entry.get('question_id') or ''), int(entry['id'])], ensure_ascii=False)


async def current_path(store, session_id: str, turn_id: str = ''):
    rows = await store.get_messages(session_id)
    current = next((r for r in reversed(rows) if r.get('role') == 'user' and (r.get('metadata') or {}).get('turn_id') == turn_id), None) if turn_id else None
    if current:
        return _branch(rows, current['id'])
    session = await store.get_session(session_id) or {}
    return selected_branch(rows, (session.get('preferences') or {}).get('selected_branches') or {})


def selected_branch(rows, selections):
    """Match the UI's saved choices and longest-branch/latest-child fallback."""
    children = {}
    key = lambda value: 'null' if value is None else str(value)
    for row in rows:
        children.setdefault(key(row.get('parent_message_id')), []).append(row)
    for values in children.values():
        values.sort(key=lambda row: int(row['id']))
    depths = {}
    def depth(mid):
        stack, visiting = [(str(mid), False)], set()
        while stack:
            ident, done = stack.pop()
            if ident in depths:
                continue
            if done:
                depths[ident] = max((1 + depths.get(str(c['id']), 0) for c in children.get(ident, [])), default=0)
                visiting.discard(ident)
            elif ident not in visiting:
                visiting.add(ident);stack.append((ident, True))
                stack.extend((str(c['id']), False) for c in children.get(ident, []) if str(c['id']) not in visiting)
        return depths.get(str(mid), 0)
    root = 'null'
    if root not in children and rows:
        ids = {str(row['id']) for row in rows}
        orphan = next((row for row in rows if key(row.get('parent_message_id')) not in ids), rows[0])
        root = key(orphan.get('parent_message_id'))
    path, seen = [], set()
    while root in children and root not in seen:
        seen.add(root)
        choices = children[root]
        chosen = next((row for row in choices if str(row['id']) == str(selections.get(root))), None)
        if chosen is None:
            chosen = max(choices, key=lambda row: (depth(row['id']), int(row['id'])))
        path.append(chosen);root = str(chosen['id'])
    return path


async def review_queue(store, ledger: Ledger, session_id: str, current_turn: str = '', source_turn: str = ''):
    session = await store.get_session(session_id)
    if not session or session.get('deleted_at'):
        raise ValueError('找不到可访问的原测验会话')
    path = await current_path(store, session_id, current_turn)
    quizzes = [m for m in path if m.get('role') == 'assistant' and m.get('capability') == 'deep_question']
    if not source_turn:
        quizzes = quizzes[-1:]
    rounds = []
    for quiz in quizzes:
        trace = await store.get_message_trace(session_id, quiz['id'], limit=1)
        tid = str((trace or {}).get('turn_id') or (quiz.get('metadata') or {}).get('turn_id') or '')
        if tid:
            events = quiz.get('events') or await store.get_turn_events(tid)
            rounds.append((tid, _questions(events)))
    if source_turn:
        rounds = [r for r in rounds if r[0] == source_turn]
        if not rounds:
            raise ValueError('该轮次不在选定会话分支中')
    elif rounds:
        rounds = rounds[-1:]
    entries, offset = [], 0
    while True:
        result = await store.list_notebook_entries(session_id=session_id, limit=100, offset=offset)
        items = result.get('items') or []
        entries.extend(items)
        offset += len(items)
        if not items or offset >= int(result.get('total') or offset):
            break
    await ledger.reconcile(store)
    output = []
    for tid, questions in rounds:
        by_question = {str(e.get('question_id')): e for e in entries if str(e.get('turn_id') or '') == tid}
        if not by_question:
            continue  # A freshly generated, wholly unanswered quiz is not a review queue.
        for qid in questions:
            e = by_question.get(qid)
            if not e:
                # The native bank has no row for a blank answer. Keep it as
                # unanswered rather than inventing a failed attempt or grade.
                stable = json.dumps([session_id, tid, qid], ensure_ascii=False)
                virtual_id = -int(hashlib.sha256(stable.encode()).hexdigest()[:12], 16)
                e = {**questions[qid], 'id': virtual_id, 'session_id': session_id,
                     'turn_id': tid, 'question_id': qid, 'is_correct': None,
                     'user_answer': '', 'attempt_count': 0, 'unanswered': True}
            if e.get('is_correct') or not (e.get('unanswered') or e.get('attempt_count') or str(e.get('user_answer') or '').strip()):
                continue
            row = dict(e)
            state = ledger.get(identity(e))
            # Evidence on a discarded sibling does not advance this branch.
            if state.get('evidence_session') == session_id and state.get('evidence_message') not in {m['id'] for m in path}:
                state = {'state': 'unknown'}
            elif state.get('state') == 'confirmed' and state.get('confirmed_session') == session_id and state.get('confirmed_message') not in {m['id'] for m in path}:
                state = {**state, 'state': 'explained'}
            row['review'] = state
            output.append(row)
    return output
