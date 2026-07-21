"""
Classification provider adapter (Milestone 6).

Decision: same shape as EmbeddingProvider (services/embeddings.py) and
LLMProvider (services/llm.py) -- a small interface with two
implementations, auto-selected the same way (OpenAI-backed only when
CLASSIFICATION_PROVIDER=openai AND OPENAI_API_KEY is set; a dependency-free
local default otherwise). This is deliberate consistency, not a new pattern:
the same "zero-config golden path, pluggable real-quality path" reasoning
that shaped every other AI-adjacent seam in this codebase applies here too.

1. LocalHeuristicClassifier (default) -- a weighted keyword-rule table per
   content category (see CATEGORY_RULES below). Confidence is a real,
   documented, deterministic function of which rules actually matched --
   never an invented number (DRR Section 9). It deliberately only attempts
   `content_category`: subject/topic detection from raw word frequency
   would be a weak, arguably dishonest signal to dress up with a confidence
   score, so the local classifier leaves subject as (None, None) rather
   than guessing. This mirrors the existing rule in this codebase that a
   confidence badge that doesn't correlate with real accuracy is worse than
   no badge at all.

2. OpenAIClassifier -- one chat-completion call asking for a small JSON
   object (category, category confidence, subject, subject confidence).
   Confidence here is literally the number the model reported, not
   recomputed or adjusted.

Classification failures (either provider) are handled by the caller
(ingestion_service.py), not here -- this module only classifies or raises;
graceful degradation to OTHER/0.0 on failure is the ingestion pipeline's
policy, not the classifier's.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.models.resource import ResourceContentCategory

settings = get_settings()


@dataclass
class Classification:
    category: str
    category_confidence: float
    subject: str | None = None
    subject_confidence: float | None = None


class Classifier(ABC):
    @abstractmethod
    def classify(self, text: str, filename: str) -> Classification: ...


# Each rule is (compiled pattern, weight). A category's score is the sum of
# the weights of every rule that matches anywhere in the (lowercased) text
# or filename. This is intentionally simple lexical matching, not NLP --
# exactly the same honesty trade-off LocalHashEmbeddingProvider makes
# ("genuine, if lexical, not deep-semantic").
_WORD = lambda w: re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE)  # noqa: E731

CATEGORY_RULES: dict[str, list[tuple[re.Pattern, float]]] = {
    ResourceContentCategory.RESEARCH_PAPER: [
        (_WORD("abstract"), 2.0),
        (_WORD("references"), 1.5),
        (re.compile(r"\bet al\.?\b", re.IGNORECASE), 2.0),
        (_WORD("keywords"), 1.0),
        (_WORD("doi"), 1.5),
        (_WORD("methodology"), 1.0),
    ],
    ResourceContentCategory.LAB_MANUAL: [
        (re.compile(r"\blab(oratory)? manual\b", re.IGNORECASE), 3.0),
        (re.compile(r"\bexperiment\s*(no\.?|number)?\s*\d*\b", re.IGNORECASE), 1.5),
        (_WORD("procedure"), 1.0),
        (_WORD("apparatus"), 1.5),
        (_WORD("observation"), 1.0),
        (_WORD("aim"), 0.5),
    ],
    ResourceContentCategory.QUESTION_PAPER: [
        (re.compile(r"\bquestion paper\b", re.IGNORECASE), 3.0),
        (re.compile(r"\bmax(imum)? marks\b", re.IGNORECASE), 2.0),
        (re.compile(r"\battempt any\b", re.IGNORECASE), 2.0),
        (re.compile(r"\btime\s*:\s*\d+\s*hours?\b", re.IGNORECASE), 2.0),
        (_WORD("mcq"), 1.5),
        (re.compile(r"\bsection\s*[a-z]\b", re.IGNORECASE), 0.5),
    ],
    ResourceContentCategory.ASSIGNMENT: [
        (_WORD("assignment"), 2.5),
        (_WORD("homework"), 2.0),
        (re.compile(r"\bsubmit(ted)? by\b", re.IGNORECASE), 1.5),
        (re.compile(r"\bdue date\b", re.IGNORECASE), 1.5),
        (_WORD("deliverable"), 1.0),
    ],
    ResourceContentCategory.LECTURE: [
        (_WORD("lecture"), 2.5),
        (_WORD("syllabus"), 1.5),
        (re.compile(r"\bunit\s*\d+\b", re.IGNORECASE), 1.0),
        (re.compile(r"\bchapter\s*\d+\b", re.IGNORECASE), 1.0),
        (re.compile(r"\btopic\s*:", re.IGNORECASE), 1.0),
    ],
    ResourceContentCategory.PERSONAL_NOTE: [
        (re.compile(r"\bmy notes\b", re.IGNORECASE), 2.0),
        (re.compile(r"\btodo\b", re.IGNORECASE), 1.0),
        (re.compile(r"\bnote to self\b", re.IGNORECASE), 2.0),
        (re.compile(r"\bquick note\b", re.IGNORECASE), 1.5),
    ],
}

# A PPTX (slide deck) is a strong structural signal for LECTURE independent
# of keyword content -- most slide decks in an academic archive are lecture
# material. This is a filename/extension-based bonus, not a text rule.
_LECTURE_EXTENSION_BONUS = 1.5

# Normalizes a raw rule-weight score into a 0-1 confidence. This ceiling is
# the score at which confidence saturates to its cap -- a documented
# constant, not a magic number invented per-resource.
_MAX_EXPECTED_SCORE = 4.0
_MIN_CONFIDENCE_WITH_SIGNAL = 0.35
_MAX_CONFIDENCE = 0.95
_NO_SIGNAL_CONFIDENCE = 0.2


class LocalHeuristicClassifier(Classifier):
    def classify(self, text: str, filename: str) -> Classification:
        haystack = f"{filename}\n{text}"

        scores: dict[str, float] = {}
        for category, rules in CATEGORY_RULES.items():
            score = sum(weight for pattern, weight in rules if pattern.search(haystack))
            if category == ResourceContentCategory.LECTURE and filename.lower().endswith(".pptx"):
                score += _LECTURE_EXTENSION_BONUS
            if score > 0:
                scores[category] = score

        if not scores:
            return Classification(
                category=ResourceContentCategory.OTHER,
                category_confidence=_NO_SIGNAL_CONFIDENCE,
            )

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]
        confidence_range = _MAX_CONFIDENCE - _MIN_CONFIDENCE_WITH_SIGNAL
        confidence = min(
            _MAX_CONFIDENCE,
            _MIN_CONFIDENCE_WITH_SIGNAL + (best_score / _MAX_EXPECTED_SCORE) * confidence_range,
        )
        return Classification(category=best_category, category_confidence=round(confidence, 4))


_CLASSIFICATION_PROMPT = (
    "Classify the following document. Respond with ONLY a JSON object of this exact shape:\n"
    '{{"category": "<one of: {categories}>", "categoryConfidence": <0-1 float>, '
    '"subject": "<short subject/topic, or null>", "subjectConfidence": <0-1 float, or null>}}\n\n'
    "DOCUMENT (filename: {filename}):\n{text}"
)

_MAX_PROMPT_CHARS = 6000


class OpenAIClassifier(Classifier):
    def __init__(self):
        self._client = httpx.Client(
            base_url=settings.OPENAI_BASE_URL,
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            timeout=30.0,
        )

    def classify(self, text: str, filename: str) -> Classification:
        prompt = _CLASSIFICATION_PROMPT.format(
            categories=", ".join(sorted(ResourceContentCategory.ALL)),
            filename=filename,
            text=text[:_MAX_PROMPT_CHARS],
        )
        response = self._client.post(
            "/chat/completions",
            json={
                "model": settings.OPENAI_CHAT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        data = json.loads(content)

        category = data.get("category")
        if category not in ResourceContentCategory.ALL:
            category = ResourceContentCategory.OTHER
        return Classification(
            category=category,
            category_confidence=float(data.get("categoryConfidence") or 0.0),
            subject=data.get("subject") or None,
            subject_confidence=(
                float(data["subjectConfidence"]) if data.get("subjectConfidence") is not None else None
            ),
        )


_classifier: Classifier | None = None


def get_classifier() -> Classifier:
    global _classifier
    if _classifier is not None:
        return _classifier
    if settings.CLASSIFICATION_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        _classifier = OpenAIClassifier()
    else:
        _classifier = LocalHeuristicClassifier()
    return _classifier


def reset_classifier_cache() -> None:
    """Used by tests to force re-evaluation after changing settings."""
    global _classifier
    _classifier = None
