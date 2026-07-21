"""
Milestone 7 -- concept deduplication / entity-resolution tests (DRR Section
11, critical). Exercises resolve_concept() directly against the real
LocalHashEmbeddingProvider (no mocks -- lexical similarity is a genuine,
if simple, signal, same discipline as every other test in this codebase)
and the manual-merge escape hatch.

Isolation note: each test uses its own `registered_client`, which creates
a brand-new workspace. `resolve_concept`'s ANN search is scoped to
`workspace_id`, so different tests never see each other's concept vectors
even though the concept-vector InMemoryVectorRepository is a
process-wide, module-cached singleton -- the exact same isolation
precedent test_ingestion.py already documents for chunk vectors.
"""

import pytest

from app.models.concept import Concept, ConceptStatus
from app.services import concept_graph


def _workspace_id(client) -> str:
    return client.get("/api/v1/workspace").json()["workspace"]["id"]


def test_exact_name_match_reuses_existing_concept_regardless_of_case(registered_client):
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = _workspace_id(client)

    db = SessionLocal()
    try:
        first = concept_graph.resolve_concept(db, workspace_id, "Gradient Descent")
        db.commit()
        assert first.created is True
        assert first.flagged_possible_duplicate is False

        second = concept_graph.resolve_concept(db, workspace_id, "gradient descent")
        db.commit()
        assert second.created is False
        assert second.concept.id == first.concept.id
    finally:
        db.close()


def test_lexically_identical_phrasing_merges_via_similarity_not_exact_match(registered_client):
    """The DRR's named example: two names that are not string-identical
    (so the cheap exact-normalized-name path deliberately misses them) but
    share the exact same real-word vocabulary resolve to one concept via
    the embedding-similarity path instead."""
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = _workspace_id(client)

    db = SessionLocal()
    try:
        first = concept_graph.resolve_concept(db, workspace_id, "Gradient Descent")
        db.commit()

        # Punctuation makes normalize_concept_name() produce a different
        # string ("gradient, descent!" != "gradient descent"), so the
        # exact-match path genuinely does not catch this -- only the ANN
        # similarity search does, since the underlying tokens are identical.
        second = concept_graph.resolve_concept(db, workspace_id, "Gradient, Descent!")
        db.commit()

        assert second.created is False
        assert second.flagged_possible_duplicate is False
        assert second.concept.id == first.concept.id
    finally:
        db.close()


def test_related_but_distinct_phrasing_is_flagged_as_possible_duplicate(registered_client):
    """Between the two thresholds: a new concept is still created (never
    silently merged), but flagged for manual review."""
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = _workspace_id(client)

    db = SessionLocal()
    try:
        first = concept_graph.resolve_concept(db, workspace_id, "Gradient Descent")
        db.commit()

        second = concept_graph.resolve_concept(db, workspace_id, "Gradient Descent Algorithm")
        db.commit()

        assert second.created is True
        assert second.concept.id != first.concept.id
        assert second.flagged_possible_duplicate is True
        assert second.concept.possible_duplicate_of_concept_id == first.concept.id
    finally:
        db.close()


def test_unrelated_name_creates_a_new_unflagged_concept(registered_client):
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = _workspace_id(client)

    db = SessionLocal()
    try:
        first = concept_graph.resolve_concept(db, workspace_id, "Gradient Descent")
        db.commit()

        second = concept_graph.resolve_concept(db, workspace_id, "Static Site Generators")
        db.commit()

        assert second.created is True
        assert second.concept.id != first.concept.id
        assert second.flagged_possible_duplicate is False
        assert second.concept.possible_duplicate_of_concept_id is None
    finally:
        db.close()


