"""
Intent Workflows (Milestones 9-10).

DRR Section 4 (Extensibility) requires one common IntentRequest/
IntentResponse envelope, shared across every intent, rather than nine
independently-shaped request/response contracts converged on
retroactively. Milestone 9 implemented the four intents closest to plain
retrieval (Explain, Search, Summarize, Compare); Milestone 10 completes
FR-8 with the five structurally heavier "study" intents (Quiz me,
Flashcards, Viva mode, Revision mode, Study planner), extending this same
envelope only additively -- every Milestone 9 field keeps its exact
meaning. `result` is a discriminated union (tagged by `kind`) so each
intent's own payload shape stays fully typed -- the shared envelope is
the six fields above `result`, not a lowest-common-denominator
flattening of everything.

See docs/milestones/MILESTONE_9.md Section 3.1 and
docs/milestones/MILESTONE_10.md Section 3.2 for the full rationale, and
Section 3.3 of each for how app/services/intents/ dispatches to one
handler per intent rather than branching on this envelope's `intent`
field directly.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Literal, Union

from pydantic import BaseModel, Field

from app.schemas.chat import CitationOut


class IntentType:
    EXPLAIN = "EXPLAIN"
    SEARCH = "SEARCH"
    SUMMARIZE = "SUMMARIZE"
    COMPARE = "COMPARE"
    QUIZ = "QUIZ"
    FLASHCARDS = "FLASHCARDS"
    VIVA = "VIVA"
    REVISION = "REVISION"
    STUDY_PLAN = "STUDY_PLAN"

    ALL = frozenset({EXPLAIN, SEARCH, SUMMARIZE, COMPARE, QUIZ, FLASHCARDS, VIVA, REVISION, STUDY_PLAN})


class CompareTarget(BaseModel):
    """One side of a Compare request. `resourceId` or `conceptId` names an
    explicit target (summarized the same way Summarize's resource/concept
    modes work); if neither is set, `question` is a freeform phrase
    resolved via the same hybrid retrieval Explain uses. Exactly one of
    the three should be set -- app/services/intents/compare.py validates
    this, not this schema, matching this codebase's convention of keeping
    cross-field invariants in application code, not in Pydantic/SQL."""

    label: str = Field(min_length=1, max_length=100)
    resourceId: str | None = None
    conceptId: str | None = None
    question: str | None = Field(default=None, max_length=2000)


class QuizAnswerIn(BaseModel):
    """One of a Quiz grading turn's submitted answers (Milestone 10)."""

    questionNumber: int
    selectedChoice: int


class IntentRequest(BaseModel):
    intent: Literal[
        "EXPLAIN", "SEARCH", "SUMMARIZE", "COMPARE", "QUIZ", "FLASHCARDS", "VIVA", "REVISION", "STUDY_PLAN"
    ]
    question: str | None = Field(default=None, max_length=2000)  # EXPLAIN, SEARCH, freeform SUMMARIZE/etc.
    resourceId: str | None = None  # SUMMARIZE/FLASHCARDS/QUIZ/VIVA (resource-target mode)
    conceptId: str | None = None  # SUMMARIZE/FLASHCARDS/QUIZ/VIVA (concept-target mode)
    targets: list[CompareTarget] | None = None  # COMPARE (2..COMPARE_MAX_TARGETS), STUDY_PLAN (2+)
    # Milestone 8's existing consent gate, unchanged in meaning: explicit
    # per-request consent to answer from general knowledge if local
    # evidence is insufficient. Applies to EXPLAIN/SUMMARIZE/COMPARE;
    # never applies to SEARCH (MILESTONE_9.md Section 4, decision 3 --
    # Search's confidence-triggered synthesis is always LOCAL-grounded).
    useExternalFallback: bool = False

    # -- Milestone 10 (Study Workflows) --
    questionCount: int | None = None  # QUIZ: how many questions to generate (generation turn only)
    quizId: str | None = None  # QUIZ: grading turn, references the generation turn's QuizAttempt.id
    quizAnswers: list[QuizAnswerIn] | None = None  # QUIZ: grading turn, the user's selections
    sessionId: str | None = None  # VIVA: continuing an existing VivaSession
    vivaAnswer: str | None = Field(default=None, max_length=2000)  # VIVA: answer to the current question
    targetDate: _date | None = None  # STUDY_PLAN: optional deadline
    horizonDays: int | None = None  # STUDY_PLAN: fallback window if no targetDate is given


# -- Per-intent result payloads (the discriminated part of the envelope) ----


class ExplainResult(BaseModel):
    kind: Literal["explain"] = "explain"
    content: str


class SearchResult(BaseModel):
    kind: Literal["search"] = "search"
    hits: list[CitationOut]
    # Populated only when the top hit's score is below
    # SEARCH_LLM_CONFIDENCE_THRESHOLD and at least one hit exists (approved
    # design, MILESTONE_9.md Section 4 decision 3) -- a grounded synthesis
    # on top of (never instead of) the always-present `hits` above.
    assistedSynthesis: str | None = None


