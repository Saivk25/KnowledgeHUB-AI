"""
ExplainIntent (Milestone 9): the one intent that predates this milestone
-- a thin wrapper around app/services/retrieval_service.py's
answer_question(), unchanged in behavior since Milestone 8. This handler
exists so EXPLAIN is dispatched through the same registry as every other
intent, rather than special-cased in the route. `POST /conversations/
{id}/messages` (Milestone 8's existing endpoint) is itself now a thin
wrapper that constructs an IntentRequest(intent="EXPLAIN", ...) and calls
this same handler -- see app/api/v1/routes/chat.py.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.workspace import Workspace
from app.schemas.chat import CitationOut
from app.schemas.intents import ExplainResult, IntentRequest, IntentResponse, IntentType
from app.services.intents.base import IntentHandler
from app.services.retrieval_service import answer_question


class ExplainIntent(IntentHandler):
    intent_type = IntentType.EXPLAIN

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        result = answer_question(
            db,
            workspace_id=workspace.id,
            question=request.question or "",
            use_external_fallback=request.useExternalFallback,
            allow_external_fallback=workspace.allow_external_fallback,
        )
        citations = [
            CitationOut(
                documentId=c.document_id,
                documentFilename=c.document_filename,
                chunkId=c.chunk_id,
                pageNumber=c.page_number,
                excerpt=c.excerpt,
                order=c.order,
            )
            for c in result.citations
        ]
        return IntentResponse(
            intent=IntentType.EXPLAIN,
            status=result.status,
            provenance=result.provenance,
            sufficiencyScore=result.sufficiency_score,
            retrievalConfidence=result.retrieval_confidence,
            canOfferExternalFallback=result.can_offer_external_fallback,
            citations=citations,
            result=ExplainResult(content=result.content),
        )
