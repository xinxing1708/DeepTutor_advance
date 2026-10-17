"""Local mastery-v2 tool-level smoke tests (staged copy only)."""

import json

import pytest

from deeptutor.capabilities.mastery.tools import (
    MasteryBuildTool,
    MasteryGradeTool,
    MasteryQuizTool,
    MasteryStatusTool,
)
from deeptutor.learning.storage import LearningStore
from deeptutor.learning.tests.test_mastery_tools import _store_init_factory


@pytest.fixture
def path_id(tmp_path, monkeypatch):
    monkeypatch.setattr(LearningStore, "__init__", _store_init_factory(tmp_path))
    return "v2_path"


async def _build(path_id):
    return json.loads(
        (
            await MasteryBuildTool().execute(
                _mastery_path_id=path_id,
                mode="replace",
                modules=[
                    {
                        "name": "范式",
                        "objective": "能判定关系模式的范式",
                        "knowledge_points": [
                            {
                                "name": "范式判定",
                                "type": "procedure",
                                "facets": ["求候选键", "判定范式"],
                                "pitfalls": ["把部分依赖当传递依赖"],
                            }
                        ],
                    }
                ],
            )
        ).content
    )


def _choice(kp_id, facet="f1"):
    return dict(
        knowledge_point_id=kp_id,
        question="R(A,B,C,D) 最高满足哪个范式？",
        expected_answer="C",
        question_type="choice",
        options=[
            {"label": "A", "body": "2NF"},
            {"label": "B", "body": "3NF"},
            {"label": "C", "body": "BCNF"},
            {"label": "D", "body": "1NF"},
        ],
        facet_id=facet,
    )


@pytest.mark.asyncio
async def test_build_keeps_facets_and_status_reports_blockers(path_id):
    build = await _build(path_id)
    point = build["map"]["modules"][0]["knowledge_points"][0]
    assert [f["name"] for f in point["facets"]] == ["求候选键", "判定范式"]
    assert point["pitfalls"] == ["把部分依赖当传递依赖"]
    status = json.loads((await MasteryStatusTool().execute(_mastery_path_id=path_id)).content)
    assert status["current_pitfalls"] == ["把部分依赖当传递依赖"]
    assert status["current_gate_blockers"]


@pytest.mark.asyncio
async def test_prose_mentioning_a_letter_is_not_graded(path_id):
    build = await _build(path_id)
    kp_id = build["map"]["modules"][0]["knowledge_points"][0]["id"]
    await MasteryQuizTool().execute(_mastery_path_id=path_id, **_choice(kp_id))
    result = await MasteryGradeTool().execute(
        _mastery_path_id=path_id, answer="A是候选键，别的都不是，四个都是主属性"
    )
    assert result.success is False
    assert "NOT graded" in result.content
    progress = LearningStore().load(path_id)
    assert progress.quiz_attempts == []


@pytest.mark.asyncio
async def test_third_choice_in_a_row_is_refused(path_id):
    build = await _build(path_id)
    kp_id = build["map"]["modules"][0]["knowledge_points"][0]["id"]
    for _ in range(2):
        await MasteryQuizTool().execute(_mastery_path_id=path_id, **_choice(kp_id))
        progress = LearningStore().load(path_id)
        label = next(o.label for o in progress.pending_question.options if o.body == "BCNF")
        graded = json.loads(
            (await MasteryGradeTool().execute(_mastery_path_id=path_id, answer=label)).content
        )
        assert graded["is_correct"] is True
        assert graded["gate_blockers"]
    refused = await MasteryQuizTool().execute(_mastery_path_id=path_id, **_choice(kp_id))
    assert refused.success is False
    assert "multiple choice" in refused.content
    attempts = LearningStore().load(path_id).quiz_attempts
    assert [a.question_type for a in attempts] == ["choice", "choice"]


@pytest.mark.asyncio
async def test_short_accepted_answers(path_id):
    build = await _build(path_id)
    kp_id = build["map"]["modules"][0]["knowledge_points"][0]["id"]
    await MasteryQuizTool().execute(
        _mastery_path_id=path_id,
        knowledge_point_id=kp_id,
        question="写出 R 的候选键",
        expected_answer="{A,B}",
        question_type="short",
        accepted_answers=["AB", "A、B"],
        facet_id="f1",
        difficulty="hard",
    )
    graded = json.loads(
        (await MasteryGradeTool().execute(_mastery_path_id=path_id, answer="A、B")).content
    )
    assert graded["is_correct"] is True
    attempt = LearningStore().load(path_id).quiz_attempts[-1]
    assert (attempt.question_type, attempt.difficulty, attempt.facet_id) == ("short", "hard", "f1")
