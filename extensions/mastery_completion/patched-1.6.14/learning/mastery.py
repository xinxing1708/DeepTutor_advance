"""Mastery scoring policy — intentionally simple and swappable.

``compute_mastery`` maps a knowledge point's attempt history to a 0..1 mastery
score. The policy is a recency-weighted, evidence-weighted accuracy with three
guards (local mastery-v2 rules):

* **confidence cap** — few attempts cannot reach the gate, however right.
* **evidence weight** — a correct multiple-choice pick is weaker evidence than
  a produced answer (short / open), so it earns partial credit; a hard choice
  question earns more than an ordinary one. Attempts recorded before the
  question type was stored keep full credit, so earned history is not demoted.
* **error debt** — each wrong answer adds debt that only later correct answers
  on the same part (facet) repay. While any debt is outstanding the score is
  capped below the gate, so an early mistake cannot be washed out of the
  window by a streak of easy answers on a different part.

This is the one place the pedagogy math lives. To plug in a richer model
(e.g. an IRT/BKT estimate), replace ``compute_mastery`` alone; callers
(`LearningService.calculate_mastery`) need not change.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Recency weights for the most recent attempts (oldest -> newest).
_WINDOW = 6
_RECENCY_WEIGHTS: tuple[float, ...] = tuple(
    0.4 + 0.6 * index / (_WINDOW - 1) for index in range(_WINDOW)
)

# Mastery cannot exceed this until enough attempts accumulate: the 0.9 gate
# needs at least four graded attempts.
_CONFIDENCE_CAP: dict[int, float] = {1: 0.4, 2: 0.6, 3: 0.8}

# Credit a correct answer earns, by how strong the evidence is.
CHOICE_CREDIT = 0.85
HARD_CHOICE_CREDIT = 0.95
PRODUCED_CREDIT = 1.0

# Error debt: a wrong answer adds ERROR_DEBT units; each later correct answer
# on the same facet repays one. Outstanding debt caps mastery below the gate.
ERROR_DEBT = 2
MAX_DEBT_PER_FACET = 4
DEBT_CAP = 0.85


@dataclass(frozen=True)
class AttemptEvidence:
    """One graded attempt as the scoring policy sees it."""

    is_correct: bool
    question_type: str = ""
    difficulty: str = ""
    facet_id: str = ""


def answer_credit(question_type: str, difficulty: str = "") -> float:
    """Credit a *correct* answer of this kind earns (0..1)."""
    qtype = str(question_type or "").strip().lower()
    if qtype == "choice":
        return HARD_CHOICE_CREDIT if str(difficulty or "").lower() == "hard" else CHOICE_CREDIT
    return PRODUCED_CREDIT


def _as_evidence(item: Any) -> AttemptEvidence:
    if isinstance(item, AttemptEvidence):
        return item
    if isinstance(item, bool):
        return AttemptEvidence(is_correct=item)
    return AttemptEvidence(
        is_correct=bool(getattr(item, "is_correct", False)),
        question_type=str(getattr(item, "question_type", "") or ""),
        difficulty=str(getattr(item, "difficulty", "") or ""),
        facet_id=str(getattr(item, "facet_id", "") or ""),
    )


def error_debt(attempts: Iterable[Any]) -> dict[str, int]:
    """Outstanding error debt per facet key (``""`` for the whole objective).

    A wrong answer on facet ``f2`` is repaid only by later correct answers on
    ``f2``; debt recorded without a facet is repaid by any correct answer.
    Wrong answers recorded before the question type was stored (legacy
    attempts) add no debt, so history graded under the old rules is not
    retroactively penalised.
    """
    debt: dict[str, int] = {}
    for raw in attempts:
        item = _as_evidence(raw)
        key = item.facet_id
        if not item.is_correct:
            if not item.question_type:
                continue
            debt[key] = min(MAX_DEBT_PER_FACET, debt.get(key, 0) + ERROR_DEBT)
            continue
        for target in {key, ""}:
            if debt.get(target):
                debt[target] -= 1
    return {key: value for key, value in debt.items() if value > 0}


def compute_mastery(attempts: list[Any]) -> float:
    """Return a 0..1 mastery score from a knowledge point's attempt history.

    Args:
        attempts: chronological attempts — bools (legacy callers), or objects
            with ``is_correct`` / ``question_type`` / ``difficulty`` /
            ``facet_id`` (``QuizAttempt`` or :class:`AttemptEvidence`).
    """
    if not attempts:
        return 0.0
    evidence = [_as_evidence(item) for item in attempts]
    recent = evidence[-_WINDOW:]
    weights = _RECENCY_WEIGHTS[-len(recent) :]
    earned = sum(
        weight * (answer_credit(item.question_type, item.difficulty) if item.is_correct else 0.0)
        for item, weight in zip(recent, weights, strict=True)
    )
    score = earned / sum(weights)
    cap = _CONFIDENCE_CAP.get(len(evidence), 1.0)
    if error_debt(evidence):
        cap = min(cap, DEBT_CAP)
    return min(score, cap)


__all__ = [
    "AttemptEvidence",
    "CHOICE_CREDIT",
    "DEBT_CAP",
    "HARD_CHOICE_CREDIT",
    "PRODUCED_CREDIT",
    "answer_credit",
    "compute_mastery",
    "error_debt",
]
