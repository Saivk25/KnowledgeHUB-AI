"""
Milestone 10: unit tests for app/services/intents/quiz.py -- the
generate-then-grade two-turn flow, MCQ-only grading (exact-match against
the stored answer key, no LLM call needed to grade), and the
freeform-target FR-10 adversarial case (mirrors every other freeform
path's zero-local-coverage test in this suite).
"""

import pytest

from app.db.session import SessionLocal
from app.deps import AppError
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.intents import IntentRequest, QuizAnswerIn
from app.services import retrieval_service
from app.services.intents.quiz import QuizIntent
from app.services.llm import QuizQuestionDraft


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
        return [
            QuizQuestionDraft(
                prompt=f"What does evidence [{e.order}] say?",
                choices=["A", "B", "C", "D"],
                correct_choice=0,
                citation_order=e.order,
            )
            for e in evidence[:count]
        ]

    def generate_flashcards(self, target_label, evidence, count):
        raise AssertionError("not used by QuizIntent")

    def conduct_viva_turn(self, target_label, evidence, transcript_so_far):
        raise AssertionError("not used by QuizIntent")

    def narrate_study_plan(self, days):
        raise AssertionError("not used by QuizIntent")


class _EmptyVectorRepo:
    def search(self, query_vector, workspace_id, top_k):
        return []


def _make_workspace_and_resource(db, content="Some content to quiz on."):
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


def test_generate_then_grade_resource_target(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.quiz.get_llm_provider", lambda: _StubLLMProvider())

    gen_response = QuizIntent().handle(
        db, workspace, IntentRequest(intent="QUIZ", resourceId=resource.id, questionCount=1)
    )
    assert gen_response.status == "OK"
    assert gen_response.provenance == "LOCAL"
    assert gen_response.result.kind == "quiz"
    assert gen_response.result.status == "AWAITING_ANSWERS"
    assert len(gen_response.result.questions) == 1
    quiz_id = gen_response.result.quizId
    assert quiz_id

    grade_response = QuizIntent().handle(
        db,
        workspace,
        IntentRequest(
            intent="QUIZ", quizId=quiz_id, quizAnswers=[QuizAnswerIn(questionNumber=1, selectedChoice=0)]
        ),
    )
    assert grade_response.status == "OK"
    assert grade_response.result.status == "GRADED"
    assert grade_response.result.score == 1.0
    assert grade_response.result.gradedQuestions[0].isCorrect is True


def test_wrong_answer_is_graded_incorrect(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.quiz.get_llm_provider", lambda: _StubLLMProvider())

    gen_response = QuizIntent().handle(
        db, workspace, IntentRequest(intent="QUIZ", resourceId=resource.id, questionCount=1)
    )
    quiz_id = gen_response.result.quizId

    grade_response = QuizIntent().handle(
        db,
        workspace,
        IntentRequest(
            intent="QUIZ", quizId=quiz_id, quizAnswers=[QuizAnswerIn(questionNumber=1, selectedChoice=2)]
        ),
    )
    assert grade_response.result.score == 0.0
    assert grade_response.result.gradedQuestions[0].isCorrect is False


def test_grading_unknown_quiz_id_raises(db):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    with pytest.raises(AppError):
        QuizIntent().handle(db, workspace, IntentRequest(intent="QUIZ", quizId="nonexistent", quizAnswers=[]))


def test_regrading_already_graded_quiz_raises(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.quiz.get_llm_provider", lambda: _StubLLMProvider())

    gen_response = QuizIntent().handle(
        db, workspace, IntentRequest(intent="QUIZ", resourceId=resource.id, questionCount=1)
    )
    quiz_id = gen_response.result.quizId
    answers = [QuizAnswerIn(questionNumber=1, selectedChoice=0)]
    QuizIntent().handle(db, workspace, IntentRequest(intent="QUIZ", quizId=quiz_id, quizAnswers=answers))

    with pytest.raises(AppError):
        QuizIntent().handle(db, workspace, IntentRequest(intent="QUIZ", quizId=quiz_id, quizAnswers=answers))


def test_freeform_quiz_with_zero_local_coverage_is_never_labeled_local(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _EmptyVectorRepo())
    monkeypatch.setattr(retrieval_service, "find_nearby_concepts", lambda *a, **k: [])

    response = QuizIntent().handle(
        db, workspace, IntentRequest(intent="QUIZ", question="something with zero coverage")
    )

    assert response.status == "INSUFFICIENT"
    assert response.provenance is None
