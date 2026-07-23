"""
SearchIntent (Milestone 9): pure ranked retrieval by default -- no
sufficiency gate blocks results from being returned, and no LLM call
happens unless the top result's confidence is low. See
docs/milestones/MILESTONE_9.md Section 3.3 and Section 4 decision 3 (your
explicit direction, not the original recommendation of "never call an
LLM") for the full rationale of the confidence-triggered synthesis below.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.workspace import Workspace
from app.schemas.chat import CitationOut
from app.schemas.intents import IntentRequest, IntentResponse, IntentType, SearchResult
from app.services.intents.base import IntentHandler
from app.services.llm import get_llm_provider
from app.services.retrieval_service import resolve_citations_and_evidence, resolve_question_candidates
from app.services.sufficiency import compute_sufficiency

settings = get_settings()


class SearchIntent(IntentHandler):
    intent_type = IntentType.SEARCH

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        question = request.question or ""
        candidates, scored = resolve_question_candidates(db, workspace.id, question)

        if not candidates:
            verdict = compute_sufficiency([])
            return IntentResponse(
                intent=IntentType.SEARCH,
                status="INSUFFICIENT",
                provenance=None,
                sufficiencyScore=verdict.score,
                retrievalConfidence=verdict.score,
                canOfferExternalFallback=False,
                citations=[],
                result=SearchResult(hits=[], assistedSynthesis=None),
            )

        verdict = compute_sufficiency(scored)
        ordered = sorted(candidates.values(), key=lambda c: c.final_score, reverse=True)
        ordered = ordered[: settings.SEARCH_TOP_K]
        evidence, citation_results = resolve_citations_and_evidence(db, ordered)

        hits = [
            CitationOut(
                documentId=c.document_id,
                documentFilename=c.document_filename,
                chunkId=c.chunk_id,
                pageNumber=c.page_number,
                excerpt=c.excerpt,
                order=c.order,
            )
            for c in citation_results
        ]

        assisted_synthesis: str | None = None
        # Approved design (MILESTONE_9.md Section 4 decision 3): below
        # threshold, additionally call the LLM for a grounded synthesis on
        # top of the ranked hits above -- never instead of them, and never
        # calling the LLM at all when the match is already confident. The
        # synthesis can only draw on `evidence` (what Search's own
        # retrieval already surfaced), so FR-10 holds and provenance stays
        # LOCAL in both branches.
        if verdict.score < settings.SEARCH_LLM_CONFIDENCE_THRESHOLD:
            llm = get_llm_provider()
            assisted_synthesis = (
                "Low-confidence match -- here is a best-effort synthesis grounded "
                "only in the ranked results below:\n\n" + llm.answer(question, evidence)
            )

        return IntentResponse(
            intent=IntentType.SEARCH,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=verdict.score,
            retrievalConfidence=verdict.score,
            canOfferExternalFallback=False,
            citations=hits,
            result=SearchResult(hits=hits, assistedSynthesis=assisted_synthesis),
        )
