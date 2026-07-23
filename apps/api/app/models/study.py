"""
Study Workflows (Milestone 10): server-side-only state for Quiz me's
generate-then-grade flow and Viva mode's multi-turn flow.

Neither table is ever serialized directly to the client -- both hold data
(a quiz's correct-choice indices, a viva's grading rubric) that must stay
hidden between turns. `chat.py`'s generic `create_intent` route persists
`Answer.intent_payload = intent_response.result.model_dump_json()` -- the
exact same object already returned to the caller -- so anything that must
stay hidden cannot live there (see docs/milestones/MILESTONE_10.md
Section 3.3). The public shape a client sees (`QuizResult`/`VivaResult` in
app/schemas/intents.py) is always a strict subset of what's stored here:
a `QuizQuestionOut` never carries `correctChoice`; a `VivaResult` never
carries the grading rubric for the question currently being asked.

Both tables are workspace-scoped exactly like every other table in this
codebase -- every read is filtered by `workspace_id`, matching the tenant
isolation `app/services/intents/quiz.py` and `viva.py` enforce.

Each row's full structured detail (questions + correct-choice indices +
grounding citations for `QuizAttempt`; the turn-by-turn transcript +
per-turn rubric + citations for `VivaSession`) lives in one JSON-as-Text
column, matching this codebase's existing convention for structured data
without its own relational schema (`Resource.type_metadata`,
`Answer.intent_payload`) -- not a second layer of child tables.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPK, TimestampMixin


class QuizAttemptStatus:
    GENERATED = "GENERATED"
    GRADED = "GRADED"

    ALL = frozenset({GENERATED, GRADED})


class QuizAttempt(Base, UUIDPK, TimestampMixin):
    """One Quiz me round-trip. A generation turn (`intent=QUIZ`, no
    `quizId`) creates this row with `status=GENERATED` and the full
    answer key in `questions_payload`. A later grading turn (`intent=QUIZ`,
    `quizId=<this row's id>`, `quizAnswers` set) loads the row (workspace-
    checked), grades against the stored answer key, and flips
    `status=GRADED`. Exactly one of `resource_id`/`concept_id` is set for
    the two explicit-target modes; both are null for a freeform-question
    quiz -- the same three-mode resolution Summarize/Flashcards already
    use (app/services/intents/quiz.py)."""

    __tablename__ = "quiz_attempts"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, nullable=False
    )
    resource_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("resources.id"), nullable=True)
    concept_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("concepts.id"), nullable=True)
    target_label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=QuizAttemptStatus.GENERATED)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Server-side only (see module docstring): sufficiency score, citation
    # detail, and the full question list including each one's
    # correct-choice index -- a JSON string, matching this codebase's
    # existing Text-for-JSON convention.
    questions_payload: Mapped[str] = mapped_column(Text, nullable=False)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VivaSessionStatus:
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

    ALL = frozenset({IN_PROGRESS, COMPLETED})


class VivaSession(Base, UUIDPK, TimestampMixin):
    """One Viva mode conversation. A start turn (`intent=VIVA`, no
    `sessionId`) creates this row and asks question 1. A continuation
    turn (`sessionId=<this row's id>`, `vivaAnswer` set) grades the
    previous question against its stored rubric, appends the turn to
    `transcript_payload`, and either asks the next question or marks
    `status=COMPLETED` (at `max_turns`, snapshotted from
    `VIVA_MAX_TURNS` at session start so a later config change never
    changes an in-flight session's length)."""

    __tablename__ = "viva_sessions"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, nullable=False
    )
    resource_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("resources.id"), nullable=True)
    concept_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("concepts.id"), nullable=True)
    target_label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=VivaSessionStatus.IN_PROGRESS)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False)

    # Server-side only (see module docstring): the evidence/citations
    # resolved at session start, and every turn so far (question, the
    # grading rubric used, the user's answer once given, the evaluation).
    # The client only ever sees the current question and the *previous*
    # turn's evaluation (VivaResult) -- never a rubric.
    transcript_payload: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
