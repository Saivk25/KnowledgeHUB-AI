"""
Milestone 7 -- graph traversal safeguards (DRR Section 11, critical): cycle
protection via an explicit visited-node set, plus an independent max-depth
bound. Exercises traverse_concept_graph() directly against manually
constructed ConceptRelationship rows, including a real cycle, proving it
terminates correctly rather than infinite-looping.
"""

from app.models.concept import Concept, ConceptRelationship, RelationshipType
from app.models.resource import ResourceChunk
from app.services.concept_graph import traverse_concept_graph


def _make_concept(db, workspace_id, name):
    concept = Concept(workspace_id=workspace_id, name=name, normalized_name=name.lower())
    db.add(concept)
    db.flush()
    return concept


def _make_relationship(db, workspace_id, from_concept, to_concept, rel_type, evidence_chunk_id):
    rel = ConceptRelationship(
        workspace_id=workspace_id,
        from_concept_id=from_concept.id,
        to_concept_id=to_concept.id,
        relationship_type=rel_type,
        strength=0.8,
        evidence_chunk_id=evidence_chunk_id,
    )
    db.add(rel)
    db.flush()
    return rel


def _real_chunk_id(client, tmp_path, db):
    path = tmp_path / "evidence.txt"
    path.write_text("some content used only to produce a real evidence chunk")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("evidence.txt", f, "text/plain")})
    resource_id = resp.json()["id"]
    chunk = db.query(ResourceChunk).filter(ResourceChunk.resource_id == resource_id).first()
    assert chunk is not None
    return chunk.id


def test_cyclic_relationship_terminates_and_returns_the_real_neighbor_only(registered_client, tmp_path):
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    db = SessionLocal()
    try:
        chunk_id = _real_chunk_id(client, tmp_path, db)
        a = _make_concept(db, workspace_id, "A")
        b = _make_concept(db, workspace_id, "B")
        _make_relationship(db, workspace_id, a, b, RelationshipType.DEPENDS_ON, chunk_id)
        _make_relationship(db, workspace_id, b, a, RelationshipType.DEPENDS_ON, chunk_id)  # the cycle
        db.commit()

        # The actual assertion is that this call returns at all (rather
        # than hanging or raising a recursion error) -- a real regression
        # here would time the test suite out, not just fail an assert.
        hits = traverse_concept_graph(db, a.id, workspace_id, max_depth=10)

        assert {h.concept_id for h in hits} == {b.id}
    finally:
        db.close()


def test_non_cyclic_chain_returns_correct_multihop_neighbors_at_correct_depth(registered_client, tmp_path):
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    db = SessionLocal()
    try:
        chunk_id = _real_chunk_id(client, tmp_path, db)
        a = _make_concept(db, workspace_id, "A")
        b = _make_concept(db, workspace_id, "B")
        c = _make_concept(db, workspace_id, "C")
        _make_relationship(db, workspace_id, a, b, RelationshipType.RELATED_TO, chunk_id)
        _make_relationship(db, workspace_id, b, c, RelationshipType.EXTENDS, chunk_id)
        db.commit()

        hits = traverse_concept_graph(db, a.id, workspace_id, max_depth=5)
        by_id = {h.concept_id: h for h in hits}

        assert by_id[b.id].depth == 1
        assert by_id[c.id].depth == 2
    finally:
        db.close()


def test_requested_depth_beyond_max_traversal_depth_is_capped(registered_client, tmp_path):
    """A long chain of 6 hops, requested at a huge depth, must still stop
    at the server-side MAX_TRAVERSAL_DEPTH (5) -- the belt-and-suspenders
    guard independent of the visited-node set."""
    from app.core.config import get_settings
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]
    settings = get_settings()

    db = SessionLocal()
    try:
        chunk_id = _real_chunk_id(client, tmp_path, db)
        concepts = [_make_concept(db, workspace_id, f"C{i}") for i in range(7)]  # C0..C6, 6 edges
        for i in range(6):
            _make_relationship(
                db, workspace_id, concepts[i], concepts[i + 1], RelationshipType.RELATED_TO, chunk_id
            )
        db.commit()

        hits = traverse_concept_graph(db, concepts[0].id, workspace_id, max_depth=1000)
        reached_depths = {h.depth for h in hits}

        assert max(reached_depths) <= settings.MAX_TRAVERSAL_DEPTH
        # C6 is 6 hops away -- strictly beyond the 5-hop cap -- so it must
        # never be reached, proving the cap actually bites.
        assert concepts[6].id not in {h.concept_id for h in hits}
        assert concepts[5].id in {h.concept_id for h in hits}
    finally:
        db.close()


def test_requested_depth_smaller_than_max_is_honored(registered_client, tmp_path):
    from app.db.session import SessionLocal

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    db = SessionLocal()
    try:
        chunk_id = _real_chunk_id(client, tmp_path, db)
        a = _make_concept(db, workspace_id, "A")
        b = _make_concept(db, workspace_id, "B")
        c = _make_concept(db, workspace_id, "C")
        _make_relationship(db, workspace_id, a, b, RelationshipType.RELATED_TO, chunk_id)
        _make_relationship(db, workspace_id, b, c, RelationshipType.RELATED_TO, chunk_id)
        db.commit()

        hits = traverse_concept_graph(db, a.id, workspace_id, max_depth=1)

        assert {h.concept_id for h in hits} == {b.id}
    finally:
        db.close()
