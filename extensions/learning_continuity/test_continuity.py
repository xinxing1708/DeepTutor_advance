import asyncio
import gc
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from deeptutor_learning_continuity.state import Ledger, identity, review_queue, selected_branch
from deeptutor_learning_continuity.tools import ConversationRead, ConversationSearch, QuestionReview
from deeptutor_learning_continuity.extension import LearningContinuityExtension
from deeptutor.core.context import UnifiedContext


class Store:
    def __init__(self):
        def quiz(mid, tid, parent, qids):
            return dict(id=mid, role='assistant', parent_message_id=parent, capability='deep_question', content='quiz',
                metadata={'turn_id': tid}, events=[{'metadata': {'qa_pair': {'question_id': q, 'question': q, 'options': {'A': 'alpha', 'B': 'beta'}}}} for q in qids])
        self.rows = [dict(id=1, role='user', parent_message_id=None, content='old'), quiz(2,'r1',1,['q_1','q_3']),
                     dict(id=3, role='user', parent_message_id=2, content='parsed', metadata={'turn_id':'t1'}),
                     dict(id=4, role='assistant', parent_message_id=3, content='这是一段足够长的核心解释证据原文'),
                     dict(id=5, role='user', parent_message_id=4, content='现在我理解了', metadata={'turn_id':'t2'}),
                     quiz(6,'r2',5,['q_1']), dict(id=7, role='user', parent_message_id=6, content='new', metadata={'turn_id':'t3'})]
        self.entries = [dict(id=i, session_id='s', turn_id=t, question_id=q, is_correct=False, user_answer='B', question=q) for i,t,q in [(21,'r1','q_1'),(23,'r1','q_3'),(31,'r2','q_1')]][::-1]
        self.turns={'t1':dict(status='completed',assistant_message_id=4), 't2':dict(status='running'), 't3':dict(status='running')}
    async def get_messages(self, sid): return self.rows if sid=='s' else []
    async def get_session(self, sid): return {'title':'course'} if sid=='s' else None
    async def get_message_trace(self,sid,mid,limit=1): return {'turn_id': next((m.get('metadata',{}).get('turn_id') for m in self.rows if m['id']==mid),'')}
    async def get_turn_events(self, tid): return []
    async def list_notebook_entries(self, **kw): return {'items':self.entries,'total':len(self.entries)}
    async def get_turn(self, tid): return self.turns.get(tid)


class ContinuityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ledger=Ledger(Path(self.temp.name)/'review.db')
        self.store=Store()
    async def asyncTearDown(self):
        gc.collect()
        self.temp.cleanup()
    async def queue(self, tid='t2', source='r1'):
        return await review_queue(self.store,self.ledger,'s',tid,source)
    async def test_original_order_not_recent_bank_order(self):
        self.assertEqual([e['id'] for e in await self.queue()],[21,23])
    async def test_blank_card_without_bank_row_is_kept_without_inventing_grade(self):
        self.store.rows[1]['events'].append({'metadata':{'qa_pair':{'question_id':'q_9','question':'未作答原题'}}})
        one=await self.queue();two=await self.queue()
        self.assertEqual(one[-1]['question_id'],'q_9')
        self.assertLess(one[-1]['id'],0);self.assertEqual(one[-1]['id'],two[-1]['id'])
        self.assertIsNone(one[-1]['is_correct']);self.assertEqual(len(self.store.entries),3)
    async def test_repeated_q1_does_not_share_state(self):
        self.ledger.stage(self.store.entries[-1],'s','t1','这是一段足够长的核心解释证据原文')
        old=await self.queue();new=await self.queue('t3','r2')
        self.assertEqual(old[0]['review']['state'],'explained')
        self.assertEqual(new[0]['review']['state'],'unknown')
    async def test_failed_turn_does_not_advance(self):
        self.store.turns['t1']['status']='failed'
        self.ledger.stage(self.store.entries[-1],'s','t1','这是一段足够长的核心解释证据原文')
        self.assertEqual((await self.queue())[0]['review']['state'],'unknown')
    async def test_tool_only_without_final_evidence_does_not_advance(self):
        self.store.rows[3]['content']='工具已完成'
        self.ledger.stage(self.store.entries[-1],'s','t1','这是一段足够长的核心解释证据原文')
        self.assertEqual((await self.queue())[0]['review']['state'],'unknown')
    async def test_restart_commits_success_and_keeps_wrong_grade(self):
        self.ledger.stage(self.store.entries[-1],'s','t1','这是一段足够长的核心解释证据原文')
        restarted=Ledger(self.ledger.path)
        rows=await review_queue(self.store,restarted,'s','t2','r1')
        self.assertEqual(rows[0]['review']['evidence_message'],4)
        self.assertFalse(rows[0]['is_correct'])
    async def test_sibling_explanation_not_current_branch_progress(self):
        self.ledger.stage(self.store.entries[-1],'s','t1','这是一段足够长的核心解释证据原文')
        await self.queue()
        self.store.rows.append(dict(id=8,role='user',parent_message_id=2,content='sibling',metadata={'turn_id':'t4'}))
        self.assertEqual((await self.queue('t4'))[0]['review']['state'],'unknown')
    async def test_read_anchor_labels_old_branch_no_sibling_leak(self):
        self.store.rows.append(dict(id=8,role='assistant',parent_message_id=2,content='discarded sibling'))
        result=await ConversationRead().execute(_store=self.store,_session_id='s',_leaf_id=7,anchor_message_id=8)
        data=json.loads(result.content)
        self.assertFalse(data['anchor_in_active_branch'])
        self.assertEqual([m['message_id'] for m in data['messages']],[1,2,8])
    async def test_saved_ui_branch_beats_latest_and_longer_sibling(self):
        self.store.rows.append(dict(id=8,role='assistant',parent_message_id=2,content='chosen short sibling'))
        self.assertEqual([m['id'] for m in selected_branch(self.store.rows,{'2':8})],[1,2,8])
        self.assertEqual([m['id'] for m in selected_branch(self.store.rows,{})],[1,2,3,4,5,6,7])
    async def test_confirm_cites_real_user_and_never_corrects_grade(self):
        e=self.store.entries[-1]
        self.ledger.stage(e,'s','t1','这是一段足够长的核心解释证据原文');await self.queue()
        args=dict(_store=self.store,_ledger=self.ledger,_session_id='s',_turn_id='t2',action='confirm',entry_id=21,turn_id='r1')
        self.assertFalse((await QuestionReview().execute(**args,evidence='虚构确认')).success)
        self.assertTrue((await QuestionReview().execute(**args,evidence='我理解了')).success)
        self.assertFalse(e['is_correct'])
    async def test_extension_mounts_prompt_and_private_parameters(self):
        c=UnifiedContext(session_id='s',metadata={'turn_id':'t2'})
        ext=LearningContinuityExtension()
        self.assertTrue(ext.is_active(c));self.assertIn('精通之路主动绘图',ext.system_block(c,language='zh',prompts={}).content)
        self.assertEqual(ext.augment_kwargs('question_review',{},c)['_turn_id'],'t2')
if __name__=='__main__':unittest.main(verbosity=2)
