"""
SummarizeIntent (Milestone 9): three modes based on which request field
is set -- `resourceId` (whole-document summary), `conceptId` (whole-
concept summary across its evidence), or a freeform `question` (the same
hybrid retrieval + real sufficiency gate EXPLAIN uses, since a freeform
"summarize what I know about X" can genuinely have zero local coverage --
FR-10 applies here exactly like it does to Explain). See
docs/milestones/MILESTONE_9.md Section 3.3.
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
from app.schemas.intents import IntentRequest, IntentResponse, IntentType, SummarizeResult
from app.services.intents.base import IntentHandler
from app.services.llm import get_llm_provider
from app.services.retrieval_service import (
    CitationResult,
    resolve_concept_evidence,
    resolve_freeform_evidence,
    resolve_resource_evidence,
)

settings = get_settings()

_NO_EVIDENCE_MESSAGE = "I could not find sufficient evidence in your authorized documents to summarize that."


def _to_citation_out(citations: list[CitationResult]) -> list[CitationOut]:
    return [
        CitationOut(
            documentId=c.document_id,
            documentFilename=c.document_filename,
            chunkId=c.chunk_id,
            pageNumber=c.page_number,
            excerpt=c.excerpt,
            order=c.order,
        )
        for c in citations
    ]


def _insufficient(target: str) -> IntentResponse:
    return IntentResponse(
        intent=IntentType.SUMMARIZE,
        status="INSUFFICIENT",
        provenance=None,
        sufficiencyScore=0.0,
        retrievalConfidence=0.0,
        canOfferExternalFallback=False,
        citations=[],
        result=SummarizeResult(content=_NO_EVIDENCE_MESSAGE, target=target),
    )


class SummarizeIntent(IntentHandler):
    intent_type = IntentType.SUMMARIZE

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        if request.resourceId:
            return self._summarize_resource(db, workspace, request.resourceId)
        if request.conceptId:
            return self._summarize_concept(db, workspace, request.conceptId)
        return self._summarize_freeform(db, workspace, request.question or "")

    def _summarize_resource(self, db: Session, workspace: Workspace, resource_id: str) -> IntentResponse:
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
            db, resource_id, max_chunks=settings.SUMMARIZE_MAX_EVIDENCE_CHUNKS
        )
        # Defensive only: a READY resource always has chunks (Milestone 3
        # guarantee) -- this should never actually trigger.
        if not evidence:
            return _insufficient(label)

        content = get_llm_provider().summarize(label, evidence)
        return IntentResponse(
            intent=IntentType.SUMMARIZE,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=1.0,
            retrievalConfidence=1.0,
            canOfferExternalFallback=False,
            citations=_to_citation_out(citations),
            result=SummarizeResult(content=content, target=label),
        )

    def _summarize_concept(self, db: Session, workspace: Workspace, concept_id: str) -> IntentResponse:
        concept = db.get(Concept, concept_id)
        if concept is None or concept.workspace_id != workspace.id:
            raise AppError(status.HTTP_404_NOT_FOUND, "CONCEPT_NOT_FOUND", "Concept not found.")

        evidence, citations = resolve_concept_evidence(
            db, concept_id, max_chunks=settings.SUMMARIZE_MAX_EVIDENCE_CHUNKS
        )
        # Defensive only: a concept is never created without at least one
        # evidence link (concept_graph.resolve_concept()'s invariant) --
        # this only trips for an edge case like a MERGED/UNUSED concept
        # reached via a stale client reference.
        if not evidence:
            return _insufficient(concept.name)

        content = get_llm_provider().summarize(concept.name, evidence)
        return IntentResponse(
            intent=IntentType.SUMMARIZE,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=1.0,
            retrievalConfidence=1.0,
            canOfferExternalFallback=False,
            citations=_to_citation_out(citations),
            result=SummarizeResult(content=content, target=concept.name),
        )

    def _summarize_freeform(self, db: Session, workspace: Workspace, question: str) -> IntentResponse:
        evidence, citations, verdict = resolve_freeform_evidence(db, workspace.id, question)
        if not verdict.is_sufficient:
            return IntentResponse(
                intent=IntentType.SUMMARIZE,
                status="INSUFFICIENT",
                provenance=None,
                sufficiencyScore=verdict.score,
                retrievalConfidence=verdict.score,
                canOfferExternalFallback=True,
                citations=[],
                result=SummarizeResult(content=_NO_EVIDENCE_MESSAGE, target=question),
            )

        content = get_llm_provider().summarize(question, evidence)
        return IntentResponse(
            intent=IntentType.SUMMARIZE,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=verdict.score,
            retrievalConfidence=verdict.score,
            canOfferExternalFallback=False,
            citations=_to_citation_out(citations),
            result=SummarizeResult(content=content, target=question),
        )
