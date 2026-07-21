from pydantic import BaseModel


class ConceptOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str
    evidenceCount: int
    possibleDuplicateOfConceptId: str | None = None
    createdAt: str


class ConceptListOut(BaseModel):
    items: list[ConceptOut]


class EvidenceOut(BaseModel):
    resourceId: str
    filename: str
    contributionType: str
    confidence: float
    evidenceChunkId: str
    excerpt: str


class RelatedConceptOut(BaseModel):
    conceptId: str
    name: str
    relationshipType: str
    depth: int


class ConceptDetailOut(BaseModel):
    concept: ConceptOut
    evidence: list[EvidenceOut]
    related: list[RelatedConceptOut]


class ConceptMergeRequest(BaseModel):
    """POST /concepts/{id}/merge body. One-way for this milestone (approved
    design): the source concept (the one in the URL) is folded into
    `intoConceptId` and marked MERGED, not deleted or later restorable."""

    intoConceptId: str
