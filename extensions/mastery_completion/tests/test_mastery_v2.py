"""Regression: local mastery-v2 — stricter gates, explicit facets, choice-prose grading.

Run against a staged copy (production package + patched files) with
``PYTHONPATH=<stage> python -m unittest discover -s tests``.
"""

from __future__ import annotations

import unittest

from deeptutor.learning.grading import grade_answer, normalize_short_answer
from deeptutor.learning.mastery import compute_mastery, error_debt
from deeptutor.learning.models import (
    KnowledgePoint,
    KnowledgeType,
    LearningModule,
    LearningProgress,
    QuizAttempt,
)
from deeptutor.learning.pending import is_readable_choice_answer, resolve_choice_submission
from deeptutor.learning.policy import (
    facet_report,
    gate_blockers,
    has_strong_evidence,
    is_assessed_mastered,
    objective_facets,
)

OPTIONS = {"A": "2NF", "B": "3NF", "C": "BCNF", "D": "1NF"}


def _attempt(qid: str, ok: bool, qtype: str = "short", difficulty: str = "", facet: str = "", kp: str = "kp"):
    return QuizAttempt(
        question_id=qid,
        knowledge_point_id=kp,
        user_answer="x",
        is_correct=ok,
        question_type=qtype,
        difficulty=difficulty,
        facet_id=facet,
    )


def _progress(kp: KnowledgePoint) -> LearningProgress:
    progress = LearningProgress(book_id="v2")
    progress.modules = [LearningModule(id="m", name="M", order=0, knowledge_points=[kp])]
    return progress


class ScoringTests(unittest.TestCase):
    def test_confidence_cap_needs_four_attempts(self) -> None:
        self.assertEqual(compute_mastery([True]), 0.4)
        self.assertEqual(compute_mastery([True, True, True]), 0.8)
        self.assertAlmostEqual(compute_mastery([True] * 4), 1.0)

    def test_choice_picks_alone_stay_below_gate(self) -> None:
        picks = [_attempt(f"q{i}", True, "choice") for i in range(6)]
        self.assertLess(compute_mastery(picks), 0.9)

    def test_error_debt_caps_until_repaid_on_same_facet(self) -> None:
        history = [_attempt("q1", False, facet="f1")] + [
            _attempt(f"q{i}", True, facet="f2") for i in range(2, 8)
        ]
        self.assertEqual(error_debt(history), {"f1": 2})
        self.assertLessEqual(compute_mastery(history), 0.85)
        repaid = history + [_attempt("q8", True, facet="f1"), _attempt("q9", True, facet="f1")]
        self.assertEqual(error_debt(repaid), {})

    def test_legacy_wrong_answers_add_no_debt(self) -> None:
        legacy = [_attempt("q1", False, qtype="")] + [_attempt(f"q{i}", True, qtype="") for i in range(2, 6)]
        self.assertEqual(error_debt(legacy), {})


