"""
Intent Workflows (Milestone 9).

DRR Section 4 (Extensibility) requires one common IntentRequest/
IntentResponse envelope, shared across every intent (this milestone
implements four: Explain, Compare, Summarize, Search; Milestone 10 adds
five more), rather than four -- eventually nine -- independently-shaped
request/response contracts converged on retroactively. `result` is a
discriminated union (tagged by `kind`) so each intent's own payload shape
stays fully typed -- the shared envelope is the six fields above
`result`, not a lowest-common-denominator flattening of everything.

See docs/milestones/MILESTONE_9.md Section 3.1 for the full rationale and
Section 3.3 for how app/services/intents/ dispatches to one handler per
intent rather than branching on this envelope's `intent` field directly.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field

from app.schemas.chat import CitationOut


class IntentType:
    EXPLAIN = "EXPLAIN"
    SEARCH = "SEARCH"
    SUMMARIZE = "SUMMARIZE"
    COMPARE = "COMPARE"
    # Reserved for Milestone 10 (Study Workflows), not implemented by any
    # handler yet: QUIZ, FLASHCARDS, VIVA, REVISION, STUDY_PLAN.

    ALL = frozenset({EXPLAIN, SEARCH, SUMMARIZE, COMPARE})


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


class IntentRequest(BaseModel):
    intent: Literal["EXPLAIN", "SEARCH", "SUMMARIZE", "COMPARE"]
    question: str | None = Field(default=None, max_length=2000)  # EXPLAIN, SEARCH, freeform SUMMARIZE
    resourceId: str | None = None  # SUMMARIZE (resource-target mode)
    conceptId: str | None = None  # SUMMARIZE (concept-target mode)
    targets: list[CompareTarget] | None = None  # COMPARE (2..COMPARE_MAX_TARGETS targets)
    # Milestone 8's existing consent gate, unchanged in meaning: explicit
    # per-request consent to answer from general knowledge if local
    # evidence is insufficient. Applies to EXPLAIN/SUMMARIZE/COMPARE;
    # never applies to SEARCH (MILESTONE_9.md Section 4, decision 3 --
    # Search's confidence-triggered synthesis is always LOCAL-grounded).
    useExternalFallback: bool = False


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


IntentResult = Union[ExplainResult, SearchResult, SummarizeResult, CompareResult]


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
