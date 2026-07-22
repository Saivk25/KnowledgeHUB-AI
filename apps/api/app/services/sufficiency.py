"""
Sufficiency scorer (Milestone 8: Local-First Retrieval & Provenance).

DRR Section 10 (Critical) requires this to be a standalone, independently
tested component with defined inputs and outputs -- not a threshold buried
inside a retrieval call. This module is the single source of truth
(approved design, decision 3) for three values that the rest of the
codebase must never recompute independently:

  - the sufficiency verdict (is there enough authorized local evidence to
    answer this question at all)
  - a numeric sufficiency score
  - retrieval_confidence, stored on every Answer row and logged alongside
    its provenance label (DRR Section 16)

Fail-closed by construction (Product Vision v2 FR-10, "no hallucinated
local knowledge"): every path that cannot establish sufficiency returns
is_sufficient=False. There is no code path here that defaults to True --
an empty candidate list, a missing setting, or any other degenerate input
all resolve to INSUFFICIENT, never to an assumed-sufficient default. This
is what makes "a query with zero relevant local content must never
receive a Local label" (DRR Section 10's adversarial test) a structural
guarantee rather than something a caller has to remember to check.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings

settings = get_settings()


@dataclass
class ScoredCandidate:
    """One ranked retrieval candidate, already boosted by
    retrieval_service._score_candidates() (final_score = vector_similarity
    + concept_match_boost + metadata_match_boost -- ADR-0003-compatible
    additive ranking, no reranker). This module only ever reasons about
    the final_score distribution across candidates; it does not know or
    care whether a candidate came from vector search or concept
    expansion."""

    chunk_id: str
    resource_id: str
    final_score: float


@dataclass
class SufficiencyVerdict:
    is_sufficient: bool
    score: float
    reason: str


def compute_sufficiency(candidates: list[ScoredCandidate]) -> SufficiencyVerdict:
    """
    Inputs: the full ranked, boosted candidate list for one question
    (top-k similarity+boost scores and result count are both implicit in
    `candidates`). "Coverage across query terms/concepts" (DRR Section 10)
    is approximated by counting how many *distinct resources* clear a
    corroboration floor (`SUFFICIENCY_SECONDARY_FLOOR`) -- deliberately
    distinct resources, not distinct chunks: several chunks from the same
    single document are still only one source agreeing with itself, not
    independent corroboration. Several different resources corroborating
    each other is stronger evidence of real coverage than one isolated
    high-scoring chunk, unless that one chunk's score is high enough to
    stand on its own.

    Fail-closed formula:
      1. No candidates at all -> INSUFFICIENT, score 0.0. This is the
         DRR-mandated hard case: zero relevant local content must never
         be labeled Local.
      2. Otherwise, take the top candidate's final_score.
         - If it clears SUFFICIENCY_STRONG_SCORE, trust it alone (an
           unambiguous single match needs no corroboration).
         - Else if fewer than SUFFICIENCY_MIN_SUPPORTING_HITS distinct
           resources clear SUFFICIENCY_SECONDARY_FLOOR, the evidence is
           thin -- the score is halved before the sufficiency check.
         - Else use the top score as-is.
      3. is_sufficient is True only if the (possibly halved) score meets
         SUFFICIENCY_MIN_SCORE. Never assumed True.

    Output score is clamped to [0, 1] for storage/display: final_score can
    exceed 1.0 once concept/metadata boosts stack on top of cosine
    similarity, but the stored confidence is a 0..1 signal.
    """
    if not candidates:
        return SufficiencyVerdict(is_sufficient=False, score=0.0, reason="no_candidates")

    ordered = sorted(candidates, key=lambda c: c.final_score, reverse=True)
    top_score = ordered[0].final_score

    if top_score >= settings.SUFFICIENCY_STRONG_SCORE:
        score = top_score
        reason = "strong_single_hit"
    else:
        supporting_resources = {
            c.resource_id for c in ordered if c.final_score >= settings.SUFFICIENCY_SECONDARY_FLOOR
        }
        if len(supporting_resources) < settings.SUFFICIENCY_MIN_SUPPORTING_HITS:
            score = top_score * 0.5
            reason = "insufficient_supporting_hits"
        else:
            score = top_score
            reason = "top_score"

    is_sufficient = score >= settings.SUFFICIENCY_MIN_SCORE
    if not is_sufficient and reason == "top_score":
        reason = "below_min_score"

    clamped = max(0.0, min(1.0, score))
    return SufficiencyVerdict(is_sufficient=is_sufficient, score=clamped, reason=reason)
