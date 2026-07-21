"""
Concept graph management (Milestone 7): entity resolution/deduplication,
manual merge, orphan-prevention, and the one shared safe-traversal helper.

DRR Section 11 (Critical) requires two things this module exists to
satisfy, both centralized here rather than spread across call sites:

1. **Deduplication / entity resolution** (`resolve_concept`) -- a
   three-zone check (exact normalized-name match, then an ANN search
   against this workspace's concept-vector collection) so "Gradient
   Descent" and "Gradient descent algorithm" resolve to one Concept
   instead of two. DRR Section 3 requires this to be an ANN lookup
   reusing the existing vector store, not an O(existing-concept-count)
   table scan -- see services/vector_repo.py's
   get_concept_vector_repository().

2. **Cycle-safe graph traversal** (`traverse_concept_graph`) -- the one
   function every current and future recursive concept-graph query in
   this codebase must go through, never a bespoke query per call site.
   Implemented as an application-level breadth-first walk with an
   explicit visited-node set (the actual cycle-safety mechanism) plus a
   hard `MAX_TRAVERSAL_DEPTH` bound as a second, independent guard --
   deliberately not a raw recursive SQL CTE: at the personal-archive
   scale this product targets (DRR Section 3), a handful of indexed
   queries per hop is exactly the "simplest necessary technology" this
   codebase already favors elsewhere (Architecture Section 9), and an
   application-level walk is far easier to unit-test the cycle/depth
   guarantees against directly (see tests/test_concept_graph_traversal.py)
   than a hand-written recursive CTE would be.

Also implements the manual-merge escape hatch (DRR: "a manual-merge
escape hatch for anything the automated check misses") and the
orphan-prevention rule from the approved design: a concept is never left
without at least one evidence link -- see `recompute_concept_usage`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.concept import (
    Concept,
    ConceptRelationship,
    ConceptStatus,
    ResourceConcept,
    normalize_concept_name,
)
from app.services.embeddings import get_embedding_provider
from app.services.vector_repo import VectorPoint, get_concept_vector_repository, new_point_id

settings = get_settings()


@dataclass
class ConceptResolution:
    concept: Concept
    created: bool
    flagged_possible_duplicate: bool


def _concept_text(name: str, description: str | None) -> str:
    return f"{name}\n{description or ''}".strip()


def resolve_concept(
    db: Session, workspace_id: str, name: str, description: str | None = None
) -> ConceptResolution:
    """DRR Section 11's dedup/entity-resolution strategy, three zones:

    1. Exact normalized-name match within the workspace, among ACTIVE
       concepts (cheap, indexed) -- catches same-name-different-casing
       duplicates outright.
    2. Otherwise, an ANN search against this workspace's concept vectors.
       Above `SIMILARITY_MERGE_THRESHOLD`: treat as the same concept --
       link evidence to it, create nothing new.
    3. Between that and `POSSIBLE_DUPLICATE_THRESHOLD`: create a new
       concept but set `possible_duplicate_of_concept_id` so the UI can
       surface a manual-merge suggestion. Never silently merged.
    4. Below both: create a genuinely new concept and index its vector.
    """
    normalized = normalize_concept_name(name)

    exact = (
        db.query(Concept)
        .filter(
            Concept.workspace_id == workspace_id,
            Concept.normalized_name == normalized,
            Concept.status == ConceptStatus.ACTIVE,
        )
        .first()
    )
    if exact:
        return ConceptResolution(concept=exact, created=False, flagged_possible_duplicate=False)

    embedder = get_embedding_provider()
    candidate_vector = embedder.embed_one(_concept_text(name, description))
    concept_repo = get_concept_vector_repository()
    hits = concept_repo.search(candidate_vector, workspace_id=workspace_id, top_k=5)
    best = hits[0] if hits else None

    if best is not None and best.score >= settings.SIMILARITY_MERGE_THRESHOLD:
        matched = db.get(Concept, best.point.concept_id) if best.point.concept_id else None
        if matched is not None and matched.status == ConceptStatus.ACTIVE:
            return ConceptResolution(concept=matched, created=False, flagged_possible_duplicate=False)

    possible_duplicate_of: str | None = None
    if best is not None and best.score >= settings.POSSIBLE_DUPLICATE_THRESHOLD:
        matched = db.get(Concept, best.point.concept_id) if best.point.concept_id else None
        if matched is not None and matched.status == ConceptStatus.ACTIVE:
            possible_duplicate_of = matched.id

    concept = Concept(
        workspace_id=workspace_id,
        name=name,
        normalized_name=normalized,
        description=description,
        status=ConceptStatus.ACTIVE,
        possible_duplicate_of_concept_id=possible_duplicate_of,
    )
    db.add(concept)
    db.flush()  # need concept.id before indexing its vector

    concept_repo.upsert(
        [
            VectorPoint(
                id=new_point_id(),
                vector=candidate_vector,
                workspace_id=workspace_id,
                concept_id=concept.id,
                content=_concept_text(name, description),
            )
        ]
    )

    return ConceptResolution(
        concept=concept, created=True, flagged_possible_duplicate=possible_duplicate_of is not None
    )


def find_nearby_concepts(db: Session, workspace_id: str, query_text: str, top_k: int = 5):
    """Coarse grounding context for OpenAIConceptLinker (Architecture
    Section 9 item 5: "retrieval-grounded prompts"). Not the authoritative
    dedup check -- that's `resolve_concept`, run separately once the
    linker has proposed a specific candidate name."""
    from app.services.concept_linking import ExistingConceptRef

    if not query_text or not query_text.strip():
        return []

    embedder = get_embedding_provider()
    vector = embedder.embed_one(query_text)
    hits = get_concept_vector_repository().search(vector, workspace_id=workspace_id, top_k=top_k)

    refs: list[ExistingConceptRef] = []
    for hit in hits:
        if not hit.point.concept_id:
            continue
        concept = db.get(Concept, hit.point.concept_id)
        if concept is not None and concept.status == ConceptStatus.ACTIVE:
            refs.append(ExistingConceptRef(id=concept.id, name=concept.name, description=concept.description))
    return refs


def recompute_concept_usage(db: Session, concept_ids: set[str]) -> None:
    """Orphan-prevention (approved design constraint): a concept must
    always have at least one evidence link. Called after anything that
    can remove a concept's evidence -- a resource being deleted, or a
    resource's concept-links being replaced on ingestion retry. If a
    concept's evidence count reaches zero, it is marked `UNUSED` (never
    hard-deleted, since a ConceptRelationship may still reference it, and
    never re-marked if it is already `MERGED` -- that status already says
    where its evidence went, more specifically than `UNUSED` would).
    Reactivates a concept back to `ACTIVE` if evidence returns (e.g. a
    retry re-links it) after having gone `UNUSED`.
    """
    for concept_id in concept_ids:
        concept = db.get(Concept, concept_id)
        if concept is None or concept.status == ConceptStatus.MERGED:
            continue
        remaining = db.query(ResourceConcept).filter(ResourceConcept.concept_id == concept_id).count()
        if remaining == 0 and concept.status != ConceptStatus.UNUSED:
            concept.status = ConceptStatus.UNUSED
        elif remaining > 0 and concept.status == ConceptStatus.UNUSED:
            concept.status = ConceptStatus.ACTIVE
    db.flush()


class ConceptMergeError(Exception):
    pass


def merge_concepts(db: Session, workspace_id: str, source_id: str, target_id: str) -> Concept:
    """The manual-merge escape hatch (DRR: "a manual-merge escape hatch
    for anything the automated check misses"). One-way for this milestone
    (approved design): the source concept is preserved with
    status=MERGED and merged_into_concept_id set, not deleted or
    restorable -- undo-merge is deferred to a future milestone."""
    if source_id == target_id:
        raise ConceptMergeError("Cannot merge a concept into itself.")

    source = db.get(Concept, source_id)
    target = db.get(Concept, target_id)
    if source is None or source.workspace_id != workspace_id:
        raise ConceptMergeError("Source concept not found.")
    if target is None or target.workspace_id != workspace_id:
        raise ConceptMergeError("Target concept not found.")
    if source.status == ConceptStatus.MERGED:
        raise ConceptMergeError("Source concept is already merged.")

    db.query(ResourceConcept).filter(ResourceConcept.concept_id == source_id).update(
        {"concept_id": target_id}, synchronize_session=False
    )
    db.query(ConceptRelationship).filter(ConceptRelationship.from_concept_id == source_id).update(
        {"from_concept_id": target_id}, synchronize_session=False
    )
    db.query(ConceptRelationship).filter(ConceptRelationship.to_concept_id == source_id).update(
        {"to_concept_id": target_id}, synchronize_session=False
    )
    db.flush()

    # Re-pointing both ends above can produce a self-loop (source used to
    # relate to target, or vice versa) -- drop those, a concept relating
    # to itself is meaningless.
    db.query(ConceptRelationship).filter(
        ConceptRelationship.from_concept_id == target_id,
        ConceptRelationship.to_concept_id == target_id,
    ).delete(synchronize_session=False)

    source.status = ConceptStatus.MERGED
    source.merged_into_concept_id = target_id
    db.flush()

    get_concept_vector_repository().delete_by_concept(source_id)

    return target


@dataclass
class TraversalHit:
    concept_id: str
    relationship_type: str
    depth: int


def traverse_concept_graph(
    db: Session, start_concept_id: str, workspace_id: str, max_depth: int | None = None
) -> list[TraversalHit]:
    """The one shared, cycle-safe graph-traversal helper (DRR Section 11).
    Every current and future recursive traversal must go through this
    function. Cycle safety comes from the explicit `visited` set (a
    concept, once reached, is never re-added to the frontier or re-scored
    at a deeper depth); `depth_limit` is a second, independent guard
    regardless of what a caller requests, so a runaway or densely
    connected graph still terminates in bounded work."""
    depth_limit = min(max_depth or settings.MAX_TRAVERSAL_DEPTH, settings.MAX_TRAVERSAL_DEPTH)

    visited: set[str] = {start_concept_id}
    frontier: set[str] = {start_concept_id}
    hits: dict[str, TraversalHit] = {}

    current_depth = 0
    while frontier and current_depth < depth_limit:
        current_depth += 1
        rows = (
            db.query(ConceptRelationship)
            .filter(
                ConceptRelationship.workspace_id == workspace_id,
                (ConceptRelationship.from_concept_id.in_(frontier))
                | (ConceptRelationship.to_concept_id.in_(frontier)),
            )
            .all()
        )
        next_frontier: set[str] = set()
        for row in rows:
            for candidate, touches_frontier in (
                (row.to_concept_id, row.from_concept_id in frontier),
                (row.from_concept_id, row.to_concept_id in frontier),
            ):
                if not touches_frontier or candidate in visited:
                    continue
                visited.add(candidate)
                next_frontier.add(candidate)
                hits[candidate] = TraversalHit(
                    concept_id=candidate, relationship_type=row.relationship_type, depth=current_depth
                )
        frontier = next_frontier

    return sorted(hits.values(), key=lambda h: h.depth)