class SummarizeResult(BaseModel):
    kind: Literal["summarize"] = "summarize"
    content: str
    # Human-readable label for what was summarized: a resource's
    # filename, a concept's name, or the free-text question asked.
    target: str


class CompareTargetResult(BaseModel):
    label: str
    hasEvidence: bool
    citations: list[CitationOut]


class CompareResult(BaseModel):
    kind: Literal["compare"] = "compare"
    content: str
    targets: list[CompareTargetResult]


# -- Milestone 10: Quiz me -----------------------------------------------


class QuizQuestionOut(BaseModel):
    """Generation-turn shape: no answer key. See app/models/study.py's
    docstring for why the correct choice never reaches the client here."""

    questionNumber: int
    prompt: str
    choices: list[str]


class QuizGradedQuestionOut(BaseModel):
    """Grading-turn shape: correctness revealed, grounded in the citation
    the question was written from."""

    questionNumber: int
    prompt: str
    choices: list[str]
    selectedChoice: int
    correctChoice: int
    isCorrect: bool
    citation: CitationOut


class QuizResult(BaseModel):
    kind: Literal["quiz"] = "quiz"
    quizId: str
    target: str
    status: Literal["AWAITING_ANSWERS", "GRADED"]
    questions: list[QuizQuestionOut] | None = None  # present on the generation turn
    gradedQuestions: list[QuizGradedQuestionOut] | None = None  # present on the grading turn
    score: float | None = None


# -- Milestone 10: Flashcards ---------------------------------------------


class FlashcardOut(BaseModel):
    front: str
    back: str
    citation: CitationOut


class FlashcardsResult(BaseModel):
    kind: Literal["flashcards"] = "flashcards"
    target: str
    cards: list[FlashcardOut]


# -- Milestone 10: Viva mode -----------------------------------------------


class VivaEvaluationOut(BaseModel):
    verdict: Literal["correct", "partial", "incorrect"]
    feedback: str


class VivaResult(BaseModel):
    kind: Literal["viva"] = "viva"
    sessionId: str
    target: str
    isComplete: bool
    turnNumber: int
    previousEvaluation: VivaEvaluationOut | None = None  # null on the first turn
    nextQuestion: str | None = None  # null once isComplete


# -- Milestone 10: Revision mode -------------------------------------------


class RevisionItemOut(BaseModel):
    label: str
    resourceId: str | None = None
    conceptId: str | None = None
    reason: str  # e.g. "Never reviewed" | "Last quiz: 40%" | "Only 1 source linked"
    priority: int  # 1 = most urgent


class RevisionResult(BaseModel):
    kind: Literal["revision"] = "revision"
    items: list[RevisionItemOut]


# -- Milestone 10: Study planner --------------------------------------------


class StudyPlanDayOut(BaseModel):
    day: int
    date: _date | None = None
    targets: list[str]  # labels, not full CompareTarget echoes
    # Deterministic reason the scheduler assigned these targets to this
    # day, passed through LLMProvider.narrate_study_plan() for phrasing --
    # the assignment itself is never LLM-decided (MILESTONE_10.md Section
    # 4, decision 4). Identical to the scheduler's own text when no LLM
    # provider is configured.
    note: str


class StudyPlanResult(BaseModel):
    kind: Literal["study_plan"] = "study_plan"
    days: list[StudyPlanDayOut]


IntentResult = Union[
    ExplainResult,
    SearchResult,
    SummarizeResult,
    CompareResult,
    QuizResult,
    FlashcardsResult,
    VivaResult,
    RevisionResult,
    StudyPlanResult,
]


class IntentResponse(BaseModel):
    """The DRR Section 4 shared envelope. Every field above `result` is
    identical in shape and meaning across all four intents (and every
    future one); `result` is the one place each intent's own output
    schema lives."""

    intent: str
    status: str  # OK | INSUFFICIENT | ERROR
    provenance: str | None  # LOCAL | HYBRID | EXTERNAL | None
    sufficiencyScore: float
    retrievalConfidence: float
    canOfferExternalFallback: bool
    citations: list[CitationOut]
    result: IntentResult = Field(discriminator="kind")
    # Milestone 11 (Confidence & Correction UX): mirrors AnswerOut's own
    # addition (schemas/chat.py) -- one of the five fixed sufficiency
    # reason codes from services/sufficiency.py. Every existing intent
    # handler's IntentResponse(...) construction continues to work
    # unchanged (Pydantic optional-field default), matching the same
    # pattern Milestone 10 used adding its own optional envelope fields --
    # no handler in app/services/intents/ is modified by this addition,
    # so this field is always None for every intent today. It exists as
    # additive, forward-compatible schema plumbing (the field a handler
    # would populate if/when one starts resolving a real
    # SufficiencyVerdict), not as something currently wired end to end.
    sufficiencyReason: str | None = None
