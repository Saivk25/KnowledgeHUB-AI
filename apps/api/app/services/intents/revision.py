"""
RevisionIntent (Milestone 10): a pure read, zero LLM calls, zero new
frozen-file touches (approved design, MILESTONE_10.md Section 4 decision
3). Surfaces concepts that need attention, derived entirely from this
milestone's own quiz/viva history plus the existing concept graph --
never from retrofitting Milestone 8/9's frozen Explain/Search/Summarize/
Compare handlers to log per-concept exposure. See
app/services/study_signals.py's assess_review_need(), shared with
StudyPlannerIntent.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.concept import Concept, ConceptStatus
from app.models.workspace import Workspace
from app.schemas.intents import IntentRequest, IntentResponse, IntentType, RevisionItemOut, RevisionResult
from app.services.intents.base import IntentHandler
from app.services.study_signals import assess_review_need

settings = get_settings()


class RevisionIntent(IntentHandler):
    intent_type = IntentType.REVISION

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        concepts = (
            db.query(Concept)
            .filter(Concept.workspace_id == workspace.id, Concept.status == ConceptStatus.ACTIVE)
            .all()
        )

        items: list[RevisionItemOut] = []
        reviewed_count = 0
        for concept in concepts:
            assessment = assess_review_need(db, workspace.id, concept_id=concept.id)
            if assessment.reviewed:
                reviewed_count += 1
            items.append(
                RevisionItemOut(
                    label=concept.name,
                    conceptId=concept.id,
                    reason=assessment.reason,
                    priority=assessment.priority,
                )
            )

        items.sort(key=lambda i: i.priority)
        items = items[: settings.REVISION_MAX_ITEMS]

        sufficiency_score = (reviewed_count / len(concepts)) if concepts else 1.0

        return IntentResponse(
            intent=IntentType.REVISION,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=sufficiency_score,
            retrievalConfidence=1.0,
            canOfferExternalFallback=False,
            citations=[],
            result=RevisionResult(items=items),
        )
