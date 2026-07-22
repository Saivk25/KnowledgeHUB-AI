"""
Milestone 8: unit tests for app/services/sufficiency.py -- the standalone,
independently-tested sufficiency scorer DRR Section 10 requires. These
tests exercise compute_sufficiency() directly against synthetic
ScoredCandidate lists, with no database, no embeddings, and no HTTP layer,
so the fail-closed formula itself is verified in isolation from anything
that could mask a regression (end-to-end coverage of the same formula
lives in test_chat_citations.py's adversarial test).
"""

from app.core.config import get_settings
from app.services.sufficiency import ScoredCandidate, compute_sufficiency

settings = get_settings()


def test_no_candidates_is_never_sufficient():
    """DRR Section 10's hard case: a query with zero relevant local
    content must never receive a Local label."""
    verdict = compute_sufficiency([])
    assert verdict.is_sufficient is False
    assert verdict.score == 0.0
    assert verdict.reason == "no_candidates"


def test_single_strong_hit_is_sufficient_without_corroboration():
    candidates = [
        ScoredCandidate(chunk_id="c1", resource_id="r1", final_score=settings.SUFFICIENCY_STRONG_SCORE)
    ]
    verdict = compute_sufficiency(candidates)
    assert verdict.is_sufficient is True
    assert verdict.reason == "strong_single_hit"
    assert verdict.score == settings.SUFFICIENCY_STRONG_SCORE


def test_single_borderline_hit_without_corroboration_is_penalized():
    """A lone hit above SUFFICIENCY_MIN_SCORE but below
    SUFFICIENCY_STRONG_SCORE, with no other candidates to corroborate it,
    is halved -- thin evidence must not pass on its own."""
    top_score = settings.SUFFICIENCY_MIN_SCORE + 0.1
    candidates = [ScoredCandidate(chunk_id="c1", resource_id="r1", final_score=top_score)]
    verdict = compute_sufficiency(candidates)
    assert verdict.reason == "insufficient_supporting_hits"
    assert verdict.score == top_score * 0.5


def test_corroborated_hits_from_distinct_resources_are_sufficient():
    """Corroboration counts distinct resources, not raw chunk count --
    two different documents agreeing is real coverage."""
    top_score = settings.SUFFICIENCY_MIN_SCORE + 0.05
    candidates = [
        ScoredCandidate(chunk_id="c1", resource_id="r1", final_score=top_score),
        ScoredCandidate(chunk_id="c2", resource_id="r2", final_score=settings.SUFFICIENCY_SECONDARY_FLOOR),
    ]
    verdict = compute_sufficiency(candidates)
    assert verdict.reason == "top_score"
    assert verdict.score == top_score
    assert verdict.is_sufficient is True


def test_multiple_chunks_from_the_same_resource_do_not_count_as_corroboration():
    """Several chunks from one document are one source agreeing with
    itself, not independent corroboration -- must be penalized exactly
    like a single isolated hit, not treated as two supporting hits."""
    top_score = settings.SUFFICIENCY_MIN_SCORE + 0.05
    candidates = [
        ScoredCandidate(chunk_id="c1", resource_id="r1", final_score=top_score),
        ScoredCandidate(chunk_id="c2", resource_id="r1", final_score=settings.SUFFICIENCY_SECONDARY_FLOOR),
    ]
    verdict = compute_sufficiency(candidates)
    assert verdict.reason == "insufficient_supporting_hits"
    assert verdict.score == top_score * 0.5


def test_score_below_min_score_is_insufficient_even_with_corroboration():
    top_score = settings.SUFFICIENCY_MIN_SCORE - 0.05
    candidates = [
        ScoredCandidate(chunk_id="c1", resource_id="r1", final_score=top_score),
        ScoredCandidate(chunk_id="c2", resource_id="r2", final_score=settings.SUFFICIENCY_SECONDARY_FLOOR),
    ]
    verdict = compute_sufficiency(candidates)
    assert verdict.is_sufficient is False
    assert verdict.reason == "below_min_score"


def test_score_is_clamped_to_one():
    candidates = [ScoredCandidate(chunk_id="c1", resource_id="r1", final_score=1.4)]
    verdict = compute_sufficiency(candidates)
    assert verdict.score == 1.0


def test_only_top_candidate_counts_toward_the_reported_score():
    """Multiple strong candidates (here, from three distinct resources, so
    corroboration is satisfied) don't inflate the score beyond the top one
    -- score reflects the best evidence found, not a sum."""
    candidates = [
        ScoredCandidate(chunk_id="c1", resource_id="r1", final_score=0.4),
        ScoredCandidate(chunk_id="c2", resource_id="r2", final_score=0.3),
        ScoredCandidate(chunk_id="c3", resource_id="r3", final_score=0.25),
    ]
    verdict = compute_sufficiency(candidates)
    assert verdict.score == 0.4
