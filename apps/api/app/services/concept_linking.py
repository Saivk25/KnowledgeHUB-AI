"""
Concept linker provider adapter (Milestone 7).

Same shape as Classifier (services/classification.py) and EmbeddingProvider
(services/embeddings.py): a narrow ABC, a dependency-free local default,
an OpenAI-backed opt-in implementation, and a get_X()/reset_X_cache() pair.

Scope, matching the approved design exactly:

1. **One concept proposal per resource per linking run.** M6 already
   distills a resource down to one `subject` string; this milestone reuses
   that field as the candidate concept name rather than attempting
   multi-concept extraction, which was never part of the approved scope.
   `LinkingResult.concept` is singular, not a list.

2. **LocalConceptLinker (default, zero-config).** The candidate name is
   the resource's already-classified `subject` (Milestone 6) -- no new
   NLP dependency, per the approved design ("do not introduce spaCy, NER
   models, or additional NLP dependencies"). If `subject` is None (the
   classifier had no signal), this linker proposes nothing; concept
   linking is enrichment, not a prerequisite, so ingestion_service.py logs
   and continues exactly as it already does for a classifier failure.
   `contribution_type` is derived from the resource's already-classified
   `content_category` via a small, documented, deterministic mapping
   (CATEGORY_TO_CONTRIBUTION) that operationalizes Vision v2 Section 2's
   own examples verbatim ("a lecture PDF *defines* ... an assignment
   *applies* it ... an MCQ set *tests* it ... a research paper *extends*
   it") -- a real, already-computed signal, never invented. `confidence`
   is the resource's real `subject_confidence` (M6), not a new number.
   The evidence chunk is chosen by real embedding similarity between the
   candidate name and each of the resource's own chunks (argmax), using
   whichever EmbeddingProvider is already configured -- never a
   placeholder.

   **Zero-config fallback:** `LocalHeuristicClassifier` (Milestone 6)
   deliberately never guesses a `subject` -- it honestly leaves it `None`
   when there's no real signal (see that classifier's own docstring).
   Without a fallback, a fully zero-config deployment (both
   `CLASSIFICATION_PROVIDER` and `CONCEPT_LINKER_PROVIDER` left at
   `local`, the actual defaults) would therefore never create a single
   concept -- contradicting this codebase's established "zero-config
   golden path" precedent (`LocalHashEmbeddingProvider`,
   `LocalHeuristicClassifier` itself). So when `subject` is `None`, this
   linker falls back to a name derived from the resource's own filename
   (strip the extension, replace separators with spaces, title-case) --
   plain string manipulation, not NLP, and a real if weak signal (the
   file's own name), reflected honestly via a flat, low, documented
   confidence (`_FILENAME_FALLBACK_CONFIDENCE`), never dressed up as a
   strong classification.

   **This linker never proposes relationships** -- with no
   grounding step and no NLP, there is no honest signal for "concept A
   relates to concept B" locally; guessing one would be exactly the kind
   of manufactured-trust confidence badge this codebase's discipline
   (DRR Section 9) exists to avoid. This is the same restraint
   `LocalHeuristicClassifier` already applies to subject-guessing in
   Milestone 6.

3. **OpenAIConceptLinker (opt-in).** Retrieval-grounded per Architecture
   Section 9 item 5: given the resource's text, its own chunks (id +
   excerpt), and a list of *already-existing* nearby concepts (id, name,
   description -- found via a coarse embedding search run by the caller
   before this is invoked), the model may propose linking to one of those
   existing concepts directly (by id) or a new concept name, plus
   `contribution_type`/confidence, and 0+ relationships to concepts drawn
   *only* from the provided nearby-concepts list. Every evidence_chunk_id
   and every relationship's target concept_id is validated against what
   was actually provided -- a hallucinated id is dropped, never trusted.
"""

from __future__ import annotations

import json
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings
from app.models.resource import ResourceContentCategory

settings = get_settings()


@dataclass
class ChunkRef:
    id: str
    content: str


@dataclass
class ExistingConceptRef:
    id: str
    name: str
    description: str | None = None


@dataclass
class ConceptLinkProposal:
    """Either `concept_id` (linking to an already-existing concept the
    linker was shown) or `name` (a candidate for a new/matched concept,
    resolved via app/services/concept_graph.py's dedup pipeline) is set --
    never both. `evidence_chunk_id` must be one of the ids the linker was
    given."""

    contribution_type: str
    confidence: float
    evidence_chunk_id: str
    concept_id: str | None = None
    name: str | None = None
    description: str | None = None


