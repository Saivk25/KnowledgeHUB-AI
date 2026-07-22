"""
Retrieval + citation pipeline.

Milestone 4 scope (dense-only top-k Qdrant search, no reranking, no query
rewriting, no hybrid lexical search -- ADR-0003) stays intact and stays
isolated in this module. Milestone 8 (Local-First Retrieval & Provenance)
extends it, it does not replace it:

1. Hybrid candidates: raw vector-search hits, plus one-hop concept
   expansion (reusing Milestone 7's find_nearby_concepts() -- no recursive
   graph traversal during retrieval; that's traverse_concept_graph(),
   deliberately not used here, per the approved design).
2. Ranking: final_score = vector_similarity + concept_match_boost +
   metadata_match_boost (approved design). ADR-0003's "no BM25, no
   cross-encoder reranker, no learned ranking model" stays in force --
   only this additive formula on top of dense similarity is new.
3. Sufficiency: delegated entirely to app/services/sufficiency.py (DRR
   Section 10 -- a standalone, independently-tested component, never a
   threshold buried in this function; see that module's docstring).
4. Provenance, decided here and nowhere else:
   - LOCAL: sufficient evidence, no external call.
   - HYBRID: sufficient evidence AND the caller explicitly asked to
     supplement with general knowledge. Never a silent blend -- the
     general-knowledge portion is clearly delimited in the answer text.
   - EXTERNAL: insufficient evidence, but either explicit per-request
     confirmation or the workspace's allow_external_fallback setting
     grants consent to answer from general knowledge instead.
   - Insufficient, no call: insufficient evidence and no consent -- the
     honest "I don't know" answer, with can_offer_external_fallback=True
     so the UI can ask the question this module is not allowed to assume
     the answer to.

Chunk-identity reconciliation (the one subtle part of merging the two
candidate sources): a vector-search hit's `SearchResult.point.chunk_id` is
NOT a ResourceChunk.id -- it is the vector point's own generated id,
separately stored on the chunk row as `ResourceChunk.vector_point_id`
(see services/ingestion_service.py, where both are set to the same
generated `point_id`). A concept-expansion candidate's chunk identity
(`ResourceConcept.evidence_chunk_id`) IS a real ResourceChunk.id directly.
To merge/dedupe/boost both sources into one candidate map without
double-counting or missing a boost, every vector hit is resolved to its
real ResourceChunk.id up front (via vector_point_id), and the merged map
is keyed by that real id throughout. Citations are built from the same
resolved ResourceChunk rows regardless of which path found them, so the
answer-generation layer never knows -- and is never told -- whether a
piece of evidence came from vector search or concept expansion, per the
approved design's explicit constraint.

Citation integrity rule (unchanged since Milestone 4): citation
document/page/excerpt values are always read from retrieved chunk
metadata the backend fetched, never from text the LLM generated.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.concept import ResourceConcept
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.services.concept_graph import find_nearby_concepts
from app.services.embeddings import get_embedding_provider
from app.services.llm import EvidenceChunk, get_llm_provider
from app.services.sufficiency import ScoredCandidate, SufficiencyVerdict, compute_sufficiency
from app.services.vector_repo import cosine_similarity, get_vector_repository

settings = get_settings()
logger = logging.getLogger(__name__)

INSUFFICIENT_MESSAGE = "I could not find sufficient evidence in your authorized documents to answer that."
MIN_SCORE_THRESHOLD = 0.05  # ADR-0003: raw-hit floor, unchanged from Milestone 4.

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) > 2}


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
    status: str  # OK | INSUFFICIENT | ERROR
    model_name: str
    retrieval_latency_ms: int
    generation_latency_ms: int
    citations: list[CitationResult]
    # Milestone 8: always populated, never bolted on after the fact
    # (Architecture Section 9 item 4 -- provenance is structurally
    # required, not optional).
    provenance: str | None  # LOCAL | HYBRID | EXTERNAL | None (no answer given)
    # sufficiency_score and retrieval_confidence are deliberately the same
    # number in this implementation (both always set to verdict.score --
    # see answer_question below) -- kept as two named fields, not
    # collapsed into one, because they answer two different questions
    # ("was the sufficiency scorer's verdict correct?" vs. "how much
    # should the user trust this answer?") that happen to share one
    # formula today per the approved design's "single source, do not
    # duplicate confidence calculations elsewhere." A future milestone
    # that layers additional confidence signals on top of sufficiency
    # (e.g. generation-quality signals) would extend retrieval_confidence
    # without touching sufficiency_score's meaning.
    sufficiency_score: float
    retrieval_confidence: float
    sufficiency_reason: str
    can_offer_external_fallback: bool


@dataclass
class _Candidate:
    chunk_id: str  # always a real ResourceChunk.id -- see module docstring
    resource_id: str
    page_number: int
    content: str
    vector_score: float
    from_concept: bool = False
    final_score: float = 0.0


def _resolve_vector_hit_chunks(db: Session, vector_point_ids: set[str]) -> dict[str, ResourceChunk]:
    """Map vector_point_id -> the real ResourceChunk row. See module
    docstring: a vector hit's chunk_id lives in the vector_point_id
    namespace, not ResourceChunk.id."""
    if not vector_point_ids:
        return {}
    rows = db.query(ResourceChunk).filter(ResourceChunk.vector_point_id.in_(vector_point_ids)).all()
    return {row.vector_point_id: row for row in rows}


def _build_candidates(
    db: Session,
    workspace_id: str,
    question: str,
    query_vector: list[float],
    ready_doc_ids: set[str],
) -> dict[str, _Candidate]:
    vector_repo = get_vector_repository()
    raw_hits = vector_repo.search(query_vector, workspace_id=workspace_id, top_k=settings.TOP_K)
    raw_hits = [h for h in raw_hits if h.score >= MIN_SCORE_THRESHOLD]
    raw_hits = [h for h in raw_hits if h.point.document_id in ready_doc_ids]

    chunk_rows_by_point_id = _resolve_vector_hit_chunks(db, {h.point.chunk_id for h in raw_hits})

    candidates: dict[str, _Candidate] = {}
    for h in raw_hits:
        chunk_row = chunk_rows_by_point_id.get(h.point.chunk_id)
        if chunk_row is None:
            # Defensive only: an orphaned vector point (e.g. a chunk row
            # deleted without its vector being cleaned up) must never
            # surface as a citation with no real chunk behind it.
            continue
        candidates[chunk_row.id] = _Candidate(
            chunk_id=chunk_row.id,
            resource_id=h.point.document_id,
            page_number=h.point.page_number,
            content=h.point.content,
            vector_score=h.score,
        )

    # One-hop concept expansion only (approved design: no recursive
    # traversal during retrieval).
    concept_refs = find_nearby_concepts(db, workspace_id, question, top_k=settings.CONCEPT_EXPANSION_TOP_K)
    concept_ids = {c.id for c in concept_refs}
    if not concept_ids:
        return candidates

    links = db.query(ResourceConcept).filter(ResourceConcept.concept_id.in_(concept_ids)).all()
    extra_chunk_ids: set[str] = set()
    for link in links:
        if link.resource_id not in ready_doc_ids:
            continue
        if link.evidence_chunk_id in candidates:
            candidates[link.evidence_chunk_id].from_concept = True
        else:
            extra_chunk_ids.add(link.evidence_chunk_id)

    if extra_chunk_ids:
        extra_rows = db.query(ResourceChunk).filter(ResourceChunk.id.in_(extra_chunk_ids)).all()
        if extra_rows:
            embedder = get_embedding_provider()
            extra_vectors = embedder.embed([row.content for row in extra_rows])
            for row, vec in zip(extra_rows, extra_vectors, strict=False):
                candidates[row.id] = _Candidate(
                    chunk_id=row.id,
                    resource_id=row.resource_id,
                    page_number=row.page_number,
                    content=row.content,
                    vector_score=cosine_similarity(query_vector, vec),
                    from_concept=True,
                )

    return candidates


def _score_candidates(db: Session, question: str, candidates: dict[str, _Candidate]) -> list[ScoredCandidate]:
    """final_score = vector_similarity + concept_match_boost +
    metadata_match_boost (approved design, ADR-0003 additive ranking).
    metadata_match_boost applies when the resource's confirmed subject
    (Milestone 6) shares a token with the question -- a user-confirmed
    signal is trusted more than the classifier's unconfirmed guess.
    Deliberately subject-only: content_category_confirmed is not part of
    this boost -- content_category is a fixed enum label (LECTURE,
    ASSIGNMENT, ...), not a natural-language phrase a question's tokens
    could meaningfully overlap with, unlike a free-text subject."""
    resource_ids = {c.resource_id for c in candidates.values()}
    resources_by_id = {r.id: r for r in db.query(Resource).filter(Resource.id.in_(resource_ids)).all()}
    question_tokens = _tokens(question)

    scored: list[ScoredCandidate] = []
    for cand in candidates.values():
        resource = resources_by_id.get(cand.resource_id)
        metadata_match = bool(
            resource
            and resource.subject_confirmed
            and resource.subject
            and _tokens(resource.subject) & question_tokens
        )
        final_score = cand.vector_score
        if cand.from_concept:
            final_score += settings.CONCEPT_MATCH_BOOST
        if metadata_match:
            final_score += settings.METADATA_MATCH_BOOST
        cand.final_score = final_score
        scored.append(
            ScoredCandidate(chunk_id=cand.chunk_id, resource_id=cand.resource_id, final_score=final_score)
        )
    return scored


def _build_citations_and_evidence(
    db: Session, ordered: list[_Candidate]
) -> tuple[list[EvidenceChunk], list[CitationResult]]:
    """Builds both the LLM-facing evidence list and the response-facing
    citation list from the same resolved candidates -- the generation
    layer receives only document_filename/page_number/content, never
    whether a candidate came from vector search or concept expansion
    (approved design's explicit constraint)."""
    resource_ids = {c.resource_id for c in ordered}
    resources_by_id = {r.id: r for r in db.query(Resource).filter(Resource.id.in_(resource_ids)).all()}

    evidence: list[EvidenceChunk] = []
    citations: list[CitationResult] = []
    for order, cand in enumerate(ordered, start=1):
        resource = resources_by_id.get(cand.resource_id)
        filename = resource.filename if resource else "unknown"
        evidence.append(
            EvidenceChunk(
                order=order, document_filename=filename, page_number=cand.page_number, content=cand.content
            )
        )
        citations.append(
            CitationResult(
                document_id=cand.resource_id,
                document_filename=filename,
                chunk_id=cand.chunk_id,
                page_number=cand.page_number,
                excerpt=cand.content[:500],
                order=order,
            )
        )
    return evidence, citations


def _insufficient_result(
    workspace_id: str,
    verdict: SufficiencyVerdict,
    retrieval_ms: int,
    question: str,
    use_external_fallback: bool,
    allow_external_fallback: bool,
) -> AnswerResult:
    if use_external_fallback or allow_external_fallback:
        t1 = time.monotonic()
        llm = get_llm_provider()
        content = llm.answer_general_knowledge(question)
        generation_ms = int((time.monotonic() - t1) * 1000)
        logger.info(
            "retrieval_answer workspace_id=%s provenance=EXTERNAL sufficiency_score=%.3f reason=%s "
            "citations=0",
            workspace_id,
            verdict.score,
            verdict.reason,
        )
        return AnswerResult(
            content=content,
            status="OK",
            model_name=llm.name,
            retrieval_latency_ms=retrieval_ms,
            generation_latency_ms=generation_ms,
            citations=[],
            provenance="EXTERNAL",
            sufficiency_score=verdict.score,
            retrieval_confidence=verdict.score,
            sufficiency_reason=verdict.reason,
            can_offer_external_fallback=False,
        )

    # DRR Section 16: log the sufficiency score and matched evidence
    # alongside every answer's provenance label -- here, provenance=None
    # (no answer given) with zero matched evidence is itself the signal
    # this log line exists to make visible.
    logger.info(
        "retrieval_answer workspace_id=%s provenance=none sufficiency_score=%.3f reason=%s citations=0",
        workspace_id,
        verdict.score,
        verdict.reason,
    )
    return AnswerResult(
        content=INSUFFICIENT_MESSAGE,
        status="INSUFFICIENT",
        model_name="none",
        retrieval_latency_ms=retrieval_ms,
        generation_latency_ms=0,
        citations=[],
        provenance=None,
        sufficiency_score=verdict.score,
        retrieval_confidence=verdict.score,
        sufficiency_reason=verdict.reason,
        can_offer_external_fallback=True,
    )


def answer_question(
    db: Session,
    workspace_id: str,
    question: str,
    use_external_fallback: bool = False,
    allow_external_fallback: bool = False,
) -> AnswerResult:
    """
    use_external_fallback: explicit, per-request user confirmation (from
    the request body -- see schemas/chat.py's CreateMessageRequest).
    allow_external_fallback: the workspace-level setting
    (Workspace.allow_external_fallback, default False). Per the approved
    design, an external model is never called without one of these two
    consents -- enforced here, in the one place provenance is decided, not
    left to the route.
    """
    t0 = time.monotonic()

    embedder = get_embedding_provider()
    query_vector = embedder.embed_one(question)

    ready_doc_ids = {
        d.id
        for d in db.query(Resource.id)
        .filter(Resource.workspace_id == workspace_id, Resource.status == ResourceStatus.READY)
        .all()
    }

    candidates = _build_candidates(db, workspace_id, question, query_vector, ready_doc_ids)
    retrieval_ms = int((time.monotonic() - t0) * 1000)

    if not candidates:
        verdict = compute_sufficiency([])
        return _insufficient_result(
            workspace_id, verdict, retrieval_ms, question, use_external_fallback, allow_external_fallback
        )

    scored = _score_candidates(db, question, candidates)
    verdict = compute_sufficiency(scored)

    if not verdict.is_sufficient:
        return _insufficient_result(
            workspace_id, verdict, retrieval_ms, question, use_external_fallback, allow_external_fallback
        )

    ordered = sorted(candidates.values(), key=lambda c: c.final_score, reverse=True)[: settings.TOP_K]
    evidence, citations = _build_citations_and_evidence(db, ordered)

    t1 = time.monotonic()
    llm = get_llm_provider()
    local_content = llm.answer(question, evidence)

    if use_external_fallback:
        # HYBRID only ever exists when explicitly requested -- never a
        # silent blend of local evidence and general knowledge.
        general_content = llm.answer_general_knowledge(question)
        content = (
            f"{local_content}\n\n---\n"
            f"Additional context from general knowledge (not sourced from your documents):\n"
            f"{general_content}"
        )
        provenance = "HYBRID"
    else:
        content = local_content
        provenance = "LOCAL"
    generation_ms = int((time.monotonic() - t1) * 1000)

    # DRR Section 16: log the sufficiency score and matched evidence
    # alongside every answer's provenance label.
    logger.info(
        "retrieval_answer workspace_id=%s provenance=%s sufficiency_score=%.3f reason=%s citations=%d",
        workspace_id,
        provenance,
        verdict.score,
        verdict.reason,
        len(citations),
    )

    return AnswerResult(
        content=content,
        status="OK",
        model_name=llm.name,
        retrieval_latency_ms=retrieval_ms,
        generation_latency_ms=generation_ms,
        citations=citations,
        provenance=provenance,
        sufficiency_score=verdict.score,
        retrieval_confidence=verdict.score,
        sufficiency_reason=verdict.reason,
        can_offer_external_fallback=False,
    )
