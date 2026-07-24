"""
Milestone 12, Section 12 addendum: concurrency regression test for the
concept-resolution race discovered during Item 4 (screenshot capture) --
see docs/milestones/MILESTONE_12.md Section 12 for the full discovery.

fastapi.testclient.TestClient cannot reproduce this race on its own: it
executes BackgroundTasks synchronously/serially, so two ingestion runs
are never actually in-flight at once (this is exactly why the bug went
unnoticed through every prior milestone's test suite). This module
therefore drives resolve_concept() directly from two real threads against
two real DB sessions on the same underlying (SQLite, in this suite)
database, with one session's db.add() call deliberately blocked via a
threading.Event *after* its exact-match SELECT and ANN search have both
already run and found nothing (proving this is a genuine TOCTOU race, not
a case the existing ANN-similarity dedup zone would have caught anyway)
and *before* its INSERT -- so the interleaving that produces the bug is
deterministic, not timing-dependent/flaky.
"""

from __future__ import annotations

import threading

from app.db.session import SessionLocal
from app.models.concept import Concept, ConceptStatus, ResourceConcept
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.services.concept_graph import ConceptMergeError, merge_concepts, resolve_concept

CONCEPT_NAME = "Data Retention Policy"
NORMALIZED_NAME = "data retention policy"


def _make_workspace(email: str) -> str:
    db = SessionLocal()
    try:
        user = User(email=email, password_hash="x", display_name="Race")
        db.add(user)
        db.flush()
        workspace = Workspace(owner_user_id=user.id, name="Race Workspace")
        db.add(workspace)
        db.commit()
        return workspace.id
    finally:
        db.close()


def _make_resource_and_chunk(db, workspace_id: str, filename: str):
    resource = Resource(
        workspace_id=workspace_id,
        filename=filename,
        storage_key=f"k-{filename}",
        mime_type="text/plain",
        size_bytes=10,
        checksum=f"c-{filename}",
        status=ResourceStatus.READY,
    )
    db.add(resource)
    db.flush()
    chunk = ResourceChunk(
        resource_id=resource.id,
        page_number=1,
        chunk_index=0,
        content="Financial records are retained for seven years.",
        content_hash=f"h-{filename}",
        vector_point_id=f"vp-{filename}",
    )
    db.add(chunk)
    db.flush()
    return resource, chunk


