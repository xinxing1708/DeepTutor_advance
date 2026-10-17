"""Regression: a module or objective must not count as done after one part passes.

Run against a staged copy (production package + patched files) with
``PYTHONPATH=<stage> python -m unittest discover -s tests``.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import deeptutor
from deeptutor.capabilities.mastery.loop import MasteryLoopCapability
from deeptutor.learning.models import KnowledgePoint, KnowledgeType, LearningModule, LearningProgress
from deeptutor.learning.policy import (
    facet_report,
    is_mastered,
    map_summary,
    objective_facets,
)
from deeptutor.learning.storage import LearningStore

KP0 = "数据表示、校验码、逻辑运算与计算机体系结构基础"
PATH = "soft_exam"


def run(coro):
    return asyncio.run(coro)


def _progress() -> LearningProgress:
    progress = LearningProgress(book_id=PATH)
    progress.modules = [
        LearningModule(
            id="module_1",
            name="计算机系统基础",
            order=0,
            knowledge_points=[
                KnowledgePoint(id="codes", name="补码", type=KnowledgeType.CONCEPT, module_id="module_1"),
                KnowledgePoint(
                    id="checksums", name="校验码", type=KnowledgeType.CONCEPT, module_id="module_1"
                ),
            ],
        )
    ]
    progress.qualitative_mastery["codes"] = True
    return progress


class Context:
    def __init__(self) -> None:
        self.metadata = {"mastery_mode": True, "mastery_path_id": PATH}
        self._state: dict = {}

    def extension(self, _name):
        return self._state


class FacetSplitTests(unittest.TestCase):
    def test_kp0_name_splits_into_parts(self) -> None:
        kp = KnowledgePoint(id="k", name=KP0, type=KnowledgeType.CONCEPT, module_id="m")
        names = [facet["name"] for facet in objective_facets(kp)]
        self.assertEqual(names, ["数据表示", "校验码", "逻辑运算", "计算机体系结构基础"])

    def test_heading_and_single_names(self) -> None:
        heading = KnowledgePoint(
            id="k", name="校验码：奇偶校验、海明码、CRC", type=KnowledgeType.CONCEPT, module_id="m"
        )
        self.assertEqual([f["name"] for f in objective_facets(heading)], ["奇偶校验", "海明码", "CRC"])
        for name in (
            "补码",
            "Why XOR matters",
            "原码反码补码的转换",
            "逻辑运算与位运算：与、或、非、异或的真值及运算结果",
        ):
            single = KnowledgePoint(id="k", name=name, type=KnowledgeType.CONCEPT, module_id="m")
            self.assertEqual(objective_facets(single), [], name)


class ToolFlowBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mc_test_"))
        root = self.tmp

        def _init(store, root_arg=None):
            store._root = root / "learning"
            store._root.mkdir(parents=True, exist_ok=True)

        self._patches = [
            patch.object(LearningStore, "__init__", _init),
            patch.dict(os.environ, {"DEEPTUTOR_MASTERY_REVIEW": "0"}),
        ]
        for item in self._patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self._patches):
            item.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, names_types):
        from deeptutor.tools.mastery_tool import MasteryBuildTool

        result = run(
            MasteryBuildTool().execute(
                _mastery_path_id=PATH,
                mode="replace",
                modules=[
                    {
                        "name": "计算机系统基础",
                        "knowledge_points": [{"name": n, "type": t} for n, t in names_types],
                    }
                ],
            )
        )
        self.assertTrue(result.success, result.content)
        progress = LearningStore().load(PATH)
        return [kp.id for kp in progress.modules[0].knowledge_points]

    def assess(self, kp_id, **kwargs):
        from deeptutor.tools.mastery_tool import MasteryAssessTool

        return run(
            MasteryAssessTool().execute(_mastery_path_id=PATH, knowledge_point_id=kp_id, **kwargs)
        )

    def kp(self, kp_id):
        progress = LearningStore().load(PATH)
        for kp in progress.modules[0].knowledge_points:
            if kp.id == kp_id:
                return progress, kp
        raise AssertionError(kp_id)


class FacetGateTests(ToolFlowBase):
    def test_one_part_does_not_master_multi_part_objective(self) -> None:
        (kp0,) = self.build([(KP0, "concept")])
        refused = self.assess(kp0, passed=True, feedback="补码讲对了")
        self.assertFalse(refused.success)
        self.assertIn("f1", refused.content)

        ok = self.assess(kp0, passed=True, facet_id="f1", learner_quote="补码就是反码加一，正数不变")
        payload = json.loads(ok.content)
        self.assertFalse(payload["mastered"])
        self.assertIn("NOT mastered", payload["instruction"])
        progress, kp = self.kp(kp0)
        self.assertFalse(is_mastered(progress, kp))
        module = map_summary(progress)["modules"][0]
        self.assertFalse(module["complete"])

        quotes = ["校验码用来发现传输错误", "逻辑运算有与或非异或", "体系结构讲的是CPU存储器和总线"]
        same = self.assess(kp0, passed=True, facet_id="f2", learner_quote="补码就是反码加一，正数不变")
        self.assertFalse(same.success, "one quote may not cover two parts")
        for facet_id, quote in zip(("f2", "f3", "f4"), quotes):
            payload = json.loads(self.assess(kp0, passed=True, facet_id=facet_id, learner_quote=quote).content)
        self.assertTrue(payload["mastered"])
        progress, kp = self.kp(kp0)
        self.assertTrue(map_summary(progress)["modules"][0]["complete"])

    def test_failed_recheck_withdraws_a_part(self) -> None:
        (kp0,) = self.build([(KP0, "concept")])
        self.assess(kp0, passed=True, facet_id="f1", learner_quote="补码就是反码加一，正数不变")
        self.assess(kp0, passed=False, facet_id="f1", feedback="又说错了")
        progress, kp = self.kp(kp0)
        self.assertFalse(facet_report(progress, kp)[0]["covered"])

    def test_legacy_pass_is_kept(self) -> None:
        (kp0,) = self.build([(KP0, "concept")])

        def legacy(tx):
            tx.progress.qualitative_mastery[kp0] = True
            tx.touch()

        LearningStore().mutate(PATH, legacy)
        progress, kp = self.kp(kp0)
        self.assertTrue(is_mastered(progress, kp))
        # Re-assessing an earned pass (review) does not demand facets or revoke it.
        result = self.assess(kp0, passed=True, feedback="复习通过")
        self.assertTrue(result.success, result.content)
        progress, kp = self.kp(kp0)
        self.assertTrue(is_mastered(progress, kp))
        self.assertNotIn(kp0, progress.objective_facets)

    def test_quiz_needs_facet_and_covers_only_that_part(self) -> None:
        from deeptutor.tools.mastery_tool import MasteryGradeTool, MasteryQuizTool

        (kp,) = self.build([("校验码：奇偶校验、海明码", "memory")])
        refused = run(
            MasteryQuizTool().execute(
                _mastery_path_id=PATH, knowledge_point_id=kp, question="q", expected_answer="a"
            )
        )
        self.assertFalse(refused.success)
        for _ in range(4):
            posed = run(
                MasteryQuizTool().execute(
                    _mastery_path_id=PATH,
                    knowledge_point_id=kp,
                    question="奇偶校验能纠错吗",
                    expected_answer="不能",
                    facet_id="f1",
                )
            )
            self.assertTrue(posed.success, posed.content)
            graded = json.loads(run(MasteryGradeTool().execute(_mastery_path_id=PATH, answer="不能")).content)
        self.assertFalse(graded["mastered"])
        self.assertIn("海明码", graded["instruction"])
        self.assertEqual([f["covered"] for f in graded["facets"]], [True, False])


class QuoteAndReviewTests(ToolFlowBase):
    def test_quote_must_come_from_learner(self) -> None:
        (kp,) = self.build([("补码", "concept")])
        short = self.assess(kp, passed=True, learner_quote="对", _user_message="对")
        self.assertFalse(short.success)
        made_up = self.assess(
            kp, passed=True, learner_quote="补码是反码末位加一得到的", _user_message="我不太懂补码"
        )
        self.assertFalse(made_up.success)
        self.assertIn("does not appear", made_up.content)
        ok = self.assess(
            kp,
            passed=True,
            learner_quote="补码是反码 末位加一",
            _user_message="我理解的是：补码是反码末位加一，符号位不变。",
        )
        self.assertTrue(json.loads(ok.content)["mastered"])

    def test_background_reviewer_can_veto(self) -> None:
        (kp,) = self.build([("补码", "concept")])
        msg = "补码嘛，我觉得应该就是那个吧"

        async def reject(*_a, **_k):
            yield "<think>只提到概念名</think>"
            yield '{"pass": false, "reason": "没有说出补码怎么求"}'

        async def boom(*_a, **_k):
            raise RuntimeError("provider down")
            yield ""  # pragma: no cover - makes this an async generator

        with patch.dict(os.environ, {"DEEPTUTOR_MASTERY_REVIEW": "1"}):
            with patch("deeptutor.services.llm.stream", reject):
                vetoed = self.assess(kp, passed=True, learner_quote=msg, _user_message=msg)
            self.assertFalse(vetoed.success)
            self.assertIn("没有说出补码怎么求", vetoed.content)
            progress, item = self.kp(kp)
            self.assertFalse(is_mastered(progress, item))
            with patch("deeptutor.services.llm.stream", boom):
                passed = self.assess(kp, passed=True, learner_quote=msg, _user_message=msg)
            self.assertTrue(json.loads(passed.content)["mastered"], "reviewer outage must not block")


class ModuleClaimTests(unittest.TestCase):
    def test_module_reports_remaining_objectives_until_all_pass(self) -> None:
        progress = _progress()
        module = map_summary(progress)["modules"][0]
        self.assertEqual((module["mastered"], module["total"]), (1, 2))
        self.assertIs(module["complete"], False)
        self.assertEqual([point["id"] for point in module["remaining"]], ["checksums"])
        progress.qualitative_mastery["checksums"] = True
        module = map_summary(progress)["modules"][0]
        self.assertIs(module["complete"], True)
        self.assertEqual(module["remaining"], [])

    def _store(self, progress):
        class Store:
            def load(self, _path_id):
                return progress

        return patch("deeptutor.learning.storage.LearningStore", Store)

    def test_claim_redirected_once_per_turn(self) -> None:
        progress = _progress()
        with self._store(progress):
            tutor = MasteryLoopCapability()
            context = Context()
            claim = "计算机系统基础这个模块已经完成，我们进入下一模块。"
            verdict = tutor.finish_instruction(context, claim)
            self.assertIsNotNone(verdict)
            self.assertIn("校验码", verdict)
            # A second rejection would fail the whole turn; the engine gate holds anyway.
            self.assertIsNone(tutor.finish_instruction(context, claim))
            progress.qualitative_mastery["checksums"] = True
            self.assertIsNone(tutor.finish_instruction(Context(), claim))
            self.assertIsNone(tutor.finish_instruction(Context(), ""))

    def test_no_false_positive_for_negated_or_question(self) -> None:
        with self._store(_progress()):
            tutor = MasteryLoopCapability()
            self.assertIsNone(tutor.finish_instruction(Context(), "这个模块还没有完成，校验码仍未通过。"))
            self.assertIsNone(tutor.finish_instruction(Context(), "你问的是‘这个模块已经完成了吗？’答案是没有。"))


class StagingSanity(unittest.TestCase):
    def test_runs_against_staged_copy(self) -> None:
        self.assertNotIn(".venv", deeptutor.__file__, "PYTHONPATH must point at the staged copy")


if __name__ == "__main__":
    unittest.main()
