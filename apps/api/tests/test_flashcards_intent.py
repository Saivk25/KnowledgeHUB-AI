"""
Milestone 10: unit tests for app/services/intents/flashcards.py -- the
same three-mode resolution (resource-target, concept-target, freeform
question) Summarize already established, generating cards instead of
prose. Mirrors test_summarize_intent.py's exact structure.
"""

import pytest

from app.db.session import SessionLocal
from app.deps import AppError
from app.models.concept import Concept, ConceptStatus, ResourceConcept
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.intents import IntentRequest
from app.services import retrieval_service
from app.services.intents.flashcards import FlashcardsIntent
from app.services.llm import FlashcardDraft


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class _StubLLMProvider:
    name = "stub"

    def answer(self, question, evidence):
        return "n/a"

    def answer_general_knowledge(self, question):
        return "n/a"

    def summarize(self, target_label, evidence):
        return "n/a"

    def compare(self, targets):
        return "n/a"

    def generate_quiz(self, target_label, evidence, count):
        raise AssertionError("not used by FlashcardsIntent")

    def generate_flashcards(self, target_label, evidence, count):
        return [
            FlashcardDraft(
                front=f"Front for {target_label} [{e.order}]", back=e.content, citation_order=e.order
            )
            for e in evidence[:count]
        ]

    def conduct_viva_turn(self, target_label, evidence, transcript_so_far):
        raise AssertionError("not used by FlashcardsIntent")

    def narrate_study_plan(self, days):
        raise AssertionError("not used by FlashcardsIntent")


class _EmptyVectorRepo:
    def search(self, query_vector, workspace_id, top_k):
        return []


def _make_workspace_and_resource(db, content="Some content to make flashcards from."):
    user = User(email="u@example.com", password_hash="x", display_name="U")
    db.add(user)
    db.flush()
    workspace = Workspace(owner_user_id=user.id, name="WS")
    db.add(workspace)
    db.flush()
    resource = Resource(
        workspace_id=workspace.id,
        filename="doc.txt",
        storage_key="k",
        mime_type="text/plain",
        size_bytes=10,
        checksum="c",
        status=ResourceStatus.READY,
    )
    db.add(resource)
    db.flush()
    chunk = ResourceChunk(
        resource_id=resource.id,
        page_number=1,
        chunk_index=0,
        content=content,
        content_hash="h",
        vector_point_id="vp-1",
    )
    db.add(chunk)
    db.flush()
    return workspace, resource, chunk


def test_resource_target_generates_cards(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.flashcards.get_llm_provider", lambda: _StubLLMProvider())

    response = FlashcardsIntent().handle(
        db, workspace, IntentRequest(intent="FLASHCARDS", resourceId=resource.id)
    )

    assert response.status == "OK"
    assert response.provenance == "LOCAL"
    assert response.result.kind == "flashcards"
    assert response.result.target == "doc.txt"
    assert len(response.result.cards) == 1
    assert response.result.cards[0].citation.chunkId == chunk.id


def test_concept_target_generates_cards(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    concept = Concept(
        workspace_id=workspace.id,
        name="Gradient Descent",
        normalized_name="gradient descent",
        status=ConceptStatus.ACTIVE,
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
    db.commit()
    monkeypatch.setattr("app.services.intents.flashcards.get_llm_provider", lambda: _StubLLMProvider())

    response = FlashcardsIntent().handle(
        db, workspace, IntentRequest(intent="FLASHCARDS", conceptId=concept.id)
    )

    assert response.status == "OK"
    assert response.result.target == "Gradient Descent"
    assert len(response.result.cards) == 1


def test_freeform_flashcards_with_zero_local_coverage_is_never_labeled_local(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _EmptyVectorRepo())
    monkeypatch.setattr(retrieval_service, "find_nearby_concepts", lambda *a, **k: [])

    response = FlashcardsIntent().handle(
        db, workspace, IntentRequest(intent="FLASHCARDS", question="something with zero coverage")
    )

    assert response.status == "INSUFFICIENT"
    assert response.provenance is None


def test_resource_not_found_raises_error(db):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    with pytest.raises(AppError):
        FlashcardsIntent().handle(db, workspace, IntentRequest(intent="FLASHCARDS", resourceId="nonexistent"))
