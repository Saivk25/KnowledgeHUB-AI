"""
Retrieval + citation pipeline.

Decision: dense-only retrieval (top-k Qdrant similarity search filtered by
workspace_id), no reranking, no query rewriting, no hybrid lexical search.
Why over hybrid/rerank/agentic pipelines: each adds real value at scale, but
also a real chance to break the two-day build. A small workspace corpus does
not need them to produce trustworthy citations (see ADR-0003). The retrieval
interface is isolated in this module specifically so reranking or hybrid
search can be inserted later without touching the chat route or UI.

Citation integrity rule: citation document/page/excerpt values are always
read from the retrieved chunk metadata that the backend fetched, never from
text the LLM generated. This prevents the model from inventing a page number
or a document that was not actually retrieved.

Milestone 4 update: this module is still dormant (not imported by anything
mounted -- see app/README.md), but its import of the renamed Document model
was updated to Resource so it does not raise ModuleNotFoundError the moment
a future milestone activates it. Field/variable names below (document_id,
document_filename, etc.) are left as-is; renaming them is a cosmetic choice
for whichever milestone actually builds RAG chat, not part of this
milestone's approved scope.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.services.embeddings import get_embedding_provider
from app.services.llm import EvidenceChunk, get_llm_provider
from app.services.vector_repo import get_vector_repository

settings = get_settings()

NO_EVIDENCE_MESSAGE = "I could not find sufficient evidence in your authorized documents to answer that."
MIN_SCORE_THRESHOLD = 0.05


@dataclass
class CitationResult:
    document_id: str
    document_filename: str
    chunk_id: str
    page_number: int
    excerpt: str
    order: int


@dataclass
class AnswerResult:
    content: str
    status: str  # OK | NO_EVIDENCE
    model_name: str
    retrieval_latency_ms: int
    generation_latency_ms: int
    citations: list[CitationResult]


def answer_question(db: Session, workspace_id: str, question: str) -> AnswerResult:
    t0 = time.monotonic()

    embedder = get_embedding_provider()
    query_vector = embedder.embed_one(question)

    vector_repo = get_vector_repository()
    hits = vector_repo.search(query_vector, workspace_id=workspace_id, top_k=settings.TOP_K)
    hits = [h for h in hits if h.score >= MIN_SCORE_THRESHOLD]

    retrieval_ms = int((time.monotonic() - t0) * 1000)

    ready_doc_ids = {
        d.id
        for d in db.query(Resource.id)
        .filter(Resource.workspace_id == workspace_id, Resource.status == ResourceStatus.READY)
        .all()
    }
    hits = [h for h in hits if h.point.document_id in ready_doc_ids]

    if not hits:
        return AnswerResult(
            content=NO_EVIDENCE_MESSAGE,
            status="NO_EVIDENCE",
            model_name="none",
            retrieval_latency_ms=retrieval_ms,
            generation_latency_ms=0,
            citations=[],
        )

    documents_by_id = {
        d.id: d for d in db.query(Resource).filter(Resource.id.in_({h.point.document_id for h in hits})).all()
    }

    evidence: list[EvidenceChunk] = []
    for order, hit in enumerate(hits, start=1):
        doc = documents_by_id.get(hit.point.document_id)
        evidence.append(
            EvidenceChunk(
                order=order,
                document_filename=doc.filename if doc else "unknown",
                page_number=hit.point.page_number,
                content=hit.point.content,
            )
        )

    t1 = time.monotonic()
    llm = get_llm_provider()
    content = llm.answer(question, evidence)
    generation_ms = int((time.monotonic() - t1) * 1000)

    citations: list[CitationResult] = []
    for e, hit in zip(evidence, hits, strict=False):
        chunk_row = (
            db.query(ResourceChunk).filter(ResourceChunk.vector_point_id == hit.point.chunk_id).first()
        )
        citations.append(
            CitationResult(
                document_id=hit.point.document_id,
                document_filename=e.document_filename,
                chunk_id=chunk_row.id if chunk_row else hit.point.chunk_id,
                page_number=hit.point.page_number,
                excerpt=hit.point.content[:500],
                order=e.order,
            )
        )

    return AnswerResult(
        content=content,
        status="OK",
        model_name=llm.name,
        retrieval_latency_ms=retrieval_ms,
        generation_latency_ms=generation_ms,
        citations=citations,
    )
