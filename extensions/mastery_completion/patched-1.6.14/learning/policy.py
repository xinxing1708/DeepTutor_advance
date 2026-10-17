"""Mastery Path policy — pure decisions over a :class:`LearningProgress`.

No LLM calls, no I/O. This is the engine the chat-loop tutor consults each
turn. It answers three questions:

* **is this objective mastered?** (:func:`is_mastered` — a HARD, per-type gate)
* **what should the learner work on next?** (:func:`next_objective`)
* **what does the whole map look like?** (:func:`map_summary`)

The gate is the heart of mastery-based learning. An objective only counts as
mastered when the evidence clears its threshold, and :func:`next_objective`
keeps returning the same objective until it does — advancement is *computed
from what is mastered*, never tracked by a stage counter. Objective ordering
follows module order then knowledge-point order; an objective the learner has
already proven is skipped (the "test out" / compression path) because the gate
reads proven mastery, not a fixed sequence of stages.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from deeptutor.learning.models import (
    KnowledgePoint,
    KnowledgeType,
    LearningProgress,
    RepetitionState,
    ReviewTask,
)
from deeptutor.learning.pending import PublicPendingQuestion, public_pending_question

# Quantitative gate for objective knowledge types: the learner must reach this
# mastery (recency-weighted accuracy; see ``mastery.compute_mastery``) before
# the objective unlocks. ~0.9 mirrors Alpha School's "90% before you advance".
QUANTITATIVE_GATE: dict[KnowledgeType, float] = {
    KnowledgeType.MEMORY: 0.9,
    KnowledgeType.PROCEDURE: 0.9,
}

# CONCEPT / DESIGN are gated qualitatively — a Feynman-style explanation judged
# by the tutor via ``mastery_assess`` — rather than by string-graded accuracy,
# because there is rarely a single canonical right answer to match against.
QUALITATIVE_TYPES: frozenset[KnowledgeType] = frozenset(
    {KnowledgeType.CONCEPT, KnowledgeType.DESIGN}
)

# Display mastery a qualitative pass maps to, so the map's colours agree with
# the gate even though qualitative mastery is a boolean, not a score. (The
# fail-side display is handled in ``LearningService.record_qualitative``.)
_QUALITATIVE_PASS_DISPLAY = 1.0


def path_display_name(progress: LearningProgress) -> str:
    """What to call this path, everywhere it is named.

    A path's own :attr:`~deeptutor.learning.models.LearningProgress.name` wins.
    Without one the first module's name stands in, and failing that the storage
    id — the behaviour every surface implemented separately before this
    function existed, which is why rebuilding a map used to rename the path
    (``mastery_build`` replaces module one) and why three surfaces could
    disagree about the same path.

    Derivation is the fallback, never the record: a named path keeps its name
    across every rebuild.
    """
    named = str(progress.name or "").strip()
    if named:
        return named
    first_module = progress.modules[0].name.strip() if progress.modules else ""
    return first_module or progress.book_id


def gate_threshold(kp_type: KnowledgeType) -> float:
    """The quantitative mastery bar for *kp_type* (qualitative types report
    their pass-display value so callers have a single number to show)."""
    if kp_type in QUALITATIVE_TYPES:
        return _QUALITATIVE_PASS_DISPLAY
    return QUANTITATIVE_GATE.get(kp_type, 0.9)


_FACET_OPENERS = "（([【《「"
_FACET_CLOSERS = "）)]】》」"
_FACET_LIST_SEPARATORS = "、，,；;"
_FACET_HEADING_SEPARATORS = "：:"
_FACET_FINAL_CONNECTORS = ("以及", "及", "与", "和")


def _top_level_positions(text: str) -> set[int]:
    """Indexes of ``text`` that sit outside every bracket pair."""
    depth = 0
    positions: set[int] = set()
    for index, char in enumerate(text):
        if char in _FACET_OPENERS:
            depth += 1
        elif char in _FACET_CLOSERS:
            depth = max(0, depth - 1)
        elif depth == 0:
            positions.add(index)
    return positions


#: Local mastery-v2: explicit facet lists are bounded so one objective cannot
#: turn into a whole module of sub-gates.
MAX_DECLARED_FACETS = 6
#: Independent correct answers, on distinct questions, each part needs.
FACET_CORRECT_NEEDED = 2
#: ``objective_facets`` state version that applies the v2 per-part rule.
FACET_RULES_VERSION = 2


def declared_facets(kp: KnowledgePoint) -> list[str]:
    """The sub-skills declared on ``kp`` when the outline was designed.

    Fewer than two usable entries declare nothing: one part is the objective
    itself, so the name-derived split (or the single gate) stays in force.
    """
    unique: list[str] = []
    for raw in getattr(kp, "facets", None) or []:
        part = " ".join(str(raw or "").split())[:120]
        if part and part not in unique:
            unique.append(part)
    unique = unique[:MAX_DECLARED_FACETS]
    return unique if len(unique) >= 2 else []


def objective_facets(kp: KnowledgePoint) -> list[dict[str, str]]:
    """Independently testable parts listed in one knowledge point's name.

    An outline entry such as ``数据表示、校验码、逻辑运算与体系结构基础`` names
    several exam points, while the engine kept one gate for the whole entry, so
    evidence on one part (补码) cleared all of them. The parts are derived from
    the stored name, never from the tutor, so a tutor cannot narrow them. A
    name without a top-level enumeration returns ``[]`` and keeps the
    original single gate.
    """
    declared = declared_facets(kp)
    if declared:
        return [{"id": f"f{index}", "name": part} for index, part in enumerate(declared, start=1)]
    name = str(kp.name or "").strip()
    top = _top_level_positions(name)
    body = name
    for index in sorted(top):
        if name[index] in _FACET_HEADING_SEPARATORS and name[index + 1 :].strip():
            body = name[index + 1 :].strip()
            break
    body_top = _top_level_positions(body)
    parts: list[str] = []
    start = 0
    for index, char in enumerate(body):
        if index in body_top and char in _FACET_LIST_SEPARATORS:
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    cleaned: list[str] = []
    for part in parts:
        part = part.strip()
        # "…，以及作业管理基础": a connector after a separator is not content.
        for connector in _FACET_FINAL_CONNECTORS:
            # A bare "与" is an enumerated item (the AND operator), not a connector.
            if part.startswith(connector) and part != connector:
                part = part[len(connector) :].strip()
                break
        if part:
            cleaned.append(part)
    parts = cleaned
    if len(parts) < 2:
        return []
    # A Chinese enumeration ends "A、B与C": the last connector joins two items.
    last = parts[-1]
    last_top = _top_level_positions(last)
    cut, width = -1, 0
    for connector in _FACET_FINAL_CONNECTORS:
        found = last.rfind(connector)
        while found > 0 and found not in last_top:
            found = last.rfind(connector, 0, found)
        if found > cut:
            cut, width = found, len(connector)
    if cut > 0 and last[cut + width :].strip():
        parts[-1:] = [last[:cut].strip(), last[cut + width :].strip()]
    # "与、或、非、异或的真值" enumerates operators, not separately taught parts.
    if sum(len(part) <= 1 for part in parts) * 2 > len(parts):
        return []
    unique: list[str] = []
    for part in parts:
        if part not in unique:
            unique.append(part)
    if len(unique) < 2:
        return []
    return [{"id": f"f{index}", "name": part} for index, part in enumerate(unique, start=1)]


def match_facet(kp: KnowledgePoint, raw: Any) -> dict[str, str] | None:
    """Resolve a facet reference by id, exact name, or one unambiguous substring."""
    wanted = str(raw or "").strip()
    if not wanted:
        return None
    facets = objective_facets(kp)
    for facet in facets:
        if wanted.lower() == facet["id"] or wanted == facet["name"]:
            return facet
    loose = [facet for facet in facets if wanted in facet["name"] or facet["name"] in wanted]
    return loose[0] if len(loose) == 1 else None


def facet_report(progress: LearningProgress, kp: KnowledgePoint) -> list[dict[str, Any]]:
    """Every derived part of ``kp`` and whether it has its own passing evidence.

    Quiz coverage is derived from the attempt log, so voiding or re-grading an
    attempt with ``mastery_repair_question`` changes coverage with it.

    Local mastery-v2 rule (tracking state ``v == 2``): a part is covered by
    quiz evidence only after ``FACET_CORRECT_NEEDED`` independent correct
    answers on distinct questions, with no outstanding error debt on that part
    (each wrong answer must be repaid by later correct answers on the same
    part). Tracking states written before v2 keep the original one-correct
    rule, so a part earned under it is never revoked.
    """
    from deeptutor.learning.mastery import error_debt

    facets = objective_facets(kp)
    if not facets:
        return []
    state = progress.objective_facets.get(kp.id) or {}
    strict = state.get("v") == FACET_RULES_VERSION or kp.id not in progress.objective_facets
    needed = FACET_CORRECT_NEEDED if strict else 1
    assessed = set(state.get("covered") or [])
    attempts_by_facet: dict[str, list[Any]] = {}
    for attempt in progress.quiz_attempts:
        if (
            attempt.knowledge_point_id == kp.id
            and attempt.independent
            and not attempt.voided
            and attempt.facet_id
        ):
            attempts_by_facet.setdefault(attempt.facet_id, []).append(attempt)
    report: list[dict[str, Any]] = []
    for facet in facets:
        attempts = attempts_by_facet.get(facet["id"], [])
        correct = len({attempt.question_id for attempt in attempts if attempt.is_correct})
        debt = sum(error_debt(attempts).values()) if strict else 0
        quiz_covered = correct >= needed and debt == 0
        report.append(
            {
                "id": facet["id"],
                "name": facet["name"],
                "covered": facet["id"] in assessed or quiz_covered,
                "correct": correct,
                "needed": needed,
                "debt": debt,
            }
        )
    return report


def facet_gate_applies(progress: LearningProgress, kp: KnowledgePoint) -> bool:
    """Whether new evidence on ``kp`` must name the part it tests."""
    if not objective_facets(kp):
        return False
    return kp.id in progress.objective_facets or not is_assessed_mastered(progress, kp)


def remaining_facets(progress: LearningProgress, kp: KnowledgePoint) -> list[dict[str, Any]]:
    """Tracked parts of ``kp`` that still lack passing evidence."""
    if kp.id not in progress.objective_facets:
        return []
    return [facet for facet in facet_report(progress, kp) if not facet["covered"]]


def is_assessed_mastered(progress: LearningProgress, kp: KnowledgePoint) -> bool:
    """Whether ``kp`` clears its mastery gate.

    * MEMORY / PROCEDURE: recency-weighted accuracy ≥ the type's threshold.
    * CONCEPT / DESIGN: a recorded qualitative pass (``mastery_assess``).
    * A tracked multi-part objective also needs evidence on every part.

    Tracking starts the first time a facet-aware tool touches the objective.
    A pass recorded before tracking existed is left as earned.
    """
    if not set(kp.required_visual_tasks).issubset(visual_achievements(progress, kp.id)):
        return False
    if remaining_facets(progress, kp):
        return False
    if kp.type in QUALITATIVE_TYPES:
        return bool(progress.qualitative_mastery.get(kp.id, False))
    if not has_strong_evidence(progress, kp.id):
        return False
    return progress.mastery_levels.get(kp.id, 0.0) >= gate_threshold(kp.type)


#: Local mastery-v2: how many recent independent attempts the strong-evidence
#: rule looks back over (matches the scoring window in ``mastery.py``).
STRONG_EVIDENCE_WINDOW = 6


def _is_strong(attempt: Any) -> bool:
    qtype = str(getattr(attempt, "question_type", "") or "")
    if not qtype:
        # Recorded before the question type was stored: earned under the old
        # rules, so it is not demoted now.
        return True
    return qtype != "choice" or str(getattr(attempt, "difficulty", "") or "") == "hard"


def has_strong_evidence(progress: LearningProgress, kp_id: str) -> bool:
    """Whether recent correct answers on ``kp_id`` include more than easy picks.

    Local mastery-v2: a quantitative gate needs at least one correct answer,
    among the last ``STRONG_EVIDENCE_WINDOW`` independent attempts, that the
    learner *produced* (short / open) or that was a hard question. A run of
    ordinary multiple-choice picks alone cannot clear it. Objectives with no
    typed (v2) attempt are unaffected.
    """
    attempts = [
        attempt
        for attempt in progress.quiz_attempts
        if attempt.knowledge_point_id == kp_id and attempt.independent and not attempt.voided
    ]
    if not any(getattr(attempt, "question_type", "") for attempt in attempts):
        return True
    recent = attempts[-STRONG_EVIDENCE_WINDOW:]
    return any(attempt.is_correct and _is_strong(attempt) for attempt in recent)


def gate_blockers(progress: LearningProgress, kp: KnowledgePoint) -> list[str]:
    """Human-readable reasons ``kp`` has not cleared its gate yet (for the tutor)."""
    from deeptutor.learning.mastery import error_debt

    if is_assessed_mastered(progress, kp):
        return []
    blockers: list[str] = []
    for facet in remaining_facets(progress, kp):
        need = max(0, int(facet.get("needed", 1)) - int(facet.get("correct", 0)))
        detail = f"part {facet['id']} ({facet['name']}): "
        parts = []
        if need:
            parts.append(f"needs {need} more independent correct answer(s) on new questions")
        if facet.get("debt"):
            parts.append(f"has error debt {facet['debt']} to repay with correct answers")
        blockers.append(detail + ("; ".join(parts) or "needs passing evidence"))
    if kp.type in QUALITATIVE_TYPES:
        if not progress.qualitative_mastery.get(kp.id):
            blockers.append("needs a qualitative pass recorded with mastery_assess")
        return blockers
    attempts = [
        attempt
        for attempt in progress.quiz_attempts
        if attempt.knowledge_point_id == kp.id and attempt.independent and not attempt.voided
    ]
    debt = sum(error_debt(attempts).values())
    if debt:
        blockers.append(
            f"error debt {debt}: earlier wrong answers must be repaid by later correct ones"
        )
    if not has_strong_evidence(progress, kp.id):
        blockers.append(
            "needs a correct produced answer (short/open) or a hard question — "
            "multiple-choice picks alone cannot clear this gate"
        )
    level = progress.mastery_levels.get(kp.id, 0.0)
    if level < gate_threshold(kp.type):
        blockers.append(f"mastery {level:.2f} is below the {gate_threshold(kp.type):.2f} gate")
    return blockers


def visual_achievements(progress: LearningProgress, kp_id: str) -> list[str]:
    """Independent source-verified visual tasks, separate from generic text scores."""
    return sorted(
        {
            event.visual_context["task"]
            for event in progress.learning_evidence
            if event.knowledge_point_id == kp_id
            and event.result == "correct"
            and event.visual_context.get("task")
            and event.visual_context.get("key_status") == "verified"
            and not event.hints_used
        }
    )


def learning_stage(progress: LearningProgress, kp_id: str) -> str:
    attempts = [
        item
        for item in progress.quiz_attempts
        if item.knowledge_point_id == kp_id and not item.voided
    ]
    evidence = [item for item in progress.learning_evidence if item.knowledge_point_id == kp_id]
    if any(item.independent and item.is_correct for item in attempts) or any(
        item.assessment_type == "qualitative" and item.result == "correct" and not item.hints_used
        for item in evidence
    ):
        return "independently_demonstrated"
    if any(not item.independent for item in attempts) or any(item.hints_used for item in evidence):
        return "practiced_with_help"
    if attempts or evidence:
        return "practiced_not_demonstrated"
    return "explained" if kp_id in progress.explained_objectives else "not_yet_covered"


def mastery_source(progress: LearningProgress, kp: KnowledgePoint) -> str:
    """Return ``system`` or ``learner`` provenance for a cleared waypoint."""

    if is_assessed_mastered(progress, kp):
        return "system"
    if kp.id in progress.learner_mastery_overrides:
        return "learner"
    return ""


def is_mastered(progress: LearningProgress, kp: KnowledgePoint) -> bool:
    """Whether the route may advance past ``kp``.

    The deterministic assessed gate remains available through
    :func:`is_assessed_mastered`.  An explicit learner claim may advance the
    route, but every public report exposes that different provenance.
    """

    return bool(mastery_source(progress, kp))


def display_mastery(progress: LearningProgress, kp: KnowledgePoint) -> float:
    """A 0..1 number for the map UI. Qualitatively-mastered points show full;
    otherwise the recency-weighted accuracy stands in."""
    if kp.type in QUALITATIVE_TYPES and progress.qualitative_mastery.get(kp.id):
        return _QUALITATIVE_PASS_DISPLAY
    return float(progress.mastery_levels.get(kp.id, 0.0))


def objective_status(progress: LearningProgress, kp: KnowledgePoint) -> str:
    """``"mastered"`` | ``"learning"`` | ``"new"`` for one knowledge point."""
    if is_mastered(progress, kp):
        return "mastered"
    seen = any(a.knowledge_point_id == kp.id for a in progress.quiz_attempts) or (
        kp.id in progress.qualitative_mastery
    )
    return "learning" if seen else "new"


def due_reviews(progress: LearningProgress, *, now: float | None = None) -> list[ReviewTask]:
    """Spaced-repetition tasks whose ``due_at`` has passed, highest forgetting
    risk first. Pure read over ``progress.review_queue`` (built by the scheduler)."""
    from deeptutor.learning.scheduler import review_sort_key

    moment = time.time() if now is None else now
    due = [task for task in progress.review_queue if task.due_at <= moment]
    due.sort(key=lambda task: review_sort_key(task, now=moment))
    return due


@dataclass(frozen=True)
class NextStep:
    """What the tutor should do next, decided by the gate — not a stage cursor.

    ``action`` is advisory for the model's pedagogy; the binding fact is the
    objective and whether it is mastered. Values:

    * ``answer_pending`` — a posed question awaits the learner's answer.
    * ``review`` — a spaced-repetition item is due.
    * ``probe`` — an untouched objective; test out before teaching.
    * ``teach`` — teach an untouched objective before assessing it, by request.
    * ``practice`` — a quantitative objective below its gate.
    * ``assess`` — a qualitative objective awaiting a Feynman-style check.
    * ``complete`` — every objective mastered, nothing due.
    """

    action: str
    module_id: str = ""
    module_name: str = ""
    knowledge_point_id: str = ""
    knowledge_point_name: str = ""
    knowledge_point_type: str = ""
    status: str = ""
    gate: str = ""
    mastery: float = 0.0
    threshold: float = 0.0
    reason: str = ""
    forgetting_risk: float = 0.0
    pending_prompt: str = ""
    pending_question: PublicPendingQuestion | None = None
    session_id: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "module_id": self.module_id,
            "module_name": self.module_name,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point_name": self.knowledge_point_name,
            "knowledge_point_type": self.knowledge_point_type,
            "status": self.status,
            "gate": self.gate,
            "mastery": round(self.mastery, 3),
            "threshold": round(self.threshold, 3),
            "reason": self.reason,
            "forgetting_risk": round(self.forgetting_risk, 3),
            "pending_prompt": self.pending_prompt,
            "pending_question": (
                self.pending_question.to_dict() if self.pending_question is not None else None
            ),
            "session_id": self.session_id,
        }


def find_knowledge_point(
    progress: LearningProgress, kp_id: str
) -> tuple[KnowledgePoint | None, str, str]:
    """Return ``(kp, module_id, module_name)`` for *kp_id*, or ``(None, "", "")``."""
    for module in progress.modules:
        for kp in module.knowledge_points:
            if kp.id == kp_id:
                return kp, module.id, module.name
    return None, "", ""


def gate_kind(kp: KnowledgePoint) -> str:
    """Which gate ``kp`` has to clear — ``qualitative`` or ``quantitative``.

    Public because the tutor's tools report it too: a quiz attempt on a
    qualitative objective moves ``mastery_levels`` without moving the gate,
    so every surface that shows a mastery number has to be able to say which
    kind of gate that number is being read against.
    """
    return "qualitative" if kp.type in QUALITATIVE_TYPES else "quantitative"


def next_objective(
    progress: LearningProgress,
    *,
    now: float | None = None,
    pending_session_id: str = "",
) -> NextStep:
    """Decide the next thing to work on. Order of precedence:

    1. an outstanding posed question (grade it before moving on);
    2. a due spaced-repetition review (don't let mastered ground decay);
    3. the first not-yet-mastered objective in module/KP order (the gate IS
       the cursor — mastered objectives are skipped);
    4. otherwise the path is complete.
    """
    pending = progress.pending_question
    if pending is not None:
        kp, module_id, module_name = find_knowledge_point(progress, pending.knowledge_point_id)
        return NextStep(
            action="answer_pending",
            module_id=module_id or pending.module_id,
            module_name=module_name,
            knowledge_point_id=pending.knowledge_point_id,
            knowledge_point_name=kp.name if kp else "",
            knowledge_point_type=kp.type.value if kp else "",
            status=objective_status(progress, kp) if kp else "learning",
            gate=gate_kind(kp) if kp else "",
            mastery=display_mastery(progress, kp) if kp else 0.0,
            threshold=gate_threshold(kp.type) if kp else 0.0,
            reason="A posed question is awaiting the learner's answer; grade it with mastery_grade.",
            pending_prompt=pending.prompt,
            pending_question=public_pending_question(pending),
            session_id=str(pending_session_id or ""),
        )

    deferred_ids = set(progress.deferred_objectives)
    due = [
        task
        for task in due_reviews(progress, now=now)
        if task.knowledge_point_id not in deferred_ids
    ]
    if due:
        kp, module_id, module_name = find_knowledge_point(progress, due[0].knowledge_point_id)
        if kp is not None:
            task = due[0]
            return NextStep(
                action="review",
                module_id=module_id,
                module_name=module_name,
                knowledge_point_id=kp.id,
                knowledge_point_name=kp.name,
                knowledge_point_type=kp.type.value,
                status=objective_status(progress, kp),
                gate=gate_kind(kp),
                mastery=display_mastery(progress, kp),
                threshold=gate_threshold(kp.type),
                reason=(task.reason or "This objective is due for spaced-repetition review."),
                forgetting_risk=task.forgetting_risk,
            )

    deferred_fallback: NextStep | None = None
    for module in sorted(progress.modules, key=lambda m: m.order):
        for kp in module.knowledge_points:
            if is_mastered(progress, kp):
                continue
            status = objective_status(progress, kp)
            gate = gate_kind(kp)
            if status == "new":
                action = (
                    "teach"
                    if progress.learner_profile is not None
                    and progress.learner_profile.teaching_strategy == "teach_first"
                    else "probe"
                )
            elif gate == "qualitative":
                action = "assess"
            else:
                action = "practice"
            step = NextStep(
                action=action,
                module_id=module.id,
                module_name=module.name,
                knowledge_point_id=kp.id,
                knowledge_point_name=kp.name,
                knowledge_point_type=kp.type.value,
                status=status,
                gate=gate,
                mastery=display_mastery(progress, kp),
                threshold=gate_threshold(kp.type),
                reason=(
                    (
                        "Untouched objective — teach before assessing, as the learner requested."
                        if action == "teach"
                        else "Untouched objective — probe first to let the learner test out."
                    )
                    if status == "new"
                    else "Objective is below its mastery gate; keep working it until it clears."
                ),
            )
            if kp.id in deferred_ids:
                if deferred_fallback is None:
                    deferred_fallback = step
                continue
            return step

    if deferred_fallback is not None:
        return deferred_fallback

    return NextStep(action="complete", reason="All objectives are mastered and no reviews are due.")


def map_summary(progress: LearningProgress, *, now: float | None = None) -> dict:
    """A compact, render-ready snapshot of the whole path for the tutor's
    ``mastery_status`` tool and the dashboard."""
    counts = {"mastered": 0, "learning": 0, "new": 0, "total": 0}
    modules_out: list[dict] = []
    for module in sorted(progress.modules, key=lambda m: m.order):
        kps_out: list[dict] = []
        mastered = 0
        for kp in module.knowledge_points:
            status = objective_status(progress, kp)
            counts[status] += 1
            counts["total"] += 1
            if status == "mastered":
                mastered += 1
            kps_out.append(
                {
                    "id": kp.id,
                    "name": kp.name,
                    "type": kp.type.value,
                    "prerequisite_ids": list(kp.prerequisite_ids),
                    "topic_source_ids": list(kp.topic_source_ids),
                    "status": status,
                    "mastery": round(display_mastery(progress, kp), 3),
                    "mastery_source": mastery_source(progress, kp),
                    "override_note": (
                        progress.learner_mastery_overrides[kp.id].note
                        if kp.id in progress.learner_mastery_overrides
                        else ""
                    ),
                    "deferred": kp.id in progress.deferred_objectives,
                    # Listed parts of a multi-part objective. ``facet_gate``
                    # true means every part needs its own passing evidence.
                    "facets": facet_report(progress, kp),
                    "facet_gate": kp.id in progress.objective_facets,
                    "pitfalls": list(getattr(kp, "pitfalls", None) or []),
                }
            )
        modules_out.append(
            {
                "id": module.id,
                "name": module.name,
                # What the module is for. Empty on outlines built before the
                # field existed; every reader falls back to the name.
                "objective": module.objective,
                "order": module.order,
                "mastered": mastered,
                "total": len(module.knowledge_points),
                # A module's verdict is computed from every current waypoint,
                # not inferred from the most recently passed one. Keep the
                # unfinished list beside the verdict so tutor and UI can name
                # the exact work still open after an outline is revised.
                "complete": bool(kps_out) and mastered == len(kps_out),
                "remaining": [
                    {"id": point["id"], "name": point["name"], "status": point["status"]}
                    for point in kps_out
                    if point["status"] != "mastered"
                ],
                "knowledge_points": kps_out,
            }
        )
    return {
        "name": path_display_name(progress),
        "counts": counts,
        "due_reviews": len(due_reviews(progress, now=now)),
        "complete": counts["total"] > 0 and counts["mastered"] == counts["total"],
        "modules": modules_out,
    }


def _review_report(
    progress: LearningProgress,
    kp_id: str,
    state: RepetitionState | None,
    due_at: float | None,
    *,
    now: float,
) -> dict | None:
    if state is None:
        return None
    task = next((item for item in progress.review_queue if item.knowledge_point_id == kp_id), None)
    from deeptutor.learning.scheduler import SpacedRepetitionScheduler

    scheduler = SpacedRepetitionScheduler()
    recall = scheduler.retrievability(state, now=now)
    risk = (
        task.forgetting_risk
        if task is not None
        else scheduler.forgetting_risk(state, progress, kp_id, now=now)
    )
    reason = (
        task.reason
        if task is not None
        else scheduler.review_reason(state, progress, kp_id, now=now)
    )
    return {
        "due_at": due_at,
        "interval_index": state.interval_index,
        "consecutive_correct": state.consecutive_correct,
        "consecutive_wrong": state.consecutive_wrong,
        "stability": round(state.stability, 3),
        "retrievability": round(recall, 3),
        "desired_retention": state.desired_retention,
        "lapse_count": state.lapse_count,
        "forgetting_risk": round(risk, 3),
        "reason": reason,
        "recent_failure": bool(
            state.consecutive_wrong
            or any(
                record.knowledge_point_id == kp_id and record.status in ("active", "retrying")
                for record in progress.error_records
            )
        ),
    }


def objective_report(
    progress: LearningProgress, kp_id: str, *, now: float | None = None
) -> dict | None:
    """Everything the engine knows about one objective, for review.

    ``map_summary`` stays deliberately thin because the tutor reads it on every
    turn; this is the opposite trade — the whole evidence trail behind a single
    objective, read only when someone opens it. ``None`` when *kp_id* is not on
    the path.
    """
    kp, module_id, module_name = find_knowledge_point(progress, kp_id)
    if kp is None:
        return None

    attempts = [
        {
            "question_id": attempt.question_id,
            "is_correct": attempt.is_correct,
            "independent": attempt.independent,
            "question_type": getattr(attempt, "question_type", ""),
            "difficulty": getattr(attempt, "difficulty", ""),
            "facet_id": attempt.facet_id,
            "answer": str(attempt.user_answer or ""),
            "error_type": attempt.error_type.value if attempt.error_type else "",
            "at": attempt.timestamp,
        }
        for attempt in progress.quiz_attempts
        if attempt.knowledge_point_id == kp_id
    ]
    state = progress.repetition_states.get(kp_id)
    due_at = next(
        (task.due_at for task in progress.review_queue if task.knowledge_point_id == kp_id),
        None,
    )
    moment = time.time() if now is None else now
    return {
        "id": kp.id,
        "name": kp.name,
        "type": kp.type.value,
        "module_id": module_id,
        "module_name": module_name,
        "status": objective_status(progress, kp),
        "gate": gate_kind(kp),
        "mastered": is_mastered(progress, kp),
        "assessed_mastered": is_assessed_mastered(progress, kp),
        "mastery_source": mastery_source(progress, kp),
        "override_note": (
            progress.learner_mastery_overrides[kp_id].note
            if kp_id in progress.learner_mastery_overrides
            else ""
        ),
        "mastery": round(display_mastery(progress, kp), 3),
        "threshold": round(gate_threshold(kp.type), 3),
        "attempts": attempts,
        "correct_count": sum(1 for attempt in attempts if attempt["is_correct"]),
        # The learner's own words, kept as the evidence behind a qualitative pass.
        "explanation": progress.feynman_explanations.get(kp_id, ""),
        "explained": progress.explained_objectives.get(kp_id),
        "facets": facet_report(progress, kp),
        "facet_gate": kp_id in progress.objective_facets,
        # Local mastery-v2: declared traps to teach and probe, and the exact
        # reasons the gate is still closed.
        "pitfalls": list(getattr(kp, "pitfalls", None) or []),
        "gate_blockers": gate_blockers(progress, kp),
        "required_visual_tasks": kp.required_visual_tasks,
        "demonstrated_visual_tasks": visual_achievements(progress, kp_id),
        "review": _review_report(progress, kp_id, state, due_at, now=moment),
        "errors": [
            {
                "id": record.id,
                "error_type": record.error_type.value,
                "status": record.status,
                "self_attribution": record.self_attribution,
                "retries": len(record.retry_history),
                "created_at": record.created_at,
            }
            for record in progress.error_records
            if record.knowledge_point_id == kp_id
        ],
    }


__all__ = [
    "QUANTITATIVE_GATE",
    "QUALITATIVE_TYPES",
    "NextStep",
    "gate_blockers",
    "gate_kind",
    "gate_threshold",
    "has_strong_evidence",
    "is_assessed_mastered",
    "is_mastered",
    "mastery_source",
    "display_mastery",
    "objective_status",
    "objective_report",
    "due_reviews",
    "find_knowledge_point",
    "next_objective",
    "map_summary",
    "path_display_name",
]
