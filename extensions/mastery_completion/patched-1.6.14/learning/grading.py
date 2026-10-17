"""Deterministic answer grading + coarse error classification for Mastery Path."""

from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import TYPE_CHECKING
import unicodedata

if TYPE_CHECKING:
    from deeptutor.learning.models import ErrorType


def grade_answer(user_answer: str, expected_answer: str, question_type: str = "short") -> bool:
    """Grade user answer against expected answer.

    Args:
        user_answer: The user's submitted answer.
        expected_answer: The stored expected answer.
        question_type: One of "choice", "short", "open".

    Returns:
        True if answer is correct.
    """
    user = user_answer.strip().lower()
    expected = expected_answer.strip().lower()

    if not expected:
        return False

    if question_type == "choice":
        user_norm = user.replace(" ", "")
        expected_norm = expected.replace(" ", "")
        return user_norm == expected_norm

    if question_type == "short":
        if user == expected:
            return True
        # Local mastery-v2: compare the canonical form too, so "{A, B}" and
        # "{A,B}", full-width punctuation, or a leading "答案是" do not turn a
        # right answer into a wrong one.
        user_norm = normalize_short_answer(user)
        expected_norm = normalize_short_answer(expected)
        if user_norm and user_norm == expected_norm:
            return True
        if len(expected) <= 30:
            return (
                SequenceMatcher(None, user, expected).ratio() >= 0.85
                or SequenceMatcher(None, user_norm, expected_norm).ratio() >= 0.9
            )
        return False

    if question_type == "open":
        keywords = [k.strip() for k in re.split(r"[,;，；。\n]+", expected) if k.strip()]
        if not keywords:
            return False
        matched = sum(1 for kw in keywords if kw in user)
        return matched / len(keywords) >= 0.6

    return False


_ANSWER_PREFIX_RE = re.compile(
    r"^(?:(?:我的)?(?:最终)?(?:答案|结论|结果)(?:是|为)?|所以(?:是|为)?|应该是|"
    r"(?:the\s+)?(?:final\s+)?answer(?:\s+is)?|it\s+is|it's)\s*[:：]?\s*",
    re.IGNORECASE,
)
_ANSWER_EDGE_PUNCT = "。．.，,、；;！!？?\"'“”‘’`"


def normalize_short_answer(text: str) -> str:
    """Canonical form of a short answer for equality checks.

    NFKC-folds full-width characters, drops a leading "答案是 / answer is"
    phrase, removes all whitespace and trims sentence punctuation at the ends.
    Inner punctuation, braces, arrows and operators are kept because they
    carry meaning ("3.14" is not "31.4", "A→B" is not "B→A").
    """
    folded = unicodedata.normalize("NFKC", str(text or "")).strip().casefold()
    folded = _ANSWER_PREFIX_RE.sub("", folded, count=1)
    return "".join(folded.split()).strip(_ANSWER_EDGE_PUNCT)


def classify_error(user_answer: str) -> ErrorType:
    """Coarse error classification for a wrong answer.

    A blank answer signals the student did not know (metacognitive); anything
    else is treated as a wrong application. The richer four-type taxonomy is
    assigned later by the LLM in the error-diagnosis stage.
    """
    from deeptutor.learning.models import ErrorType

    return ErrorType.METACOGNITIVE if not user_answer.strip() else ErrorType.APPLICATION_ERROR


__all__ = ["grade_answer", "classify_error", "normalize_short_answer"]
