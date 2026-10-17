from __future__ import annotations

from pathlib import Path
from deeptutor.capabilities.protocol import PromptBlock
from .state import Ledger, ledger_path, current_path
from .tools import QuestionReview


class LearningContinuityExtension:
    name = 'learning_continuity'
    owned_tools = ('conversation_search', 'conversation_read', 'question_review')

    def is_active(self, context):
        return bool(context.session_id) and not (context.metadata or {}).get('agent_identity')

    def system_block(self, context, *, language, prompts):
        return PromptBlock(self.name, Path(__file__).with_name('prompt.md').read_text(encoding='utf-8'))

    def augment_kwargs(self, tool_name, kwargs, context):
        if tool_name not in self.owned_tools:
            return kwargs
        return {**kwargs, '_session_id': context.session_id, '_turn_id': context.metadata.get('turn_id', ''),
                '_leaf_id': context.extension(self.name).get('leaf_id')}

    def pre_loop_seed(self, context):
        return ''

    async def pre_loop(self, context, stream, *, usage=None):
        from deeptutor.services.session import get_session_store
        store = get_session_store()
        path = await current_path(store, context.session_id, context.metadata.get('turn_id', ''))
        context.extension(self.name)['leaf_id'] = path[-1]['id'] if path else None
        result = await QuestionReview().execute(action='queue', _store=store, _ledger=Ledger(ledger_path()),
                    _session_id=context.session_id, _turn_id=context.metadata.get('turn_id', ''))
        if '"items": []' in result.content:
            return None
        return PromptBlock('active_question_review', '[错题解析进度，独立于原答题成绩]\n' + result.content)
