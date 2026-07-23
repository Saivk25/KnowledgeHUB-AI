"""
FlashcardsIntent (Milestone 10): the same three-mode resolution
(resource-target, concept-target, freeform question) Summarize already
established, generating front/back card pairs instead of prose. No new
persistence -- unlike Quiz/Viva, a flashcard's "back" is meant to be seen
immediately, so there is no answer key to hide between turns (see
docs/milestones/MILESTONE_10.md Section 3.4).
"""

from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.deps import AppError
from app.models.concept import Concept
from app.models.resource import Resource, ResourceStatus
from app.models.workspace import Workspace
from app.schemas.chat import CitationOut
from app.schemas.intents import FlashcardOut, FlashcardsResult, IntentRequest, IntentResponse, IntentType
from app.services.intents.base import IntentHandler
from app.services.llm import EvidenceChunk, get_llm_provider
from app.services.retrieval_service import (
    CitationResult,
    resolve_concept_evidence,
    resolve_freeform_evidence,
    resolve_resource_evidence,
)

settings = get_settings()


def _citation_lookup(citations: list[CitationResult]) -> dict[int, CitationOut]:
    return {
        c.order: CitationOut(
            documentId=c.document_id,
            documentFilename=c.document_filename,
            chunkId=c.chunk_id,
            pageNumber=c.page_number,
            excerpt=c.excerpt,
            order=c.order,
        )
        for c in citations
    }


def _insufficient(target: str) -> IntentResponse:
    return IntentResponse(
        intent=IntentType.FLASHCARDS,
        status="INSUFFICIENT",
        provenance=None,
        sufficiencyScore=0.0,
        retrievalConfidence=0.0,
        canOfferExternalFallback=False,
        citations=[],
        result=FlashcardsResult(target=target, cards=[]),
    )


class FlashcardsIntent(IntentHandler):
    intent_type = IntentType.FLASHCARDS

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        count = min(request.questionCount or settings.FLASHCARDS_COUNT_DEFAULT, settings.FLASHCARDS_MAX_COUNT)
        if request.resourceId:
            return self._from_resource(db, workspace, request.resourceId, count)
        if request.conceptId:
            return self._from_concept(db, workspace, request.conceptId, count)
        return self._from_freeform(db, workspace, request.question or "", count)

    def _from_resource(
        self, db: Session, workspace: Workspace, resource_id: str, count: int
    ) -> IntentResponse:
        resource = db.get(Resource, resource_id)
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
            db, resource_id, max_chunks=settings.FLASHCARDS_MAX_COUNT
        )
        if not evidence:
            return _insufficient(label)
        return self._build(label, evidence, citations, count, 1.0)

    def _from_concept(self, db: Session, workspace: Workspace, concept_id: str, count: int) -> IntentResponse:
        concept = db.get(Concept, concept_id)
        if concept is None or concept.workspace_id != workspace.id:
            raise AppError(status.HTTP_404_NOT_FOUND, "CONCEPT_NOT_FOUND", "Concept not found.")
        evidence, citations = resolve_concept_evidence(
            db, concept_id, max_chunks=settings.FLASHCARDS_MAX_COUNT
        )
        if not evidence:
            return _insufficient(concept.name)
        return self._build(concept.name, evidence, citations, count, 1.0)

    def _from_freeform(self, db: Session, workspace: Workspace, question: str, count: int) -> IntentResponse:
        evidence, citations, verdict = resolve_freeform_evidence(
            db, workspace.id, question, top_k=settings.FLASHCARDS_MAX_COUNT
        )
        if not verdict.is_sufficient:
            return IntentResponse(
                intent=IntentType.FLASHCARDS,
                status="INSUFFICIENT",
                provenance=None,
                sufficiencyScore=verdict.score,
                retrievalConfidence=verdict.score,
                canOfferExternalFallback=True,
                citations=[],
                result=FlashcardsResult(target=question, cards=[]),
            )
        return self._build(question, evidence, citations, count, verdict.score)

    def _build(
        self,
        label: str,
        evidence: list[EvidenceChunk],
        citations: list[CitationResult],
        count: int,
        sufficiency_score: float,
    ) -> IntentResponse:
        citation_lookup = _citation_lookup(citations)
        drafts = get_llm_provider().generate_flashcards(label, evidence, count)
        cards = [
            FlashcardOut(front=d.front, back=d.back, citation=citation_lookup[d.citation_order])
            for d in drafts
            if d.citation_order in citation_lookup
        ]
        return IntentResponse(
            intent=IntentType.FLASHCARDS,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=sufficiency_score,
            retrievalConfidence=sufficiency_score,
            canOfferExternalFallback=False,
            citations=list(citation_lookup.values()),
            result=FlashcardsResult(target=label, cards=cards),
        )