@dataclass
class RelationshipProposal:
    to_concept_id: str
    relationship_type: str
    strength: float
    evidence_chunk_id: str


@dataclass
class LinkingResult:
    concept: ConceptLinkProposal | None = None
    relationships: list[RelationshipProposal] = field(default_factory=list)


class ConceptLinker(ABC):
    @abstractmethod
    def propose(
        self,
        subject: str | None,
        subject_confidence: float | None,
        content_category: str | None,
        filename: str,
        chunks: list[ChunkRef],
        nearby_concepts: list[ExistingConceptRef],
    ) -> LinkingResult: ...


def fallback_concept_name_from_filename(filename: str) -> str | None:
    """Plain string manipulation, not NLP: strip the extension, replace
    `_`/`-` separators with spaces, title-case. See LocalConceptLinker's
    docstring for why this fallback exists."""
    stem = re.sub(r"\.[^.]+$", "", filename or "").strip()
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    return stem.title() if stem else None


# A flat, honest, low confidence for the filename fallback -- deliberately
# below what any real subject/content-category signal would score, and a
# named constant rather than invented per-resource (same discipline as
# classification.py's _NO_SIGNAL_CONFIDENCE).
_FILENAME_FALLBACK_CONFIDENCE = 0.3


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


# Vision v2 Section 2's own examples, made deterministic. OTHER and
# PERSONAL_NOTE map to MENTIONS -- the honest fallback -- because neither
# category implies a specific contribution to a concept the way a lecture,
# assignment, question paper, or research paper does.
CATEGORY_TO_CONTRIBUTION: dict[str, str] = {
    ResourceContentCategory.LECTURE: "DEFINES",
    ResourceContentCategory.ASSIGNMENT: "APPLIES",
    ResourceContentCategory.QUESTION_PAPER: "TESTS",
    ResourceContentCategory.LAB_MANUAL: "APPLIES",
    ResourceContentCategory.RESEARCH_PAPER: "EXTENDS",
    ResourceContentCategory.PERSONAL_NOTE: "MENTIONS",
    ResourceContentCategory.OTHER: "MENTIONS",
}
_DEFAULT_CONTRIBUTION = "MENTIONS"


class LocalConceptLinker(ConceptLinker):
    def propose(
        self,
        subject: str | None,
        subject_confidence: float | None,
        content_category: str | None,
        filename: str,
        chunks: list[ChunkRef],
        nearby_concepts: list[ExistingConceptRef],
    ) -> LinkingResult:
        if not chunks:
            return LinkingResult(concept=None, relationships=[])

        if subject and subject.strip():
            candidate_name = subject.strip()
            confidence = subject_confidence if subject_confidence is not None else 0.5
        else:
            candidate_name = fallback_concept_name_from_filename(filename)
            confidence = _FILENAME_FALLBACK_CONFIDENCE
            if candidate_name is None:
                return LinkingResult(concept=None, relationships=[])

        from app.services.embeddings import get_embedding_provider

        embedder = get_embedding_provider()
        candidate_vector = embedder.embed_one(candidate_name)
        chunk_vectors = embedder.embed([c.content for c in chunks])
        similarities = [_cosine(candidate_vector, v) for v in chunk_vectors]
        best_index = max(range(len(chunks)), key=lambda i: similarities[i])

        contribution_type = CATEGORY_TO_CONTRIBUTION.get(content_category or "", _DEFAULT_CONTRIBUTION)

        proposal = ConceptLinkProposal(
            name=candidate_name,
            description=None,
            contribution_type=contribution_type,
            confidence=confidence,
            evidence_chunk_id=chunks[best_index].id,
        )
        # Deliberately no relationships -- see this module's docstring.
        return LinkingResult(concept=proposal, relationships=[])


_LINKING_PROMPT = (
    "You are linking one document into an existing knowledge graph of "
    "concepts. Respond with ONLY a JSON object of this exact shape:\n"
    '{{"concept": {{"conceptId": "<an id from existingConcepts, or null>", '
    '"name": "<required if conceptId is null, else null>", '
    '"description": "<short description, or null>", '
    '"contributionType": "<one of: DEFINES, APPLIES, TESTS, EXTENDS, MENTIONS>", '
    '"confidence": <0-1 float>, "evidenceChunkId": "<an id from chunks>"}} or null, '
    '"relationships": [{{"toConceptId": "<an id from existingConcepts>", '
    '"relationshipType": "<one of: RELATED_TO, PREREQUISITE_OF, DEPENDS_ON, EXTENDS, APPLIES, '
    'CONTRADICTS, REVISES>", "strength": <0-1 float>, "evidenceChunkId": "<an id from chunks>"}}]}}\n\n'
    "Only ever use ids that literally appear in existingConcepts or chunks below -- never invent one. "
    'If nothing in this document clearly evidences a concept, set "concept" to null.\n\n'
    "DOCUMENT SUBJECT (if known): {subject}\n"
    "EXISTING CONCEPTS: {existing_concepts}\n"
    "CHUNKS: {chunks}"
)

