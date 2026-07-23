"""
StudyPlannerIntent (Milestone 10): a deterministic scheduling algorithm
(never LLM-decided) for which targets go on which day, plus one batched
LLMProvider.narrate_study_plan() call to phrase the already-decided
schedule (approved design, MILESTONE_10.md Section 4 decision 4). Reuses
CompareTarget's exact shape and the same resource/concept/freeform
resolution modes Compare/Summarize/Flashcards already use, plus
app/services/study_signals.py's assess_review_need() (shared with
RevisionIntent) for prioritization. A target with no resolvable evidence
is scheduled anyway and labeled honestly, never silently dropped --
mirrors Compare's approved "label the gap, never fill it" precedent
(MILESTONE_9.md Section 4 decision 1).
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.deps import AppError
from app.models.concept import Concept
from app.models.resource import Resource, ResourceStatus
from app.models.workspace import Workspace
from app.schemas.intents import (
    CompareTarget,
    IntentRequest,
    IntentResponse,
    IntentType,
    StudyPlanDayOut,
    StudyPlanResult,
)
from app.services.intents.base import IntentHandler
from app.services.llm import StudyDayDraft, get_llm_provider
from app.services.study_signals import assess_review_need

settings = get_settings()


class _ResolvedTarget:
    def __init__(self, label: str, priority: int, reason: str, has_evidence: bool):
        self.label = label
        self.priority = priority
        self.reason = reason
        self.has_evidence = has_evidence


class StudyPlannerIntent(IntentHandler):
    intent_type = IntentType.STUDY_PLAN

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        targets = request.targets or []
        if len(targets) < 2:
            raise AppError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "STUDY_PLAN_NEEDS_TWO_TARGETS",
                "Study planner needs at least two targets.",
            )

        horizon_days = request.horizonDays or settings.STUDY_PLANNER_DEFAULT_HORIZON_DAYS
        if request.targetDate:
            horizon_days = (request.targetDate - date.today()).days
            if horizon_days < 1:
                raise AppError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "STUDY_PLAN_TARGET_DATE_IN_PAST",
                    "targetDate must be at least one day in the future.",
                )
        if horizon_days > settings.STUDY_PLANNER_MAX_HORIZON_DAYS:
            raise AppError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "STUDY_PLAN_HORIZON_TOO_LONG",
                f"Study planner accepts at most {settings.STUDY_PLANNER_MAX_HORIZON_DAYS} days.",
            )

        resolved = [self._resolve(db, workspace, t) for t in targets]
        resolved.sort(key=lambda r: r.priority)

        days = self._schedule(resolved, horizon_days, request.targetDate)

        narrations = get_llm_provider().narrate_study_plan(
            [StudyDayDraft(day=d.day, targets=d.targets, reason=d.note) for d in days]
        )
        for day_out, narration in zip(days, narrations, strict=True):
            day_out.note = narration

        has_gap = any(not r.has_evidence for r in resolved)

        return IntentResponse(
            intent=IntentType.STUDY_PLAN,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=1.0 if not has_gap else 0.5,
            retrievalConfidence=1.0 if not has_gap else 0.5,
            canOfferExternalFallback=has_gap,
            citations=[],
            result=StudyPlanResult(days=days),
        )

    def _resolve(self, db: Session, workspace: Workspace, target: CompareTarget) -> _ResolvedTarget:
        if target.resourceId:
            resource = db.get(Resource, target.resourceId)
            not_ready = (
                resource is None
                or resource.workspace_id != workspace.id
                or resource.status != ResourceStatus.READY
            )
            if not_ready:
                return _ResolvedTarget(
                    target.label, priority=1, reason="Resource not found or not ready", has_evidence=False
                )
            assessment = assess_review_need(db, workspace.id, resource_id=target.resourceId)
            return _ResolvedTarget(target.label, assessment.priority, assessment.reason, has_evidence=True)

        if target.conceptId:
            concept = db.get(Concept, target.conceptId)
            if concept is None or concept.workspace_id != workspace.id:
                return _ResolvedTarget(
                    target.label, priority=1, reason="Concept not found", has_evidence=False
                )
            assessment = assess_review_need(db, workspace.id, concept_id=target.conceptId)
            return _ResolvedTarget(target.label, assessment.priority, assessment.reason, has_evidence=True)

        # Freeform topic: no concept/resource id to assess review history
        # against -- treated as needing attention by default rather than
        # silently deprioritized just because it's a freeform phrase.
        return _ResolvedTarget(target.label, priority=1, reason="Never reviewed", has_evidence=True)

    def _schedule(
        self, resolved: list[_ResolvedTarget], horizon_days: int, target_date: date | None
    ) -> list[StudyPlanDayOut]:
        days: list[StudyPlanDayOut] = []
        per_day = max(1, -(-len(resolved) // max(horizon_days, 1)))  # ceil division, >=1 target/day
        index = 0
        for day_number in range(1, horizon_days + 1):
            if index >= len(resolved):
                break
            day_targets = resolved[index : index + per_day]
            index += per_day
            reason = day_targets[0].reason if day_targets else "Review"
            day_date = (date.today() + timedelta(days=day_number)) if target_date else None
            days.append(
                StudyPlanDayOut(
                    day=day_number,
                    date=day_date,
                    targets=[t.label for t in day_targets],
                    note=reason,
                )
            )
        return days
