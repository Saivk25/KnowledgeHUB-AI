"""
VivaIntent (Milestone 10): a genuinely multi-turn, adaptive intent. A
start turn (no `sessionId`) creates a VivaSession and asks question 1; a
continuation turn (`sessionId` + `vivaAnswer`) grades the previous
question against its stored rubric and asks the next one, or completes
the session at VIVA_MAX_TURNS. All server-side-only state (the rubric
for the question currently being asked, the full transcript) lives in
VivaSession.transcript_payload -- never in anything returned to the
client (see app/models/study.py's docstring). See
docs/milestones/MILESTONE_10.md Section 3.3.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.deps import AppError
from app.models.concept import Concept
from app.models.resource import Resource, ResourceStatus
from app.models.study import VivaSession, VivaSessionStatus
from app.models.workspace import Workspace
from app.schemas.chat import CitationOut
from app.schemas.intents import IntentRequest, IntentResponse, IntentType, VivaEvaluationOut, VivaResult
from app.services.intents.base import IntentHandler
from app.services.llm import EvidenceChunk, VivaTurnRecord, get_llm_provider
from app.services.retrieval_service import (
    CitationResult,
    resolve_concept_evidence,
    resolve_freeform_evidence,
    resolve_resource_evidence,
)

settings = get_settings()


def _citation_dicts(citations: list[CitationResult]) -> list[dict]:
    return [
        {
            "documentId": c.document_id,
            "documentFilename": c.document_filename,
            "chunkId": c.chunk_id,
            "pageNumber": c.page_number,
            "excerpt": c.excerpt,
            "order": c.order,
        }
        for c in citations
    ]


def _insufficient(target: str) -> IntentResponse:
    return IntentResponse(
        intent=IntentType.VIVA,
        status="INSUFFICIENT",
        provenance=None,
        sufficiencyScore=0.0,
        retrievalConfidence=0.0,
        canOfferExternalFallback=False,
        citations=[],
        result=VivaResult(sessionId="", target=target, isComplete=True, turnNumber=0),
    )


class VivaIntent(IntentHandler):
    intent_type = IntentType.VIVA

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        if request.sessionId:
            return self._continue(db, workspace, request)
        return self._start(db, workspace, request)

    def _start(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        if request.resourceId:
            resource = db.get(Resource, request.resourceId)
            if resource is None or resource.workspace_id != workspace.id:
                raise AppError(status.HTTP_404_NOT_FOUND, "RESOURCE_NOT_FOUND", "Resource not found.")
            if resource.status != ResourceStatus.READY:
                raise AppError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "RESOURCE_NOT_READY",
                    "This resource has not finished processing yet.",
                )
            label = resource.filename or "this document"
            evidence, citations = resolve_resource_evidence(
                db, request.resourceId, max_chunks=settings.VIVA_MAX_EVIDENCE_CHUNKS
            )
            return self._create_session(
                db, workspace, label, evidence, citations, request.resourceId, None, 1.0
            )

        if request.conceptId:
            concept = db.get(Concept, request.conceptId)
            if concept is None or concept.workspace_id != workspace.id:
                raise AppError(status.HTTP_404_NOT_FOUND, "CONCEPT_NOT_FOUND", "Concept not found.")
            evidence, citations = resolve_concept_evidence(
                db, request.conceptId, max_chunks=settings.VIVA_MAX_EVIDENCE_CHUNKS
            )
            return self._create_session(
                db, workspace, concept.name, evidence, citations, None, request.conceptId, 1.0
            )

        question = request.question or ""
        evidence, citations, verdict = resolve_freeform_evidence(
            db, workspace.id, question, top_k=settings.VIVA_MAX_EVIDENCE_CHUNKS
        )
        if not verdict.is_sufficient:
            return IntentResponse(
                intent=IntentType.VIVA,
                status="INSUFFICIENT",
                provenance=None,
                sufficiencyScore=verdict.score,
                retrievalConfidence=verdict.score,
                canOfferExternalFallback=True,
                citations=[],
                result=VivaResult(sessionId="", target=question, isComplete=True, turnNumber=0),
            )
        return self._create_session(db, workspace, question, evidence, citations, None, None, verdict.score)

    def _create_session(
        self,
        db: Session,
        workspace: Workspace,
        label: str,
        evidence: list[EvidenceChunk],
        citations: list[CitationResult],
        resource_id: str | None,
        concept_id: str | None,
        sufficiency_score: float,
    ) -> IntentResponse:
        if not evidence:
            return _insufficient(label)

        draft = get_llm_provider().conduct_viva_turn(label, evidence, [])
        if draft.is_complete or not draft.next_question:
            # Defensive only: a target with real evidence should always
            # produce at least one question -- this only trips if a
            # provider misbehaves.
            return _insufficient(label)

        citation_dicts = _citation_dicts(citations)
        session = VivaSession(
            workspace_id=workspace.id,
            resource_id=resource_id,
            concept_id=concept_id,
            target_label=label,
            status=VivaSessionStatus.IN_PROGRESS,
            turn_count=1,
            max_turns=settings.VIVA_MAX_TURNS,
            transcript_payload=json.dumps(
                {
                    "evidence": [
                        {
                            "order": e.order,
                            "documentFilename": e.document_filename,
                            "pageNumber": e.page_number,
                            "content": e.content,
                        }
                        for e in evidence
                    ],
                    "citations": citation_dicts,
                    "sufficiencyScore": sufficiency_score,
                    "turns": [
                        {
                            "turnNumber": 1,
                            "question": draft.next_question,
                            "rubric": draft.next_question_rubric,
                            "userAnswer": None,
                            "verdict": None,
                            "feedback": None,
                        }
                    ],
                }
            ),
        )
        db.add(session)
        db.flush()

        return IntentResponse(
            intent=IntentType.VIVA,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=sufficiency_score,
            retrievalConfidence=sufficiency_score,
            canOfferExternalFallback=False,
            citations=[CitationOut(**c) for c in citation_dicts],
            result=VivaResult(
                sessionId=session.id,
                target=label,
                isComplete=False,
                turnNumber=1,
                previousEvaluation=None,
                nextQuestion=draft.next_question,
            ),
        )

    def _continue(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        session = db.get(VivaSession, request.sessionId)
        if session is None or session.workspace_id != workspace.id:
            raise AppError(status.HTTP_404_NOT_FOUND, "VIVA_SESSION_NOT_FOUND", "Viva session not found.")
        if session.status == VivaSessionStatus.COMPLETED:
            raise AppError(
                status.HTTP_409_CONFLICT, "VIVA_SESSION_COMPLETE", "This viva session has already finished."
            )

        payload = json.loads(session.transcript_payload)
        evidence = [
            EvidenceChunk(
                order=e["order"],
                document_filename=e["documentFilename"],
                page_number=e["pageNumber"],
                content=e["content"],
            )
            for e in payload["evidence"]
        ]
        sufficiency_score = payload.get("sufficiencyScore", 1.0)
        turns = payload["turns"]
        turns[-1]["userAnswer"] = request.vivaAnswer or ""

        history = [
            VivaTurnRecord(
                turn_number=t["turnNumber"],
                question=t["question"],
                rubric=t["rubric"],
                user_answer=t["userAnswer"],
                verdict=t["verdict"],
                feedback=t["feedback"],
            )
            for t in turns
        ]

        draft = get_llm_provider().conduct_viva_turn(session.target_label, evidence, history)
        turns[-1]["verdict"] = draft.evaluation_verdict
        turns[-1]["feedback"] = draft.evaluation_feedback

        previous_evaluation = None
        if draft.evaluation_verdict:
            previous_evaluation = VivaEvaluationOut(
                verdict=draft.evaluation_verdict, feedback=draft.evaluation_feedback or ""
            )

        already_at_cap = session.turn_count >= session.max_turns
        is_complete = draft.is_complete or already_at_cap or not draft.next_question
        next_question = None
        if not is_complete:
            next_question = draft.next_question
            turns.append(
                {
                    "turnNumber": session.turn_count + 1,
                    "question": draft.next_question,
                    "rubric": draft.next_question_rubric,
                    "userAnswer": None,
                    "verdict": None,
                    "feedback": None,
                }
            )
            session.turn_count += 1

        session.status = VivaSessionStatus.COMPLETED if is_complete else VivaSessionStatus.IN_PROGRESS
        payload["turns"] = turns
        session.transcript_payload = json.dumps(payload)
        if is_complete:
            session.completed_at = datetime.now(timezone.utc)
        db.add(session)
        db.flush()

        return IntentResponse(
            intent=IntentType.VIVA,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=sufficiency_score,
            retrievalConfidence=sufficiency_score,
            canOfferExternalFallback=False,
            citations=[CitationOut(**c) for c in payload["citations"]],
            result=VivaResult(
                sessionId=session.id,
                target=session.target_label,
                isComplete=is_complete,
                turnNumber=session.turn_count,
                previousEvaluation=previous_evaluation,
                nextQuestion=next_question,
            ),
        )