def test_two_different_workspaces_never_share_a_concept(registered_client):
    """Every concept belongs to exactly one workspace (approved-design
    constraint) -- the same name in a second workspace must never resolve
    to the first workspace's concept."""
    from fastapi.testclient import TestClient

    from app.db.session import SessionLocal
    from app.main import app

    first_client, _ = registered_client
    first_workspace_id = _workspace_id(first_client)

    other = TestClient(app)
    resp = other.post(
        "/api/v1/auth/register",
        json={"email": "other-dedup@test.com", "password": "password123", "displayName": "Other"},
    )
    assert resp.status_code == 201, resp.text
    second_workspace_id = other.get("/api/v1/workspace").json()["workspace"]["id"]
    assert second_workspace_id != first_workspace_id

    db = SessionLocal()
    try:
        first = concept_graph.resolve_concept(db, first_workspace_id, "Gradient Descent")
        db.commit()

        second = concept_graph.resolve_concept(db, second_workspace_id, "Gradient Descent")
        db.commit()

        assert second.created is True
        assert second.concept.id != first.concept.id
        assert second.concept.workspace_id == second_workspace_id
    finally:
        db.close()


def test_manual_merge_repoints_evidence_and_marks_source_merged(registered_client, tmp_path):
    """Uses two lexically unrelated names (not "Concept A" / "Concept B" --
    LocalHashEmbeddingProvider's tokenizer drops single-character tokens via
    its `len(t) > 1` filter, so "Concept A" and "Concept B" both reduce to
    the single token "concept" and resolve_concept correctly treats them as
    the same concept, which defeats this test's premise of merging two
    genuinely distinct concepts. Real bug caught by the local-first
    verification loop -- see MILESTONE_7.md.)"""
    from app.db.session import SessionLocal
    from app.models.concept import ResourceConcept
    from app.models.resource import ResourceChunk

    client, _ = registered_client
    workspace_id = _workspace_id(client)

    path = tmp_path / "x.txt"
    path.write_text("some content used only to produce a real evidence chunk")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("x.txt", f, "text/plain")})
    resource_id = resp.json()["id"]

    db = SessionLocal()
    try:
        chunk = db.query(ResourceChunk).filter(ResourceChunk.resource_id == resource_id).first()
        source = concept_graph.resolve_concept(db, workspace_id, "Merge Source Concept").concept
        target = concept_graph.resolve_concept(db, workspace_id, "Unrelated Target Subject").concept
        db.add(
            ResourceConcept(
                resource_id=resource_id,
                concept_id=source.id,
                confidence=0.9,
                contribution_type="MENTIONS",
                evidence_chunk_id=chunk.id,
            )
        )
        db.commit()

        merged_target = concept_graph.merge_concepts(db, workspace_id, source.id, target.id)
        db.commit()

        assert merged_target.id == target.id

        refreshed_source = db.get(Concept, source.id)
        assert refreshed_source.status == ConceptStatus.MERGED
        assert refreshed_source.merged_into_concept_id == target.id

        assert db.query(ResourceConcept).filter(ResourceConcept.concept_id == source.id).count() == 0
        assert db.query(ResourceConcept).filter(ResourceConcept.concept_id == target.id).count() == 1
    finally:
        db.close()


def test_merge_into_self_is_rejected(registered_client):
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = _workspace_id(client)

    db = SessionLocal()
    try:
        concept = concept_graph.resolve_concept(db, workspace_id, "Solo Concept").concept
        db.commit()

        with pytest.raises(concept_graph.ConceptMergeError):
            concept_graph.merge_concepts(db, workspace_id, concept.id, concept.id)
    finally:
        db.close()


def test_merge_across_workspaces_is_rejected(registered_client):
    from fastapi.testclient import TestClient

    from app.db.session import SessionLocal
    from app.main import app

    first_client, _ = registered_client
    first_workspace_id = _workspace_id(first_client)

    other = TestClient(app)
    other.post(
        "/api/v1/auth/register",
        json={"email": "other-merge@test.com", "password": "password123", "displayName": "Other"},
    )
    second_workspace_id = other.get("/api/v1/workspace").json()["workspace"]["id"]

    db = SessionLocal()
    try:
        a = concept_graph.resolve_concept(db, first_workspace_id, "Workspace A Concept").concept
        b = concept_graph.resolve_concept(db, second_workspace_id, "Workspace B Concept").concept
        db.commit()

        with pytest.raises(concept_graph.ConceptMergeError):
            concept_graph.merge_concepts(db, first_workspace_id, a.id, b.id)
    finally:
        db.close()
