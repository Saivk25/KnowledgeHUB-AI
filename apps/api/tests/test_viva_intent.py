"""
Milestone 10: unit tests for app/services/intents/viva.py -- session
start returns turn 1 with no prior evaluation, a continuation turn grades
the previous answer and returns the next turn, a session completes at
VIVA_MAX_TURNS, and a continuation against a finished or unknown session
is rejected.
"""

import pytest

from app.db.session import SessionLocal
from app.deps import AppError
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.intents import IntentRequest
from app.services.intents.viva import VivaIntent
from app.services.llm import VivaTurnDraft


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
        raise AssertionError("not used by VivaIntent")

    def generate_flashcards(self, target_label, evidence, count):
        raise AssertionError("not used by VivaIntent")

    def conduct_viva_turn(self, target_label, evidence, transcript_so_far):
        turn_number = len(transcript_so_far) + 1
        evaluation_verdict = "correct" if transcript_so_far else None
        evaluation_feedback = "Good." if transcript_so_far else None
        return VivaTurnDraft(
            evaluation_verdict=evaluation_verdict,
            evaluation_feedback=evaluation_feedback,
            next_question=f"Question {turn_number}?",
            next_question_rubric="rubric text",
            is_complete=False,
        )

    def narrate_study_plan(self, days):
        raise AssertionError("not used by VivaIntent")


def _make_workspace_and_resource(db, content="Some content for a viva."):
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


def test_start_returns_first_question_with_no_previous_evaluation(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.viva.get_llm_provider", lambda: _StubLLMProvider())

    response = VivaIntent().handle(db, workspace, IntentRequest(intent="VIVA", resourceId=resource.id))

    assert response.status == "OK"
    assert response.result.kind == "viva"
    assert response.result.isComplete is False
    assert response.result.turnNumber == 1
    assert response.result.previousEvaluation is None
    assert response.result.nextQuestion == "Question 1?"


def test_continuation_grades_previous_turn_and_asks_next(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.viva.get_llm_provider", lambda: _StubLLMProvider())

    start = VivaIntent().handle(db, workspace, IntentRequest(intent="VIVA", resourceId=resource.id))
    session_id = start.result.sessionId

    cont = VivaIntent().handle(
        db, workspace, IntentRequest(intent="VIVA", sessionId=session_id, vivaAnswer="my answer")
    )

    assert cont.result.turnNumber == 2
    assert cont.result.previousEvaluation is not None
    assert cont.result.previousEvaluation.verdict == "correct"
    assert cont.result.isComplete is False


def test_session_completes_at_max_turns(db, monkeypatch):
    import app.services.intents.viva as viva_module

    monkeypatch.setattr(viva_module.settings, "VIVA_MAX_TURNS", 1)
    monkeypatch.setattr(viva_module, "get_llm_provider", lambda: _StubLLMProvider())
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()

    start = viva_module.VivaIntent().handle(
        db, workspace, IntentRequest(intent="VIVA", resourceId=resource.id)
    )
    session_id = start.result.sessionId

    cont = viva_module.VivaIntent().handle(
        db, workspace, IntentRequest(intent="VIVA", sessionId=session_id, vivaAnswer="my answer")
    )

    assert cont.result.isComplete is True
    assert cont.result.nextQuestion is None


def test_continuing_completed_session_raises(db, monkeypatch):
    import app.services.intents.viva as viva_module

    monkeypatch.setattr(viva_module.settings, "VIVA_MAX_TURNS", 1)
    monkeypatch.setattr(viva_module, "get_llm_provider", lambda: _StubLLMProvider())
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()

    start = viva_module.VivaIntent().handle(
        db, workspace, IntentRequest(intent="VIVA", resourceId=resource.id)
    )
    session_id = start.result.sessionId
    viva_module.VivaIntent().handle(
        db, workspace, IntentRequest(intent="VIVA", sessionId=session_id, vivaAnswer="a1")
    )

    with pytest.raises(AppError):
        viva_module.VivaIntent().handle(
            db, workspace, IntentRequest(intent="VIVA", sessionId=session_id, vivaAnswer="a2")
        )


def test_unknown_session_id_raises(db):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    with pytest.raises(AppError):
        VivaIntent().handle(
            db, workspace, IntentRequest(intent="VIVA", sessionId="nonexistent", vivaAnswer="x")
        )
