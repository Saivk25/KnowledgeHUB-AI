"""
Milestone 10: unit tests for app/services/intents/study_planner.py -- a
deterministic schedule (which targets go on which day is never
LLM-decided) plus one batched narration call (approved design,
MILESTONE_10.md Section 4 decision 4); a target with no resolvable
evidence is scheduled anyway and labeled honestly, never silently dropped
(mirrors Compare's Milestone 9 precedent).
"""

from datetime import date, timedelta

import pytest

from app.db.session import SessionLocal
from app.deps import AppError
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.intents import CompareTarget, IntentRequest
from app.services.intents.study_planner import StudyPlannerIntent


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
        raise AssertionError("not used by StudyPlannerIntent")

    def generate_flashcards(self, target_label, evidence, count):
        raise AssertionError("not used by StudyPlannerIntent")

    def conduct_viva_turn(self, target_label, evidence, transcript_so_far):
        raise AssertionError("not used by StudyPlannerIntent")

    def narrate_study_plan(self, days):
        return [f"Narrated: {d.reason}" for d in days]


def _make_workspace(db):
    user = User(email="u@example.com", password_hash="x", display_name="U")
    db.add(user)
    db.flush()
    workspace = Workspace(owner_user_id=user.id, name="WS")
    db.add(workspace)
    db.flush()
    return workspace


def _make_resource(db, workspace, filename):
    resource = Resource(
        workspace_id=workspace.id,
        filename=filename,
        storage_key="k",
        mime_type="text/plain",
        size_bytes=10,
        checksum=filename,
        status=ResourceStatus.READY,
    )
    db.add(resource)
    db.flush()
    chunk = ResourceChunk(
        resource_id=resource.id,
        page_number=1,
        chunk_index=0,
        content="Content.",
        content_hash=filename,
        vector_point_id=f"vp-{filename}",
    )
    db.add(chunk)
    db.flush()
    return resource


def test_targets_are_spread_across_horizon_and_narrated(db, monkeypatch):
    workspace = _make_workspace(db)
    resource_a = _make_resource(db, workspace, "a.txt")
    resource_b = _make_resource(db, workspace, "b.txt")
    db.commit()
    monkeypatch.setattr("app.services.intents.study_planner.get_llm_provider", lambda: _StubLLMProvider())

    response = StudyPlannerIntent().handle(
        db,
        workspace,
        IntentRequest(
            intent="STUDY_PLAN",
            horizonDays=2,
            targets=[
                CompareTarget(label="A", resourceId=resource_a.id),
                CompareTarget(label="B", resourceId=resource_b.id),
            ],
        ),
    )

    assert response.status == "OK"
    assert response.provenance == "LOCAL"
    assert len(response.result.days) >= 1
    all_targets = [t for day in response.result.days for t in day.targets]
    assert set(all_targets) == {"A", "B"}
    assert all(day.note.startswith("Narrated:") for day in response.result.days)


def test_needs_at_least_two_targets(db):
    workspace = _make_workspace(db)
    db.commit()
    with pytest.raises(AppError):
        StudyPlannerIntent().handle(
            db, workspace, IntentRequest(intent="STUDY_PLAN", targets=[CompareTarget(label="Only one")])
        )


def test_target_with_no_evidence_is_labeled_honestly_not_dropped(db, monkeypatch):
    workspace = _make_workspace(db)
    resource_a = _make_resource(db, workspace, "a.txt")
    db.commit()
    monkeypatch.setattr("app.services.intents.study_planner.get_llm_provider", lambda: _StubLLMProvider())

    response = StudyPlannerIntent().handle(
        db,
        workspace,
        IntentRequest(
            intent="STUDY_PLAN",
            horizonDays=5,
            targets=[
                CompareTarget(label="A", resourceId=resource_a.id),
                CompareTarget(label="Missing", resourceId="does-not-exist"),
            ],
        ),
    )

    assert response.status == "OK"
    assert response.canOfferExternalFallback is True
    all_targets = [t for day in response.result.days for t in day.targets]
    assert "Missing" in all_targets


def test_target_date_in_past_is_rejected(db):
    workspace = _make_workspace(db)
    resource_a = _make_resource(db, workspace, "a.txt")
    resource_b = _make_resource(db, workspace, "b.txt")
    db.commit()
    with pytest.raises(AppError):
        StudyPlannerIntent().handle(
            db,
            workspace,
            IntentRequest(
                intent="STUDY_PLAN",
                targetDate=date.today() - timedelta(days=1),
                targets=[
                    CompareTarget(label="A", resourceId=resource_a.id),
                    CompareTarget(label="B", resourceId=resource_b.id),
                ],
            ),
        )


def test_horizon_too_long_is_rejected(db):
    workspace = _make_workspace(db)
    resource_a = _make_resource(db, workspace, "a.txt")
    resource_b = _make_resource(db, workspace, "b.txt")
    db.commit()
    with pytest.raises(AppError):
        StudyPlannerIntent().handle(
            db,
            workspace,
            IntentRequest(
                intent="STUDY_PLAN",
                horizonDays=999,
                targets=[
                    CompareTarget(label="A", resourceId=resource_a.id),
                    CompareTarget(label="B", resourceId=resource_b.id),
                ],
            ),
        )