def test_concurrent_resolve_concept_calls_produce_exactly_one_active_concept_with_all_evidence():
    """The core regression: two concurrent resolve_concept() calls for the
    identical normalized name must resolve to the *same* concept, leave
    exactly one ACTIVE (and zero total duplicate) row behind, and both
    calls' evidence must end up attached to that one concept -- no
    orphaned evidence pointing at a row that was rolled back."""
    workspace_id = _make_workspace("race-a@example.com")

    # Pre-create both resources/chunks in a short-lived session that
    # commits immediately, *before* either thread starts. SQLite (this
    # suite's DB) allows only one open write transaction at a time --
    # if thread B's blocked transaction still held an uncommitted
    # resource/chunk insert while blocked, thread A's own writes would
    # deadlock/"database is locked" against it, which would be a test
    # artifact, not a reflection of production (Postgres's MVCC has no
    # such single-writer limitation). Pre-creating means each thread's own
    # transaction, while it's the one actually blocked, has done no prior
    # writes and holds no lock.
    setup_db = SessionLocal()
    try:
        resource_a, chunk_a = _make_resource_and_chunk(setup_db, workspace_id, "a.pptx")
        resource_b, chunk_b = _make_resource_and_chunk(setup_db, workspace_id, "b.docx")
        setup_db.commit()
        resource_a_id, chunk_a_id = resource_a.id, chunk_a.id
        resource_b_id, chunk_b_id = resource_b.id, chunk_b.id
    finally:
        setup_db.close()

    b_reached_insert_point = threading.Event()
    release_b = threading.Event()
    results: dict[str, str] = {}
    errors: dict[str, BaseException] = {}

    def run_b():
        session_b = SessionLocal()
        original_add = session_b.add
        blocked = {"done": False}

        def blocking_add(obj):
            # Fires on resolve_concept()'s db.add(concept) call -- i.e.
            # strictly after B's own exact-match SELECT and ANN search
            # have already both run and found nothing, and strictly
            # before B's INSERT. This is what makes the race deterministic
            # rather than a flaky sleep-based test.
            if isinstance(obj, Concept) and not blocked["done"]:
                blocked["done"] = True
                b_reached_insert_point.set()
                assert release_b.wait(timeout=5), "release_b was never set -- thread A may have failed"
            return original_add(obj)

        session_b.add = blocking_add
        try:
            resolution_b = resolve_concept(session_b, workspace_id, CONCEPT_NAME)
            session_b.add(
                ResourceConcept(
                    resource_id=resource_b_id,
                    concept_id=resolution_b.concept.id,
                    confidence=0.3,
                    contribution_type="MENTIONS",
                    evidence_chunk_id=chunk_b_id,
                )
            )
            session_b.commit()
            results["b"] = resolution_b.concept.id
        except BaseException as exc:  # noqa: BLE001 - surfaced via errors dict, not swallowed
            session_b.rollback()
            errors["b"] = exc
        finally:
            session_b.close()

    thread_b = threading.Thread(target=run_b, name="resolve-concept-B")
    thread_b.start()
    assert b_reached_insert_point.wait(timeout=5), "thread B never reached its blocking point"

    session_a = SessionLocal()
    try:
        resolution_a = resolve_concept(session_a, workspace_id, CONCEPT_NAME)
        session_a.add(
            ResourceConcept(
                resource_id=resource_a_id,
                concept_id=resolution_a.concept.id,
                confidence=0.3,
                contribution_type="MENTIONS",
                evidence_chunk_id=chunk_a_id,
            )
        )
        session_a.commit()
        results["a"] = resolution_a.concept.id
    finally:
        session_a.close()

    release_b.set()
    thread_b.join(timeout=5)

    assert "b" not in errors, f"thread B raised: {errors.get('b')!r}"
    assert "a" in results and "b" in results
    assert results["a"] == results["b"], "both concurrent calls must resolve to the same concept"
    winner_id = results["a"]

    verify_db = SessionLocal()
    try:
        all_rows = (
            verify_db.query(Concept)
            .filter(Concept.workspace_id == workspace_id, Concept.normalized_name == NORMALIZED_NAME)
            .all()
        )
        assert len(all_rows) == 1, f"expected exactly one Concept row total, found {len(all_rows)}"
        assert all_rows[0].id == winner_id
        assert all_rows[0].status == ConceptStatus.ACTIVE

        active_rows = [r for r in all_rows if r.status == ConceptStatus.ACTIVE]
        assert len(active_rows) == 1, "no duplicate/orphaned ACTIVE concepts"

        evidence = verify_db.query(ResourceConcept).filter(ResourceConcept.concept_id == winner_id).all()
        assert len(evidence) == 2, "both concurrent callers' evidence must attach to the one winning concept"
        evidenced_resource_ids = {e.resource_id for e in evidence}
        assert evidenced_resource_ids == {resource_a_id, resource_b_id}

        orphaned_evidence = (
            verify_db.query(ResourceConcept).filter(ResourceConcept.concept_id != winner_id).count()
        )
        assert orphaned_evidence == 0, "no evidence should point at a concept id other than the winner"
    finally:
        verify_db.close()


def test_merge_behavior_unchanged_by_dedup_unique_index():
    """Regression: the new partial unique index must not interfere with
    the existing manual-merge escape hatch (POST /concepts/{id}/merge's
    underlying service function), including the specific case the index
    is scoped to allow -- a MERGED concept freely coexisting with a new
    ACTIVE concept that happens to share its old normalized_name."""
    workspace_id = _make_workspace("race-merge@example.com")
    db = SessionLocal()
    try:
        source = Concept(
            workspace_id=workspace_id,
            name="Gradient Descent",
            normalized_name="gradient descent",
            status=ConceptStatus.ACTIVE,
        )
        target = Concept(
            workspace_id=workspace_id,
            name="Optimization Methods",
            normalized_name="optimization methods",
            status=ConceptStatus.ACTIVE,
        )
        db.add_all([source, target])
        db.commit()

        merged = merge_concepts(db, workspace_id, source.id, target.id)
        db.commit()
        assert merged.id == target.id

        db.refresh(source)
        assert source.status == ConceptStatus.MERGED
        assert source.merged_into_concept_id == target.id

        # Merging into oneself must still be rejected, unchanged.
        try:
            merge_concepts(db, workspace_id, target.id, target.id)
            raise AssertionError("expected ConceptMergeError for self-merge")
        except ConceptMergeError:
            pass

        # The partial unique index is scoped to ACTIVE rows only: a *new*
        # ACTIVE concept sharing the now-MERGED source's old
        # normalized_name must be creatable without conflict -- exactly
        # the scenario resolve_concept() would hit if a future resource
        # proposes "Gradient Descent" again after the original was merged
        # away.
        resolution = resolve_concept(db, workspace_id, "Gradient Descent")
        db.commit()
        assert resolution.created is True
        assert resolution.concept.id != source.id
        assert resolution.concept.status == ConceptStatus.ACTIVE

        active_gradient_descent = (
            db.query(Concept)
            .filter(
                Concept.workspace_id == workspace_id,
                Concept.normalized_name == "gradient descent",
                Concept.status == ConceptStatus.ACTIVE,
            )
            .all()
        )
        assert len(active_gradient_descent) == 1
    finally:
        db.close()
