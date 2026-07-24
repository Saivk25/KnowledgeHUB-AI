"""
Concept graph models (Milestone 7).

Roadmap scope (verbatim): "concepts/resource_concepts/concept_relationships
schema; incremental concept-linking on ingestion; browse-by-concept UI."
DRR Section 11 (Critical) additionally requires a concept
deduplication/entity-resolution strategy and cycle protection on graph
traversal -- both implemented in app/services/concept_graph.py, not here;
this module is schema only. Product Vision v2 Sections 2 and 5 layer two
additive refinements onto this same schema (both classified MVP in Vision
v2 Section 8): the evidence link carries a `contribution_type`, not just a
confidence score, and relationships are typed and (mostly) asymmetric,
not one generic "related" edge.

Three tables, purely additive -- no existing table's columns change:

1. `Concept` -- a first-class knowledge object, one per distinct idea,
   scoped to a workspace (every concept belongs to exactly one workspace,
   the same tenant boundary every other model in this codebase uses).

2. `ResourceConcept` -- the evidence link. A resource contributes evidence
   to a concept; `contribution_type` says *how* (DEFINES/APPLIES/TESTS/
   EXTENDS, or the honest fallback MENTIONS when the linker can't tell),
   and `evidence_chunk_id` points at the specific chunk that supports the
   link. Per the approved design, this column is NOT NULL: a link without
   a pointer to real supporting text is exactly the kind of unfalsifiable
   claim this codebase's confidence discipline (DRR Section 9) exists to
   prevent. See app/services/concept_linking.py for how a real chunk is
   always chosen (never invented).

3. `ConceptRelationship` -- a typed, directed edge between two concepts.
   `RELATED_TO` is the one symmetric type (queried in both directions by
   the traversal helper in app/services/concept_graph.py); every other
   type is directional only. Same evidence-required rule as
   `ResourceConcept`: `evidence_chunk_id` is NOT NULL. Only
   `OpenAIConceptLinker` ever proposes relationships in this milestone --
   the local linker deliberately never invents one (see
   app/services/concept_linking.py's docstring for why), so a
   zero-config deployment has concepts and evidence but no typed edges
   until an API key is configured. That is an honest limitation, not a
   bug: an unearned relationship is worse than no relationship, exactly
   the same principle that keeps LocalHeuristicClassifier from guessing a
   subject in Milestone 6.

Uniqueness: no duplicate evidence/relationship rows is still enforced at
the application layer only (concept_graph.py), matching this codebase's
existing convention (see resource.py's own docstring: cross-field
invariants live in Python, not SQL; `checksum` is indexed but not
DB-unique either, for the same reason).

No two ACTIVE concepts sharing a normalized name in one workspace is
*additionally* backed by a database constraint as of Milestone 12
(migration 0010_concept_dedup_unique_index): a partial unique index on
`(workspace_id, normalized_name)` `WHERE status = 'ACTIVE'`. This is a
deliberate exception to the "no DB UNIQUE constraint" convention stated
above, not a silent reversal of it -- concept_graph.py's `resolve_concept()`
originally relied purely on an application-layer SELECT-then-INSERT
check, which is race-free under any single request but is not atomic
across two concurrent requests. Concurrent `BackgroundTask` ingestion
runs resolving the same concept name (first actually exercised by
Milestone 12's multi-format seed data, see
docs/milestones/MILESTONE_12.md Section 12) could both pass the SELECT
before either committed, producing two ACTIVE concepts with the same
name -- exactly the kind of invariant a database constraint, not more
Python, is required to close. The index only ever rejects a second
concurrent ACTIVE insert; `resolve_concept()` catches that as an
`IntegrityError` and transparently joins the winner's row instead of
failing. MERGED/UNUSED rows are unaffected and may freely share a
normalized_name with each other or with the current ACTIVE row, matching
`resolve_concept()`'s own `status == ACTIVE` filter.

Concept status lifecycle: `ACTIVE` (normal) -> `MERGED` (folded into
another concept via POST /concepts/{id}/merge; the row is preserved, not
deleted, for audit -- `merged_into_concept_id` says where the evidence
went) or -> `UNUSED` (every evidence link it had was removed, e.g. the
last resource that evidenced it was deleted; also preserved, not deleted,
since a `ConceptRelationship` may still reference it). No concept is ever
created without at least one evidence link -- see
concept_graph.resolve_concept() -- and no concept is ever hard-deleted by
this milestone's code; see concept_graph.recompute_concept_usage() for the
orphan-prevention check that assigns UNUSED.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK, TimestampMixin


class ConceptStatus:
    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    UNUSED = "UNUSED"

    ALL = frozenset({ACTIVE, MERGED, UNUSED})


class ContributionType:
    """How a resource's evidence relates to the concept it's linked to.
    MENTIONS is the deliberate honest fallback -- used whenever the linker
    can identify that a resource is evidence for a concept but can't
    confidently say it defines/applies/tests/extends it. Never invented
    beyond what the linker (local or OpenAI) actually determined."""

    DEFINES = "DEFINES"
    APPLIES = "APPLIES"
    TESTS = "TESTS"
    EXTENDS = "EXTENDS"
    MENTIONS = "MENTIONS"

    ALL = frozenset({DEFINES, APPLIES, TESTS, EXTENDS, MENTIONS})


class RelationshipType:
    """Vision v2 Section 5's typed/asymmetric edge set. `recurs_in` from
    that section is deliberately not included here -- Vision v2 itself
    describes it as "not a concept-to-concept edge but a concept's
    frequency signature," i.e. a derived read over ResourceConcept
    timestamps, not a stored relationship row; building that read is a
    Phase 2 discovery feature (Vision v2 Section 8), out of this
    milestone's approved scope."""

    RELATED_TO = "RELATED_TO"
    PREREQUISITE_OF = "PREREQUISITE_OF"
    DEPENDS_ON = "DEPENDS_ON"
    EXTENDS = "EXTENDS"
    APPLIES = "APPLIES"
    CONTRADICTS = "CONTRADICTS"
    REVISES = "REVISES"

    ALL = frozenset({RELATED_TO, PREREQUISITE_OF, DEPENDS_ON, EXTENDS, APPLIES, CONTRADICTS, REVISES})
    # Traversed in both directions by concept_graph.py's shared traversal
    # helper; every other type here is directional only (e.g. "A
    # depends_on B" must never be treated as "B depends_on A").
    SYMMETRIC = frozenset({RELATED_TO})


