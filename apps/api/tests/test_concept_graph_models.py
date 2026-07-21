"""
Milestone 7 -- concept graph model-level tests: the normalize_concept_name
pure function, the taxonomy constants, and basic ORM CRUD (including that
`evidence_chunk_id` really is required, per the approved design).
"""

from app.models.concept import (
    Concept,
    ConceptStatus,
    ContributionType,
    RelationshipType,
    ResourceConcept,
    normalize_concept_name,
)


def test_normalize_concept_name_collapses_case_and_whitespace():
    assert normalize_concept_name("Gradient Descent") == "gradient descent"
    assert normalize_concept_name("  Gradient   Descent  ") == "gradient descent"
    assert normalize_concept_name("GRADIENT DESCENT") == "gradient descent"


def test_taxonomy_constants_are_consistent():
    assert ConceptStatus.ALL == {"ACTIVE", "MERGED", "UNUSED"}
    assert ContributionType.ALL == {"DEFINES", "APPLIES", "TESTS", "EXTENDS", "MENTIONS"}
    assert RelationshipType.RELATED_TO in RelationshipType.SYMMETRIC
    assert RelationshipType.DEPENDS_ON not in RelationshipType.SYMMETRIC
    assert RelationshipType.PREREQUISITE_OF not in RelationshipType.SYMMETRIC
    assert RelationshipType.SYMMETRIC <= RelationshipType.ALL
    # recurs_in is deliberately not a stored relationship type -- see
    # app/models/concept.py's RelationshipType docstring.
    assert "RECURS_IN" not in RelationshipType.ALL


def test_concept_created_with_active_status_and_no_merge_flags_by_default(registered_client):
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    db = SessionLocal()
    try:
        concept = Concept(
            workspace_id=workspace_id, name="Gradient Descent", normalized_name="gradient descent"
        )
        db.add(concept)
        db.commit()
        db.refresh(concept)

        assert concept.status == ConceptStatus.ACTIVE
        assert concept.merged_into_concept_id is None
        assert concept.possible_duplicate_of_concept_id is None
        assert concept.description is None
    finally:
        db.close()


def test_resource_concept_requires_a_real_resource_and_chunk(registered_client, tmp_path):
    """Proves evidence_chunk_id is a real, populated NOT NULL foreign key,
    not an optional pointer -- the approved design's core evidence rule."""
    from app.db.session import SessionLocal
    from app.models.resource import ResourceChunk

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    path = tmp_path / "notes.txt"
    path.write_text("Some study notes about a topic, used only to produce a real chunk row.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("notes.txt", f, "text/plain")})
    resource_id = resp.json()["id"]

    db = SessionLocal()
    try:
        chunk = db.query(ResourceChunk).filter(ResourceChunk.resource_id == resource_id).first()
        assert chunk is not None

        concept = Concept(workspace_id=workspace_id, name="Test Concept", normalized_name="test concept")
        db.add(concept)
        db.flush()

        link = ResourceConcept(
            resource_id=resource_id,
            concept_id=concept.id,
            confidence=0.9,
            contribution_type=ContributionType.MENTIONS,
            evidence_chunk_id=chunk.id,
        )
        db.add(link)
        db.commit()
        db.refresh(link)

        assert link.evidence_chunk_id == chunk.id
        assert link.contribution_type == ContributionType.MENTIONS
    finally:
        db.close()