class GateTests(unittest.TestCase):
    def test_strong_evidence_required_for_quantitative_gate(self) -> None:
        kp = KnowledgePoint(id="kp", name="范式判定", type=KnowledgeType.PROCEDURE, module_id="m")
        progress = _progress(kp)
        progress.quiz_attempts = [_attempt(f"q{i}", True, "choice") for i in range(6)]
        progress.mastery_levels["kp"] = 0.95  # forced above gate
        self.assertFalse(has_strong_evidence(progress, "kp"))
        self.assertFalse(is_assessed_mastered(progress, kp))
        self.assertTrue(any("multiple-choice" in item for item in gate_blockers(progress, kp)))
        progress.quiz_attempts.append(_attempt("q9", True, "short"))
        self.assertTrue(is_assessed_mastered(progress, kp))

    def test_legacy_history_is_not_demoted(self) -> None:
        kp = KnowledgePoint(id="kp", name="范式判定", type=KnowledgeType.MEMORY, module_id="m")
        progress = _progress(kp)
        progress.quiz_attempts = [_attempt(f"q{i}", True, qtype="") for i in range(3)]
        progress.mastery_levels["kp"] = 1.0
        self.assertTrue(is_assessed_mastered(progress, kp))

    def test_declared_facets_need_two_distinct_correct_answers(self) -> None:
        kp = KnowledgePoint(
            id="kp",
            name="关系范式",
            type=KnowledgeType.PROCEDURE,
            module_id="m",
            facets=["求候选键", "判定 2NF", "判定 3NF"],
            pitfalls=["把部分依赖当传递依赖"],
        )
        self.assertEqual([f["name"] for f in objective_facets(kp)], ["求候选键", "判定 2NF", "判定 3NF"])
        progress = _progress(kp)
        progress.objective_facets["kp"] = {"covered": [], "quotes": {}, "v": 2}
        progress.quiz_attempts = [_attempt("q1", True, facet="f1"), _attempt("q1", True, facet="f1")]
        f1 = facet_report(progress, kp)[0]
        self.assertEqual((f1["correct"], f1["needed"], f1["covered"]), (1, 2, False))
        progress.quiz_attempts.append(_attempt("q2", True, facet="f1"))
        self.assertTrue(facet_report(progress, kp)[0]["covered"])
        progress.quiz_attempts.append(_attempt("q3", False, facet="f1"))
        self.assertFalse(facet_report(progress, kp)[0]["covered"])

    def test_pre_v2_tracking_keeps_one_correct_rule(self) -> None:
        kp = KnowledgePoint(id="kp", name="奇偶校验、海明码", type=KnowledgeType.MEMORY, module_id="m")
        progress = _progress(kp)
        progress.objective_facets["kp"] = {"covered": [], "quotes": {}}
        progress.quiz_attempts = [_attempt("q1", True, qtype="", facet="f1")]
        self.assertTrue(facet_report(progress, kp)[0]["covered"])

    def test_single_declared_facet_is_ignored(self) -> None:
        kp = KnowledgePoint(id="kp", name="补码", type=KnowledgeType.MEMORY, module_id="m", facets=["补码"])
        self.assertEqual(objective_facets(kp), [])


class ChoiceProseTests(unittest.TestCase):
    def test_explicit_picks_resolve(self) -> None:
        for text, label in (
            ("A", "A"),
            ("选C", "C"),
            ("答案是 C", "C"),
            ("I think it's A", "A"),
            ("答案：B", "B"),
            ("3NF", "B"),
            ("所以最高满足 3NF", "B"),
        ):
            self.assertEqual(resolve_choice_submission(text, OPTIONS), label, text)
            self.assertTrue(is_readable_choice_answer(text, OPTIONS), text)

    def test_letters_in_reasoning_are_not_picks(self) -> None:
        for text in (
            "A是候选键，别的都不是，四个都是主属性，没有非主属性",
            "为什么B不对",
            "A or B",
            "候选键A，非主属性BCD，没有部分依赖，满足2NF，无传递依赖满足3NF",
        ):
            self.assertEqual(resolve_choice_submission(text, OPTIONS), "", text)
            self.assertFalse(is_readable_choice_answer(text, OPTIONS), text)


class ShortAnswerTests(unittest.TestCase):
    def test_canonical_forms_match(self) -> None:
        self.assertTrue(grade_answer("{A, B}", "{A,B}", "short"))
        self.assertTrue(grade_answer("答案是：AB", "AB", "short"))
        self.assertTrue(grade_answer("ＡＢ。", "AB", "short"))

    def test_meaningful_differences_stay_wrong(self) -> None:
        self.assertFalse(grade_answer("31.4", "3.14", "short"))
        self.assertFalse(grade_answer("B→A", "A→B", "short"))
        self.assertEqual(normalize_short_answer("the answer is 42"), "42")


if __name__ == "__main__":
    unittest.main()