_MAX_PROMPT_CHUNKS = 20
_MAX_CHUNK_CHARS = 500


class OpenAIConceptLinker(ConceptLinker):
    def __init__(self):
        self._client = httpx.Client(
            base_url=settings.OPENAI_BASE_URL,
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            timeout=30.0,
        )

    def propose(
        self,
        subject: str | None,
        subject_confidence: float | None,
        content_category: str | None,
        filename: str,
        chunks: list[ChunkRef],
        nearby_concepts: list[ExistingConceptRef],
    ) -> LinkingResult:
        if not chunks:
            return LinkingResult(concept=None, relationships=[])

        limited_chunks = chunks[:_MAX_PROMPT_CHUNKS]
        valid_chunk_ids = {c.id for c in limited_chunks}
        valid_concept_ids = {c.id for c in nearby_concepts}

        prompt = _LINKING_PROMPT.format(
            subject=subject or f"unknown (filename: {filename})",
            existing_concepts=json.dumps(
                [{"id": c.id, "name": c.name, "description": c.description} for c in nearby_concepts]
            ),
            chunks=json.dumps(
                [{"id": c.id, "excerpt": c.content[:_MAX_CHUNK_CHARS]} for c in limited_chunks]
            ),
        )
        response = self._client.post(
            "/chat/completions",
            json={
                "model": settings.OPENAI_CHAT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        data = json.loads(content)

        concept_data = data.get("concept")
        proposal: ConceptLinkProposal | None = None
        if concept_data:
            evidence_chunk_id = concept_data.get("evidenceChunkId")
            if evidence_chunk_id in valid_chunk_ids:
                concept_id = concept_data.get("conceptId")
                if concept_id is not None and concept_id not in valid_concept_ids:
                    concept_id = None
                contribution_type = concept_data.get("contributionType")
                if contribution_type not in {"DEFINES", "APPLIES", "TESTS", "EXTENDS", "MENTIONS"}:
                    contribution_type = _DEFAULT_CONTRIBUTION
                name = concept_data.get("name")
                if concept_id is None and not name:
                    proposal = None  # neither a valid existing id nor a name -- drop, never guess
                else:
                    proposal = ConceptLinkProposal(
                        concept_id=concept_id,
                        name=name,
                        description=concept_data.get("description") or None,
                        contribution_type=contribution_type,
                        confidence=float(concept_data.get("confidence") or 0.0),
                        evidence_chunk_id=evidence_chunk_id,
                    )
            # else: model didn't cite a real chunk -- drop the proposal entirely,
            # never trust an evidence pointer that wasn't actually offered.

        relationships: list[RelationshipProposal] = []
        for rel in data.get("relationships") or []:
            to_id = rel.get("toConceptId")
            evidence_chunk_id = rel.get("evidenceChunkId")
            rel_type = rel.get("relationshipType")
            if to_id not in valid_concept_ids or evidence_chunk_id not in valid_chunk_ids:
                continue  # hallucinated id -- drop, never trust
            valid_types = {
                "RELATED_TO",
                "PREREQUISITE_OF",
                "DEPENDS_ON",
                "EXTENDS",
                "APPLIES",
                "CONTRADICTS",
                "REVISES",
            }
            if rel_type not in valid_types:
                continue
            relationships.append(
                RelationshipProposal(
                    to_concept_id=to_id,
                    relationship_type=rel_type,
                    strength=float(rel.get("strength") or 0.0),
                    evidence_chunk_id=evidence_chunk_id,
                )
            )

        return LinkingResult(concept=proposal, relationships=relationships)


_linker: ConceptLinker | None = None


def get_concept_linker() -> ConceptLinker:
    global _linker
    if _linker is not None:
        return _linker
    if settings.CONCEPT_LINKER_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        _linker = OpenAIConceptLinker()
    else:
        _linker = LocalConceptLinker()
    return _linker


def reset_concept_linker_cache() -> None:
    """Used by tests to force re-evaluation after changing settings."""
    global _linker
    _linker = None
