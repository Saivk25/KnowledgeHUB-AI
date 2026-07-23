"""
Milestone 10: unit tests for app/services/intents/revision.py -- a pure
read, zero LLM calls, deriving "needs attention" purely from
quiz_attempts/viva_sessions plus the concept graph (approved design,
MILESTONE_10.md Section 4 decision 3).
"""

import pytest

from app.db.session import SessionLocal
from app.models.concept import Concept, ConceptStatus, ResourceConcept
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.study import QuizAttempt, QuizAttemptStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.intents import IntentRequest
from app.services.intents.revision import RevisionIntent


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_workspace(db):
    user = User(email="u@example.com", password_hash="x", display_name="U")
    db.add(user)
    db.flush()
    workspace = Workspace(owner_user_id=user.id, name="WS")
    db.add(workspace)
    db.flush()
    return workspace


def _make_resource_and_concept(db, workspace, name):
    resource = Resource(
        workspace_id=workspace.id,
        filename=f"{name}.txt",
        storage_key="k",
        mime_type="text/plain",
        size_bytes=10,
        checksum=name,
        status=ResourceStatus.READY,
    )
    db.add(resource)
    db.flush()
    chunk = ResourceChunk(
        resource_id=resource.id,
        page_number=1,
        chunk_index=0,
        content=f"About {name}.",
        content_hash=name,
        vector_point_id=f"vp-{name}",
    )
    db.add(chunk)
    db.flush()
    concept = Concept(
        workspace_id=workspace.id, name=name, normalized_name=name.lower(), status=ConceptStatus.ACTIVE
    )
    db.add(concept)
    db.flush()
    link = ResourceConcept(
        resource_id=resource.id,
        concept_id=concept.id,
        confidence=0.9,
        contribution_type="DEFINES",
        evidence_chunk_id=chunk.id,
    )
    db.add(link)
    db.flush()
    return resource, concept


def test_concept_with_no_history_is_flagged_never_reviewed(db):
    workspace = _make_workspace(db)
    resource, concept = _make_resource_and_concept(db, workspace, "GradientDescent")
    db.commit()

    response = RevisionIntent().handle(db, workspace, IntentRequest(intent="REVISION"))

    assert response.status == "OK"
    assert response.provenance == "LOCAL"
    item = next(i for i in response.result.items if i.conceptId == concept.id)
    assert item.reason == "Never reviewed"
    assert item.priority == 1


def test_concept_with_low_graded_quiz_is_flagged_with_score(db):
    workspace = _make_workspace(db)
    resource, concept = _make_resource_and_concept(db, workspace, "Backprop")
    attempt = QuizAttempt(
        workspace_id=workspace.id,
        concept_id=concept.id,
        target_label="Backprop",
        status=QuizAttemptStatus.GRADED,
        question_count=2,
        correct_count=1,
        score=0.3,
        questions_payload="{}",
    )
    db.add(attempt)
    db.commit()

    response = RevisionIntent().handle(db, workspace, IntentRequest(intent="REVISION"))

    item = next(i for i in response.result.items if i.conceptId == concept.id)
    assert "30%" in item.reason
    assert item.priority == 2


def test_concept_with_strong_recent_quiz_is_deprioritized(db):
    workspace = _make_workspace(db)
    resource, concept = _make_resource_and_concept(db, workspace, "ChainRule")
    attempt = QuizAttempt(
        workspace_id=workspace.id,
        concept_id=concept.id,
        target_label="ChainRule",
        status=QuizAttemptStatus.GRADED,
        question_count=2,
        correct_count=2,
        score=1.0,
        questions_payload="{}",
    )
    db.add(attempt)
    db.commit()

    response = RevisionIntent().handle(db, workspace, IntentRequest(intent="REVISION"))

    item = next(i for i in response.result.items if i.conceptId == concept.id)
    assert item.priority >= 3


def test_no_concepts_returns_empty_ok_result(db):
    workspace = _make_workspace(db)
    db.commit()

    response = RevisionIntent().handle(db, workspace, IntentRequest(intent="REVISION"))

    assert response.status == "OK"
    assert response.result.items == []
