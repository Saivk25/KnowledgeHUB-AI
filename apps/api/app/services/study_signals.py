"""
Shared "what needs review" signal (Milestone 10), used by both
app/services/intents/revision.py and app/services/intents/study_planner.py
-- one implementation, not two, mirroring how Compare and Summarize
already share retrieval_service.py's resolve_* evidence-resolution
helpers rather than each re-implementing evidence resolution.

Derives entirely from this milestone's own `quiz_attempts`/`viva_sessions`
history plus the existing concept graph's evidence density -- never from
retrofitting Milestone 8/9's frozen Explain/Search/Summarize/Compare
handlers to log per-concept exposure (approved design, MILESTONE_10.md
Section 4 decision 3). A concept/resource that has never been quizzed or
viva'd is honestly reported as "never reviewed," not silently assumed
fine -- the same fail-closed-by-construction discipline
app/services/sufficiency.py already uses for local-answer provenance,
applied here to "does this need attention."
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.concept import ResourceConcept
from app.models.study import QuizAttempt, QuizAttemptStatus, VivaSession, VivaSessionStatus

settings = get_settings()


@dataclass
class ReviewAssessment:
    reviewed: bool  # at least one graded quiz or completed viva exists
    last_score: float | None  # most recent graded quiz's score, if any
    evidence_count: int  # distinct resources evidencing this concept (0 for a resource target)
    reason: str  # human-readable, e.g. "Never reviewed" | "Last quiz: 40%"
    priority: int  # 1 = most urgent, lower always sorts first


def _most_recent_graded_quiz(
    db: Session, workspace_id: str, resource_id: str | None, concept_id: str | None
) -> QuizAttempt | None:
    if not resource_id and not concept_id:
        return None
    query = db.query(QuizAttempt).filter(
        QuizAttempt.workspace_id == workspace_id, QuizAttempt.status == QuizAttemptStatus.GRADED
    )
    query = (
        query.filter(QuizAttempt.resource_id == resource_id)
        if resource_id
        else query.filter(QuizAttempt.concept_id == concept_id)
    )
    return query.order_by(QuizAttempt.graded_at.desc()).first()


def _has_completed_viva(
    db: Session, workspace_id: str, resource_id: str | None, concept_id: str | None
) -> bool:
    if not resource_id and not concept_id:
        return False
    query = db.query(VivaSession).filter(
        VivaSession.workspace_id == workspace_id, VivaSession.status == VivaSessionStatus.COMPLETED
    )
    query = (
        query.filter(VivaSession.resource_id == resource_id)
        if resource_id
        else query.filter(VivaSession.concept_id == concept_id)
    )
    return db.query(query.exists()).scalar() or False


def assess_review_need(
    db: Session,
    workspace_id: str,
    resource_id: str | None = None,
    concept_id: str | None = None,
) -> ReviewAssessment:
    """Exactly one of `resource_id`/`concept_id` should be set, matching
    every other target-resolution helper in this codebase (Summarize,
    Compare, Flashcards)."""
    last_quiz = _most_recent_graded_quiz(db, workspace_id, resource_id, concept_id)
    reviewed_by_viva = _has_completed_viva(db, workspace_id, resource_id, concept_id)

    evidence_count = 0
    if concept_id:
        evidence_count = (
            db.query(func.count(func.distinct(ResourceConcept.resource_id)))
            .filter(ResourceConcept.concept_id == concept_id)
            .scalar()
            or 0
        )

    if last_quiz is None and not reviewed_by_viva:
        return ReviewAssessment(
            reviewed=False,
            last_score=None,
            evidence_count=evidence_count,
            reason="Never reviewed",
            priority=1,
        )

    if last_quiz is not None and last_quiz.score is not None:
        if last_quiz.score < settings.REVISION_LOW_SCORE_THRESHOLD:
            return ReviewAssessment(
                reviewed=True,
                last_score=last_quiz.score,
                evidence_count=evidence_count,
                reason=f"Last quiz: {last_quiz.score:.0%}",
                priority=2,
            )

    if concept_id and evidence_count <= 1:
        reason = "Only 1 source linked" if evidence_count == 1 else "No sources linked yet"
        return ReviewAssessment(
            reviewed=True,
            last_score=last_quiz.score if last_quiz else None,
            evidence_count=evidence_count,
            reason=reason,
            priority=3,
        )

    return ReviewAssessment(
        reviewed=True,
        last_score=last_quiz.score if last_quiz else None,
        evidence_count=evidence_count,
        reason="Reviewed recently, no action needed",
        priority=4,
    )
