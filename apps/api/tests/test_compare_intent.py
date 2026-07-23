"""
Milestone 9: unit tests for app/services/intents/compare.py -- resource
vs resource, needing at least two targets, total insufficiency (with and
without external-fallback consent), and partial insufficiency (approved
design: proceed with the gap labeled, provenance stays a single LOCAL
value -- MILESTONE_9.md Section 4 decisions 1-2).
"""

import pytest

from app.db.session import SessionLocal
from app.deps import AppError
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.intents import CompareTarget, IntentRequest
from app.services.intents.compare import CompareIntent


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
        return "General knowledge comparison."

    def summarize(self, target_label, evidence):
        return "n/a"

    def compare(self, targets):
        return "Comparison of " + " vs ".join(t.label for t in targets)


def _make_workspace(db):
    user = User(email="u@example.com", password_hash="x", display_name="U")
    db.add(user)
    db.flush()
    workspace = Workspace(owner_user_id=user.id, name="WS")
    db.add(workspace)
    db.flush()
    return workspace


def _make_resource(db, workspace, filename, content):
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
        content=content,
        content_hash=filename,
        vector_point_id=f"vp-{filename}",
    )
    db.add(chunk)
    db.flush()
    return resource, chunk


def test_compare_two_resources_with_evidence(db, monkeypatch):
    workspace = _make_workspace(db)
    resource_a, _ = _make_resource(db, workspace, "a.txt", "Content about topic A.")
    resource_b, _ = _make_resource(db, workspace, "b.txt", "Content about topic B.")
    db.commit()
    monkeypatch.setattr("app.services.intents.compare.get_llm_provider", lambda: _StubLLMProvider())

    response = CompareIntent().handle(
        db,
        workspace,
        IntentRequest(
            intent="COMPARE",
            targets=[
                CompareTarget(label="A", resourceId=resource_a.id),
                CompareTarget(label="B", resourceId=resource_b.id),
            ],
        ),
    )

    assert response.status == "OK"
    assert response.provenance == "LOCAL"
    assert len(response.result.targets) == 2
    assert all(t.hasEvidence for t in response.result.targets)
    # Citation order numbers are reassigned globally across targets, not
    # reset to 1 for each one.
    assert response.result.targets[0].citations[0].order == 1
    assert response.result.targets[1].citations[0].order == 2


def test_compare_needs_at_least_two_targets(db):
    workspace = _make_workspace(db)
    db.commit()
    with pytest.raises(AppError):
        CompareIntent().handle(
            db, workspace, IntentRequest(intent="COMPARE", targets=[CompareTarget(label="Only one")])
        )


def test_partial_evidence_proceeds_with_gap_labeled(db, monkeypatch):
    """Approved design decision 1: one side has evidence, the other
    doesn't -- Compare proceeds, labels the gap, never fills it."""
    workspace = _make_workspace(db)
    resource_a, _ = _make_resource(db, workspace, "a.txt", "Content about topic A.")
    db.commit()
    monkeypatch.setattr("app.services.intents.compare.get_llm_provider", lambda: _StubLLMProvider())

    response = CompareIntent().handle(
        db,
        workspace,
        IntentRequest(
            intent="COMPARE",
            targets=[
                CompareTarget(label="A", resourceId=resource_a.id),
                CompareTarget(label="Nonexistent", resourceId="does-not-exist"),
            ],
        ),
    )

    assert response.status == "OK"
    assert response.provenance == "LOCAL"  # decision 2: no fourth enum value
    assert response.canOfferExternalFallback is True
    has_evidence_flags = {t.label: t.hasEvidence for t in response.result.targets}
    assert has_evidence_flags["A"] is True
    assert has_evidence_flags["Nonexistent"] is False


def test_total_insufficiency_without_consent_is_insufficient(db, monkeypatch):
    workspace = _make_workspace(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.compare.get_llm_provider", lambda: _StubLLMProvider())

    response = CompareIntent().handle(
        db,
        workspace,
        IntentRequest(
            intent="COMPARE",
            targets=[
                CompareTarget(label="X", resourceId="nonexistent-1"),
                CompareTarget(label="Y", resourceId="nonexistent-2"),
            ],
        ),
    )

    assert response.status == "INSUFFICIENT"
    assert response.provenance is None


def test_total_insufficiency_with_consent_uses_external_fallback(db, monkeypatch):
    workspace = _make_workspace(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.compare.get_llm_provider", lambda: _StubLLMProvider())

    response = CompareIntent().handle(
        db,
        workspace,
        IntentRequest(
            intent="COMPARE",
            useExternalFallback=True,
            targets=[
                CompareTarget(label="X", resourceId="nonexistent-1"),
                CompareTarget(label="Y", resourceId="nonexistent-2"),
            ],
        ),
    )

    assert response.status == "OK"
    assert response.provenance == "EXTERNAL"