def normalize_concept_name(name: str) -> str:
    """Lowercase + collapse whitespace, used for the cheap exact-match
    dedup pass before falling back to embedding similarity (DRR Section
    11 / Section 3). A pure function so tests can assert its behavior
    directly without touching the database."""
    return " ".join(name.strip().lower().split())


class Concept(Base, UUIDPK, TimestampMixin):
    __tablename__ = "concepts"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # index=True: every concept-linking run does a workspace-scoped exact
    # lookup here before falling back to embedding similarity.
    normalized_name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ConceptStatus.ACTIVE)

    # Set only when status == MERGED. Self-referential FK; deliberately not
    # given an ORM relationship() (self-referential relationships add
    # remote_side complexity for no benefit here) -- callers that need the
    # target concept just look it up by id, same as any other FK lookup
    # elsewhere in this codebase.
    merged_into_concept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=True
    )

    # Set when entity resolution finds a similarity match in the ambiguous
    # zone (between POSSIBLE_DUPLICATE_THRESHOLD and SIMILARITY_MERGE_THRESHOLD)
    # -- a hint surfaced in the UI for a human to resolve via POST
    # /concepts/{id}/merge, never auto-resolved (DRR Section 11: "a
    # manual-merge escape hatch for anything the automated check misses").
    possible_duplicate_of_concept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=True
    )

    evidence_links = relationship(
        "ResourceConcept",
        back_populates="concept",
        cascade="all, delete-orphan",
        foreign_keys="ResourceConcept.concept_id",
    )


class ResourceConcept(Base, UUIDPK):
    """The evidence link (Vision v2 Section 2): a resource contributes
    evidence to a concept. See this module's docstring for why
    `evidence_chunk_id` is required, not optional."""

    __tablename__ = "resource_concepts"

    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id"), index=True, nullable=False
    )
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id"), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    contribution_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # NOT NULL by explicit approved decision: every evidence link must
    # point at the specific chunk that supports it. See
    # app/services/concept_linking.py for how the local linker always
    # picks a real chunk (highest embedding similarity to the candidate
    # concept among the resource's own chunks), never a placeholder.
    evidence_chunk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_chunks.id"), nullable=False
    )

    resource = relationship("Resource", back_populates="concept_links")
    concept = relationship("Concept", back_populates="evidence_links", foreign_keys=[concept_id])


class ConceptRelationship(Base, UUIDPK):
    """A typed, directed edge between two concepts (Vision v2 Section 5).
    Same evidence-required rule as ResourceConcept -- see this module's
    docstring. Only ever written by OpenAIConceptLinker in this milestone;
    the local linker never proposes relationships (see
    app/services/concept_linking.py)."""

    __tablename__ = "concept_relationships"

    # Denormalized alongside from_concept_id/to_concept_id (both of which
    # already imply a workspace via Concept) so every traversal/list query
    # can filter on workspace_id directly without a join -- the same
    # denormalize-for-query-sanity style already used for
    # VectorPoint.workspace_id in services/vector_repo.py.
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, nullable=False
    )
    from_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), index=True, nullable=False
    )
    to_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), index=True, nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(20), nullable=False)
    strength: Mapped[float | None] = mapped_column(Float, nullable=True)

    # NOT NULL -- see module docstring. Every relationship stored must be
    # traceable to the specific chunk that suggested it.
    evidence_chunk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_chunks.id"), nullable=False
    )
