"""
Concept graph routes (Milestone 7).

Mirrors app/api/v1/routes/documents.py's exact conventions: `AppError`,
workspace-scoped 404s (a concept belonging to another workspace is
indistinguishable from one that doesn't exist, same as every other
workspace-scoped lookup in this API), `Depends(get_current_workspace)` on
every route. Scope, per the approved design: list, detail (evidence +
one-hop related concepts -- the "browse by concept" page's data source),
a `related` endpoint for deeper traversal (server-side depth-capped
regardless of what's requested -- see
app/services/concept_graph.py's `traverse_concept_graph`), and the
manual-merge escape hatch. No concept-creation route: concepts are only
ever created by the ingestion pipeline's concept-linking stage (see
app/services/ingestion_service.py), never directly via this API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AppError, get_current_workspace
from app.models.concept import Concept, ConceptStatus, ResourceConcept
from app.models.resource import Resource, ResourceChunk
from app.models.workspace import Workspace
from app.schemas.concept import (
    ConceptDetailOut,
    ConceptListOut,
    ConceptMergeRequest,
    ConceptOut,
    EvidenceOut,
    RelatedConceptOut,
)
from app.services.concept_graph import ConceptMergeError, merge_concepts, traverse_concept_graph

router = APIRouter(prefix="/concepts", tags=["concepts"])

_EXCERPT_CHARS = 240


def _to_out(concept: Concept, evidence_count: int) -> ConceptOut:
    return ConceptOut(
        id=concept.id,
        name=concept.name,
        description=concept.description,
        status=concept.status,
        evidenceCount=evidence_count,
        possibleDuplicateOfConceptId=concept.possible_duplicate_of_concept_id,
        createdAt=concept.created_at.isoformat() if concept.created_at else "",
    )


def _related_out(db: Session, hits) -> list[RelatedConceptOut]:
    related: list[RelatedConceptOut] = []
    for hit in hits:
        neighbor = db.get(Concept, hit.concept_id)
        if neighbor is None:
            continue
        related.append(
            RelatedConceptOut(
                conceptId=neighbor.id,
                name=neighbor.name,
                relationshipType=hit.relationship_type,
                depth=hit.depth,
            )
        )
    return related


@router.get(
    "",
    response_model=ConceptListOut,
    summary="List concepts in the current workspace",
    description="Only ACTIVE concepts, most-evidenced first. Merged and unused concepts are excluded.",
)
def list_concepts(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    concepts = (
        db.query(Concept)
        .filter(Concept.workspace_id == workspace.id, Concept.status == ConceptStatus.ACTIVE)
        .order_by(Concept.created_at.desc())
        .all()
    )
    items = []
    for concept in concepts:
        count = db.query(ResourceConcept).filter(ResourceConcept.concept_id == concept.id).count()
        items.append(_to_out(concept, count))
    items.sort(key=lambda c: c.evidenceCount, reverse=True)
    return ConceptListOut(items=items)


@router.get(
    "/{concept_id}",
    response_model=ConceptDetailOut,
    summary="Get a concept's evidence and one-hop related concepts",
    description=(
        "Returns 404 CONCEPT_NOT_FOUND if the concept doesn't exist or "
        "belongs to a different workspace. `related` is one hop only -- "
        "use GET /concepts/{id}/related for deeper (still depth-capped) traversal."
    ),
)
def get_concept(
    concept_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_current_workspace),
):
    concept = db.get(Concept, concept_id)
    if not concept or concept.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "CONCEPT_NOT_FOUND", "Concept not found.")

    links = db.query(ResourceConcept).filter(ResourceConcept.concept_id == concept_id).all()
    evidence: list[EvidenceOut] = []
    for link in links:
        resource = db.get(Resource, link.resource_id)
        if resource is None:
            continue
        chunk = db.get(ResourceChunk, link.evidence_chunk_id)
        evidence.append(
            EvidenceOut(
                resourceId=resource.id,
                filename=resource.filename or "",
                contributionType=link.contribution_type,
                confidence=link.confidence,
                evidenceChunkId=link.evidence_chunk_id,
                excerpt=(chunk.content[:_EXCERPT_CHARS] if chunk else ""),
            )
        )

    hits = traverse_concept_graph(db, concept_id, workspace.id, max_depth=1)
    return ConceptDetailOut(
        concept=_to_out(concept, len(links)), evidence=evidence, related=_related_out(db, hits)
    )


@router.get(
    "/{concept_id}/related",
    response_model=list[RelatedConceptOut],
    summary="Traverse related concepts",
    description=(
        "Neighbor traversal via the shared, cycle-safe traversal helper "
        "(app/services/concept_graph.py). `depth` is capped server-side at "
        "MAX_TRAVERSAL_DEPTH regardless of what is requested."
    ),
)
def get_related_concepts(
    concept_id: str,
    depth: int = 1,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_current_workspace),
):
    concept = db.get(Concept, concept_id)
    if not concept or concept.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "CONCEPT_NOT_FOUND", "Concept not found.")

    hits = traverse_concept_graph(db, concept_id, workspace.id, max_depth=depth)
    return _related_out(db, hits)


@router.post(
    "/{concept_id}/merge",
    response_model=ConceptOut,
    summary="Merge a concept into another (manual-merge escape hatch)",
    description=(
        "One-way for this milestone: the concept in the URL is folded into "
        "`intoConceptId` -- its evidence and relationships are re-pointed, "
        "and it is marked MERGED (preserved, not deleted, for audit). "
        "422 MERGE_FAILED if either concept doesn't exist in this "
        "workspace, they are the same concept, or the source is already merged."
    ),
)
def merge_concept_route(
    concept_id: str,
    body: ConceptMergeRequest,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_current_workspace),
):
    concept = db.get(Concept, concept_id)
    if not concept or concept.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "CONCEPT_NOT_FOUND", "Concept not found.")

    try:
        target = merge_concepts(db, workspace.id, concept_id, body.intoConceptId)
    except ConceptMergeError as exc:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "MERGE_FAILED", str(exc)) from exc

    db.commit()
    count = db.query(ResourceConcept).filter(ResourceConcept.concept_id == target.id).count()
    return _to_out(target, count)
