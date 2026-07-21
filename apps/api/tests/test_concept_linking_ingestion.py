"""
Milestone 7 -- end-to-end concept-linking tests through the real ingestion
pipeline: filename-fallback concept creation (since the default
LocalHeuristicClassifier never sets `subject` -- see
concept_linking.py's docstring), deduplication across two separate
uploads, graceful degradation on linker failure, the orphan-prevention
rule after a resource is deleted, and that the local linker never
fabricates a relationship.
"""

from app.models.concept import Concept, ConceptRelationship, ConceptStatus, ResourceConcept

ASSIGNMENT_TEXT = "Assignment 2\nSubmit by Friday. This homework covers the due date policy."


def test_ingestion_creates_concept_via_filename_fallback(registered_client, tmp_path):
    """The default zero-config path (LocalHeuristicClassifier +
    LocalConceptLinker, no OPENAI_API_KEY) still produces a real concept
    link, via the filename fallback -- proving the zero-config golden
    path isn't inert for this milestone."""
    client, _ = registered_client
    path = tmp_path / "hw2_special.txt"
    path.write_text(ASSIGNMENT_TEXT)
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("hw2_special.txt", f, "text/plain")})
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["id"]

    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["document"]["status"] == "READY"
    concepts = detail["concepts"]
    assert len(concepts) == 1
    assert concepts[0]["name"] == "Hw2 Special"
    assert concepts[0]["confidence"] == 0.3
    # ASSIGNMENT -> APPLIES, per CATEGORY_TO_CONTRIBUTION (Vision v2 Section 2's own example).
    assert concepts[0]["contributionType"] == "APPLIES"


def test_two_uploads_with_equivalent_filenames_dedup_to_one_concept(registered_client, tmp_path):
    client, _ = registered_client

    path_a = tmp_path / "gradient_descent.txt"
    path_a.write_text("Some notes.")
    with open(path_a, "rb") as f:
        resp_a = client.post("/api/v1/documents", files={"file": ("gradient_descent.txt", f, "text/plain")})
    assert resp_a.status_code == 201, resp_a.text

    path_b = tmp_path / "Gradient-Descent.txt"
    path_b.write_text("Some different notes, different content entirely.")
    with open(path_b, "rb") as f:
        resp_b = client.post("/api/v1/documents", files={"file": ("Gradient-Descent.txt", f, "text/plain")})
    assert resp_b.status_code == 201, resp_b.text

    concepts_a = client.get(f"/api/v1/documents/{resp_a.json()['id']}").json()["concepts"]
    concepts_b = client.get(f"/api/v1/documents/{resp_b.json()['id']}").json()["concepts"]
    assert len(concepts_a) == 1
    assert len(concepts_b) == 1
    # Both filenames fold to the same fallback name ("Gradient Descent"),
    # so they must resolve to the exact same concept, not two duplicates.
    assert concepts_a[0]["conceptId"] == concepts_b[0]["conceptId"]

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        count = (
            db.query(Concept)
            .filter(Concept.normalized_name == "gradient descent", Concept.status == ConceptStatus.ACTIVE)
            .count()
        )
        assert count == 1
    finally:
        db.close()


def test_concept_linking_failure_degrades_gracefully_without_failing_resource(
    registered_client, tmp_path, monkeypatch
):
    import app.services.ingestion_service as ingestion_module

    def _broken_get_concept_linker():
        raise RuntimeError("simulated concept linker outage")

    monkeypatch.setattr(ingestion_module, "get_concept_linker", _broken_get_concept_linker)

    client, _ = registered_client
    path = tmp_path / "plain.txt"
    path.write_text("Some plain content for ingestion.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("plain.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["document"]["status"] == "READY"  # never fails solely due to concept-linking
    assert detail["concepts"] == []


def test_deleting_a_resource_marks_its_only_concept_unused(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "lonely_concept.txt"
    path.write_text(ASSIGNMENT_TEXT)
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("lonely_concept.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    concepts = client.get(f"/api/v1/documents/{document_id}").json()["concepts"]
    assert len(concepts) == 1
    concept_id = concepts[0]["conceptId"]

    delete_resp = client.delete(f"/api/v1/documents/{document_id}")
    assert delete_resp.status_code == 204

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        concept = db.get(Concept, concept_id)
        assert concept is not None  # preserved, not hard-deleted
        assert concept.status == ConceptStatus.UNUSED
        assert db.query(ResourceConcept).filter(ResourceConcept.concept_id == concept_id).count() == 0
    finally:
        db.close()


def test_local_linker_never_creates_a_relationship(registered_client, tmp_path):
    """Approved-design restraint: with no grounding step and no NLP, the
    local linker must never propose a relationship (see
    concept_linking.py's docstring) -- verified end to end, not just at
    the unit level, since this is a product-visible honesty guarantee."""
    client, _ = registered_client
    path = tmp_path / "hw3.txt"
    path.write_text(ASSIGNMENT_TEXT)
    with open(path, "rb") as f:
        client.post("/api/v1/documents", files={"file": ("hw3.txt", f, "text/plain")})

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        assert db.query(ConceptRelationship).count() == 0
    finally:
        db.close()
