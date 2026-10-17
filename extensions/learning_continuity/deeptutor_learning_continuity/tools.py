from __future__ import annotations

import json
from typing import Any
from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.services.session.quiz_context import _branch, format_question_detail
from .state import Ledger, ledger_path, review_queue, selected_branch


def param(name, kind, description, required=False, enum=None):
    return ToolParameter(name=name, type=kind, description=description, required=required, enum=enum)


def store_for(kwargs):
    # Only the extension can supply this; model parameters never contain stores/paths.
    if kwargs.get('_store') is not None:
        return kwargs['_store']
    from deeptutor.services.session import get_session_store
    return get_session_store()


class ConversationSearch(BaseTool):
    def get_definition(self):
        return ToolDefinition('conversation_search', '检索当前工作区本地聊天标题与消息原文；返回会话ID、匹配消息ID和摘录。回忆此前学习、讲解与进度时先用它，随后 conversation_read 核实。', [
            param('query', 'string', '字面关键词，如课程名或独特题干；没有结果时缩短关键词', True),
            param('scope', 'string', 'current=当前会话；workspace=同一工作区其他会话', enum=['current', 'workspace']),
            param('limit', 'integer', '最多20个结果，默认8'), param('offset', 'integer', '分页偏移')])

    async def execute(self, **kwargs):
        store = store_for(kwargs)
        query = str(kwargs.get('query') or '').strip()[:200]
        limit = max(1, min(20, int(kwargs.get('limit') or 8)))
        offset = max(0, int(kwargs.get('offset') or 0))
        if not query:
            return ToolResult(content='请输入检索关键词', success=False)
        if kwargs.get('scope') == 'current':
            sid = str(kwargs.get('_session_id') or '')
            rows = await store.get_messages(sid)
            hits = [m for m in reversed(rows) if m.get('role') in ('user', 'assistant') and query.casefold() in str(m.get('content') or '').casefold()]
            sessions = [{'id': sid, 'match_message_id': m['id'], 'match_excerpt': excerpt(m['content'], query), 'match_role': m['role'], 'match_created_at': m.get('created_at')} for m in hits[offset:offset + limit]]
            result = {'total': len(hits), 'sessions': sessions}
        else:
            native = await store.search_sessions(query, limit=limit, offset=offset)
            result = {'total': native['total'], 'sessions': [{k: s.get(k) for k in ('id', 'title', 'created_at', 'updated_at', 'match_message_id', 'match_role', 'match_excerpt', 'match_created_at')} for s in native['sessions']]}
        result['note'] = '匹配可能位于旧分支；请用conversation_read核实。当前工作区内检索。'
        return ToolResult(content=json.dumps(result, ensure_ascii=False))


def excerpt(content, query):
    text = str(content)
    start = max(0, text.casefold().find(query.casefold()) - 120)
    return text[start:start + 360]


class ConversationRead(BaseTool):
    def get_definition(self):
        return ToolDefinition('conversation_read', '读取本地会话选定分支的消息原文，核实检索证据。默认当前活动分支；anchor_message_id用于查看历史匹配附近的原文，并明确标记旧分支。每条返回message_id。', [
            param('session_id', 'string', '从conversation_search返回的ID；省略为当前会话'),
            param('anchor_message_id', 'integer', '读取匹配消息和其祖先，禁止混入兄弟分支'),
            param('before_message_id', 'integer', '向前分页：读取此消息之前的祖先'),
            param('limit', 'integer', '消息条数，默认12，最多30')])

    async def execute(self, **kwargs):
        store = store_for(kwargs)
        sid = str(kwargs.get('session_id') or kwargs.get('_session_id') or '')
        session = await store.get_session(sid)
        if not session or session.get('deleted_at') or sid.startswith('imported_'):
            return ToolResult(content='会话不可访问', success=False)
        rows = await store.get_messages(sid)
        leaf = kwargs.get('_leaf_id') if sid == kwargs.get('_session_id') else None
        active = _branch(rows, leaf) if leaf is not None else selected_branch(rows, (session.get('preferences') or {}).get('selected_branches') or {})
        anchor = kwargs.get('anchor_message_id')
        if anchor is not None and not any(str(m['id']) == str(anchor) for m in rows):
            return ToolResult(content='该消息不属于此会话', success=False)
        selected = _branch(rows, anchor) if anchor is not None else active
        before = kwargs.get('before_message_id')
        if before is not None:
            index = next((i for i, m in enumerate(selected) if str(m['id']) == str(before)), None)
            if index is None:
                return ToolResult(content='分页消息不在选定分支', success=False)
            selected = selected[:index]
        limit = max(1, min(30, int(kwargs.get('limit') or 12)))
        result = {'session_id': sid, 'title': session.get('title'), 'anchor_in_active_branch': anchor is None or str(anchor) in {str(m['id']) for m in active},
                  'older_before_message_id': selected[-limit]['id'] if len(selected) > limit else None, 'messages': []}
        budget = 24000
        # Preserve exact local text, with explicit truncation, never settings/trace.
        for row in selected[-limit:]:
            content = str(row.get('content') or '')
            size = min(6000, budget)
            if size <= 0:
                result['truncated'] = True
                break
            result['messages'].append({'message_id': row['id'], 'parent_message_id': row.get('parent_message_id'), 'created_at': row.get('created_at'), 'role': row.get('role'), 'content': content[:size], 'truncated': len(content) > size})
            budget -= min(size, len(content))
        return ToolResult(content=json.dumps(result, ensure_ascii=False))


class QuestionReview(BaseTool):
    def get_definition(self):
        return ToolDefinition('question_review', '按原始出题顺序读取错题解析队列。持久记录解析证据和用户确认，与原始错误/掌握成绩分开。explain仅暂存本轮解释证据，成功回答后提交。默认当前分支最新测验轮次。', [
            param('action', 'string', 'queue/detail/explain/confirm/reopen', True, ['queue', 'detail', 'explain', 'confirm', 'reopen']),
            param('session_id', 'string', '原测验会话；省略为当前'), param('turn_id', 'string', '指定原测验轮次，避免重复q_1串题'),
            param('entry_id', 'integer', '来自queue的稳定ID；正数是题库条目，负数是无答题记录的原题卡'),
            param('evidence', 'string', 'explain:最终回答中核心解释原文≥12字；confirm:当前用户明确理解的原文')])

    async def execute(self, **kwargs: Any):
        store = store_for(kwargs)
        ledger = kwargs.get('_ledger') or Ledger(ledger_path())
        sid = str(kwargs.get('session_id') or kwargs.get('_session_id') or '')
        current_sid = str(kwargs.get('_session_id') or '')
        try:
            rows = await review_queue(store, ledger, sid, str(kwargs.get('_turn_id') or '') if sid == current_sid else '', str(kwargs.get('turn_id') or ''))
            action = kwargs.get('action', 'queue')
            if action == 'queue':
                current = next((e['id'] for e in rows if e['review']['state'] not in ('explained', 'confirmed')), None)
                return ToolResult(content=json.dumps({'source_session': sid, 'current_entry_id': current, 'items': [
                    {'entry_id': e['id'], 'turn_id': e.get('turn_id'), 'question_id': e.get('question_id'), 'question_excerpt': str(e.get('question') or '')[:240],
                     'answer_status': 'unanswered' if e.get('unanswered') else 'incorrect',
                     'state': e['review']['state'], 'evidence_message_id': e['review'].get('evidence_message'), 'evidence_session': e['review'].get('evidence_session'),
                     'pending': bool(e['review'].get('pending_turn'))} for e in rows],
                    'note': 'unknown=无可靠解析证据，不等于从未讲过。unanswered=未作答，不能判为答错；用户表示不会或请求讲解时纳入复盘。explained/confirmed均不代表独立作答掌握。'}, ensure_ascii=False))
            entry = next((e for e in rows if str(e['id']) == str(kwargs.get('entry_id'))), None)
            if not entry:
                raise ValueError('题目不在所选分支/轮次错题队列中；先读取queue')
            if action == 'detail':
                return ToolResult(content=format_question_detail(entry, include_solution=not entry.get('unanswered')) + '\nReview: ' + json.dumps(entry['review'], ensure_ascii=False))
            evidence = str(kwargs.get('evidence') or '').strip()
            if action == 'explain':
                if len(evidence) < 12 or not kwargs.get('_turn_id') or not current_sid:
                    raise ValueError('需要本轮ID与≥12字核心解释证据')
                ledger.stage(entry, current_sid, str(kwargs['_turn_id']), evidence)
                return ToolResult(content='解释证据已暂存；必须在最终正文中完整写出该解释。成功保存后提交，失败不推进。')
            if action == 'confirm':
                from .state import current_path
                path = await current_path(store, current_sid, str(kwargs.get('_turn_id') or ''))
                user = next((m for m in reversed(path) if m.get('role') == 'user'), {})
                if entry['review']['state'] not in ('explained', 'confirmed'):
                    raise ValueError('尚无成功解析证据')
                if len(evidence) < 2 or evidence not in str(user.get('content') or ''):
                    raise ValueError('确认必须引用当前用户消息原文')
                ledger.confirm(entry, current_sid, user['id'])
                return ToolResult(content='已记录用户确认理解；原错题成绩保持不变，掌握需独立复测。')
            if action == 'reopen':
                ledger.reopen(entry)
                return ToolResult(content='已重新加入解析队列')
            raise ValueError('未知action')
        except ValueError as exc:
            return ToolResult(content=str(exc), success=False)
