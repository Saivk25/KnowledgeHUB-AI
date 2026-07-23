"""
LLM generation provider adapter.

Decision: adapter interface with two implementations, selected automatically.

1. OpenAIChatProvider — calls an OpenAI-compatible chat completions endpoint
   (default gpt-4o-mini). Used automatically when OPENAI_API_KEY is set.
   This is the recommended production path for answer quality per the SRS.

2. ExtractiveFallbackProvider — when no API key is configured, composes an
   answer directly from the retrieved evidence chunks instead of calling any
   external model. It cannot reason, but it never fabricates facts, and it
   keeps the entire golden path (upload -> index -> ask -> verify) runnable
   with zero paid dependencies. This matters for a portfolio project: a
   recruiter can clone the repo and see cited answers work before deciding
   whether to add an API key.

Why not require an API key outright: it would make the "one command,
no configuration" promise in the README false, and MVP acceptance is judged
against the golden path working end-to-end for any evaluator.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

settings = get_settings()


@dataclass
class EvidenceChunk:
    order: int
    document_filename: str
    page_number: int
    content: str


@dataclass
class ComparisonEvidence:
    """One side of a Compare request (Milestone 9): a human-readable
    label plus whatever evidence was resolved for it (empty if that
    target genuinely has no local evidence -- see
    app/services/intents/compare.py, which decides that, never this
    class)."""

    label: str
    evidence: list[EvidenceChunk]


@dataclass
class QuizQuestionDraft:
    """One generated quiz question (Milestone 10), before
    app/services/intents/quiz.py splits it into the public
    QuizQuestionOut (no answer key) and the server-side-only
    QuizAttempt.questions_payload record (full answer key)."""

    prompt: str
    choices: list[str]
    correct_choice: int  # index into `choices`
    citation_order: int  # the [n] of the EvidenceChunk this question is grounded in


@dataclass
class FlashcardDraft:
    front: str
    back: str
    citation_order: int


@dataclass
class VivaTurnRecord:
    """One already-completed turn of a Viva session, passed back into
    conduct_viva_turn() as conversation history. `rubric` is the private
    grading criteria for `question` -- never shown to the client (see
    app/models/study.py's docstring)."""

    turn_number: int
    question: str
    rubric: str
    user_answer: str | None
    verdict: str | None
    feedback: str | None


@dataclass
class VivaTurnDraft:
    """conduct_viva_turn()'s return value: grades the *previous* turn
    (None on the session's first call, when there is no previous turn)
    and proposes the *next* question, or signals completion."""

    evaluation_verdict: str | None  # "correct" | "partial" | "incorrect" | None
    evaluation_feedback: str | None
    next_question: str | None  # None once is_complete
    next_question_rubric: str | None  # private grading criteria for next_question; None once is_complete
    is_complete: bool


@dataclass
class StudyDayDraft:
    """One day of a deterministically-computed study plan (Milestone 10),
    passed into narrate_study_plan() for phrasing only -- the day/target
    assignment and `reason` are decided by app/services/intents/
    study_planner.py's scheduling logic, never by the LLM (approved
    design, MILESTONE_10.md Section 4 decision 4)."""

    day: int
    targets: list[str]
    reason: str


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def answer(self, question: str, evidence: list[EvidenceChunk]) -> str: ...

    @abstractmethod
    def answer_general_knowledge(self, question: str) -> str:
        """
        Milestone 8 (Local-First Retrieval & Provenance): used only when
        retrieval_service has already determined local evidence is
        insufficient AND the caller has consent (explicit per-request
        confirmation, or the workspace's allow_external_fallback setting)
        to answer from general knowledge instead. This method must never
        be called without that consent -- retrieval_service enforces that,
        not this class -- and its output must never be presented as
        sourced from the user's documents (see
        GENERAL_KNOWLEDGE_SYSTEM_INSTRUCTIONS below).
        """
        ...

    @abstractmethod
    def summarize(self, target_label: str, evidence: list[EvidenceChunk]) -> str:
        """
        Milestone 9 (Intent Workflows): produce a synthesized summary of
        `evidence` (already resolved by app/services/intents/summarize.py
        -- a resource's full chunk set, a concept's evidence chunks, or a
        freeform query's retrieved candidates). Must still cite by [n]
        like answer() -- summarizing is not license to drop the citation
        discipline this codebase enforces everywhere else.
        """
        ...

    @abstractmethod
    def compare(self, targets: list[ComparisonEvidence]) -> str:
        """
        Milestone 9 (Intent Workflows): produce a structured comparison
        across 2+ ComparisonEvidence targets. A target with empty evidence
        must be described as having no local coverage, never silently
        skipped or filled from general knowledge (MILESTONE_9.md Section 4
        decision 1) -- app/services/intents/compare.py is what decided
        that evidence was empty; this method's job is only to say so
        honestly in the generated text.
        """
        ...

    @abstractmethod
    def generate_quiz(
        self, target_label: str, evidence: list[EvidenceChunk], count: int
    ) -> list[QuizQuestionDraft]:
        """
        Milestone 10 (Study Workflows): generate up to `count`
        multiple-choice questions grounded ONLY in `evidence` -- MCQ-only
        for this milestone (approved design, MILESTONE_10.md Section 4
        decision 2), so grading never needs a second LLM call. Every
        returned question's `citation_order` must reference a real
        `evidence` entry -- app/services/intents/quiz.py never invents a
        citation for a question this method returns.
        """
        ...

    @abstractmethod
    def generate_flashcards(
        self, target_label: str, evidence: list[EvidenceChunk], count: int
    ) -> list[FlashcardDraft]:
        """
        Milestone 10: generate up to `count` front/back flashcard pairs
        grounded ONLY in `evidence`, one card per cited excerpt -- same
        citation discipline as every other generation method here.
        """
        ...

    @abstractmethod
    def conduct_viva_turn(
        self, target_label: str, evidence: list[EvidenceChunk], transcript_so_far: list[VivaTurnRecord]
    ) -> VivaTurnDraft:
        """
        Milestone 10: one Viva mode turn. Grades `transcript_so_far`'s
        last turn (None when `transcript_so_far` is empty -- the session's
        first call) and proposes the next question grounded in `evidence`,
        or signals `is_complete=True` once every piece of evidence has
        been asked about. Must never introduce a question this evidence
        doesn't support, and must never claim an answer is correct/
        incorrect without grounding that verdict in the evidence-derived
        rubric it itself produced for the question being graded.
        """
        ...

    @abstractmethod
    def narrate_study_plan(self, days: list[StudyDayDraft]) -> list[str]:
        """
        Milestone 10: phrase each already-scheduled day's guidance text.
        The day/target assignment and each day's `reason` are computed
        deterministically by app/services/intents/study_planner.py, never
        by this method -- it may only rephrase `reason`, never change
        which targets are assigned to which day (approved design,
        MILESTONE_10.md Section 4 decision 4). Must return exactly one
        string per input `StudyDayDraft`, in the same order.
        """
        ...


SYSTEM_INSTRUCTIONS = (
    "You are KnowledgeHub AI, an enterprise document assistant. Answer ONLY using "
    "the numbered evidence excerpts provided. Every factual claim must be followed "
    "by its citation number in square brackets, e.g. [1]. If the evidence does not "
    "contain the answer, say you could not find sufficient evidence. Never invent "
    "facts, page numbers, or documents that are not in the evidence."
)

GENERAL_KNOWLEDGE_SYSTEM_INSTRUCTIONS = (
    "You are KnowledgeHub AI. The user's own documents did not contain enough "
    "evidence to answer this question, and the user has explicitly agreed to see "
    "a general-knowledge answer instead. Answer from your own knowledge, but begin "
    "your answer by clearly stating that this answer is not sourced from their "
    "documents. Never claim a fact came from their workspace."
)

# Milestone 9 (Intent Workflows):
SUMMARIZE_SYSTEM_INSTRUCTIONS = (
    "You are KnowledgeHub AI. Summarize ONLY using the numbered evidence excerpts "
    "provided. Every factual claim must be followed by its citation number in "
    "square brackets, e.g. [1]. Do not add information the evidence does not "
    "contain. Produce a concise, well-organized summary, not a list of the "
    "excerpts themselves."
)

COMPARE_SYSTEM_INSTRUCTIONS = (
    "You are KnowledgeHub AI. You will be given two or more labeled targets, each "
    "with its own numbered evidence excerpts (which may be empty for a target). "
    "Compare and contrast the targets using ONLY the evidence given for each one "
    "-- never use one target's evidence to fill a gap in another's. Every factual "
    "claim must cite its source with [n]. If a target has no evidence, say so "
    "plainly for that target instead of guessing or using general knowledge."
)


def _build_prompt(question: str, evidence: list[EvidenceChunk]) -> str:
    evidence_block = "\n\n".join(
        f"[{e.order}] (source: {e.document_filename}, page {e.page_number})\n{e.content}" for e in evidence
    )
    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"EVIDENCE:\n{evidence_block}\n\n"
        f"QUESTION: {question}\n\n"
        f"ANSWER (cite using [n]):"
    )


def _build_summarize_prompt(target_label: str, evidence: list[EvidenceChunk]) -> str:
    evidence_block = "\n\n".join(
        f"[{e.order}] (source: {e.document_filename}, page {e.page_number})\n{e.content}" for e in evidence
    )
    return (
        f"{SUMMARIZE_SYSTEM_INSTRUCTIONS}\n\n"
        f"TARGET TO SUMMARIZE: {target_label}\n\n"
        f"EVIDENCE:\n{evidence_block}\n\n"
        f"SUMMARY (cite using [n]):"
    )


def _build_compare_prompt(targets: list[ComparisonEvidence]) -> str:
    blocks = []
    for target in targets:
        if not target.evidence:
            blocks.append(f"=== {target.label} ===\n(no local evidence found for this target)")
            continue
        evidence_block = "\n\n".join(
            f"[{e.order}] (source: {e.document_filename}, page {e.page_number})\n{e.content}"
            for e in target.evidence
        )
        blocks.append(f"=== {target.label} ===\n{evidence_block}")
    return f"{COMPARE_SYSTEM_INSTRUCTIONS}\n\n" + "\n\n".join(blocks) + "\n\nCOMPARISON (cite using [n]):"


# Milestone 10 (Study Workflows):
QUIZ_SYSTEM_INSTRUCTIONS = (
    "You are KnowledgeHub AI. Write multiple-choice quiz questions using ONLY the "
    "numbered evidence excerpts provided. Every question must test something the "
    "evidence actually states -- never invent a fact the evidence does not contain. "
    "Respond with a JSON array ONLY, no prose, where each element has exactly these "
    'keys: "prompt" (string), "choices" (an array of 2-4 strings), "correctChoice" '
    '(the integer index into "choices" that is correct), and "citationOrder" (the '
    "integer [n] of the evidence excerpt the question is grounded in)."
)

FLASHCARDS_SYSTEM_INSTRUCTIONS = (
    "You are KnowledgeHub AI. Write flashcards using ONLY the numbered evidence "
    "excerpts provided -- never invent a fact the evidence does not contain. "
    "Respond with a JSON array ONLY, no prose, where each element has exactly "
    'these keys: "front" (a short question or prompt), "back" (the answer, drawn '
    'directly from the evidence), and "citationOrder" (the integer [n] of the '
    "evidence excerpt this card is grounded in)."
)

VIVA_SYSTEM_INSTRUCTIONS = (
    "You are KnowledgeHub AI conducting a spoken-exam-style Viva. You will be given "
    "numbered evidence excerpts, the transcript of the conversation so far (if any), "
    "and the grading rubric used for the most recent question (if any). First, grade "
    "the most recent answer strictly against its rubric -- never invent a fact the "
    "rubric/evidence does not support. Then propose exactly one new question grounded "
    "in evidence that has not yet been asked about, or signal completion if every "
    "excerpt has already been covered. Respond with a JSON object ONLY, no prose, "
    'with exactly these keys: "evaluationVerdict" (one of "correct", "partial", '
    '"incorrect", or null if this is the first question), "evaluationFeedback" '
    '(string or null), "nextQuestion" (string or null if complete), '
    '"nextQuestionRubric" (the private grading criteria for nextQuestion, string or '
    'null if complete), and "isComplete" (boolean).'
)

STUDY_PLAN_NARRATION_INSTRUCTIONS = (
    "You are KnowledgeHub AI. You will be given a study schedule that has already "
    "been decided -- a list of days, each with its assigned targets and the "
    "deterministic reason they were assigned. Rephrase each day's reason into a "
    "short (one sentence), encouraging guidance note. Do NOT change which targets "
    "are assigned to which day, do NOT add targets or days, and do NOT invent "
    "reasons beyond what is given -- only phrase the reason already provided. "
    "Respond with a JSON array of strings ONLY, no prose, with exactly one string "
    "per input day, in the same order."
)


def _build_quiz_prompt(target_label: str, evidence: list[EvidenceChunk], count: int) -> str:
    evidence_block = "\n\n".join(
        f"[{e.order}] (source: {e.document_filename}, page {e.page_number})\n{e.content}" for e in evidence
    )
    return (
        f"{QUIZ_SYSTEM_INSTRUCTIONS}\n\n"
        f"TARGET: {target_label}\n\n"
        f"EVIDENCE:\n{evidence_block}\n\n"
        f"Write exactly {count} questions as a JSON array."
    )


def _build_flashcards_prompt(target_label: str, evidence: list[EvidenceChunk], count: int) -> str:
    evidence_block = "\n\n".join(
        f"[{e.order}] (source: {e.document_filename}, page {e.page_number})\n{e.content}" for e in evidence
    )
    return (
        f"{FLASHCARDS_SYSTEM_INSTRUCTIONS}\n\n"
        f"TARGET: {target_label}\n\n"
        f"EVIDENCE:\n{evidence_block}\n\n"
        f"Write exactly {count} flashcards as a JSON array."
    )


def _build_viva_prompt(
    target_label: str, evidence: list[EvidenceChunk], transcript_so_far: list["VivaTurnRecord"]
) -> str:
    evidence_block = "\n\n".join(
        f"[{e.order}] (source: {e.document_filename}, page {e.page_number})\n{e.content}" for e in evidence
    )
    if not transcript_so_far:
        transcript_block = "(no turns yet -- this is the first question)"
    else:
        lines = []
        for t in transcript_so_far:
            lines.append(
                f"Turn {t.turn_number} question: {t.question}\n"
                f"Turn {t.turn_number} rubric: {t.rubric}\n"
                f"Turn {t.turn_number} user answer: {t.user_answer or '(no answer given)'}"
            )
        transcript_block = "\n\n".join(lines)
    return (
        f"{VIVA_SYSTEM_INSTRUCTIONS}\n\n"
        f"TARGET: {target_label}\n\n"
        f"EVIDENCE:\n{evidence_block}\n\n"
        f"TRANSCRIPT SO FAR:\n{transcript_block}\n\n"
        f"Respond with the JSON object described above."
    )


def _build_study_plan_narration_prompt(days: list["StudyDayDraft"]) -> str:
    lines = []
    for d in days:
        targets_str = ", ".join(d.targets)
        lines.append(f'Day {d.day}: targets=[{targets_str}], reason="{d.reason}"')
    return f"{STUDY_PLAN_NARRATION_INSTRUCTIONS}\n\n" + "\n".join(lines)


def _parse_quiz_json(raw: str, evidence: list[EvidenceChunk]) -> list[QuizQuestionDraft] | None:
    valid_orders = {e.order for e in evidence}
    try:
        items = json.loads(_strip_code_fence(raw))
        if not isinstance(items, list) or not items:
            return None
        drafts: list[QuizQuestionDraft] = []
        for item in items:
            choices = item["choices"]
            correct = item["correctChoice"]
            citation_order = item["citationOrder"]
            if not isinstance(choices, list) or not (2 <= len(choices) <= 4):
                return None
            if not isinstance(correct, int) or not (0 <= correct < len(choices)):
                return None
            if citation_order not in valid_orders:
                return None
            drafts.append(
                QuizQuestionDraft(
                    prompt=str(item["prompt"]),
                    choices=[str(c) for c in choices],
                    correct_choice=correct,
                    citation_order=citation_order,
                )
            )
        return drafts
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _parse_flashcards_json(raw: str, evidence: list[EvidenceChunk]) -> list[FlashcardDraft] | None:
    valid_orders = {e.order for e in evidence}
    try:
        items = json.loads(_strip_code_fence(raw))
        if not isinstance(items, list) or not items:
            return None
        drafts: list[FlashcardDraft] = []
        for item in items:
            citation_order = item["citationOrder"]
            if citation_order not in valid_orders:
                return None
            drafts.append(
                FlashcardDraft(
                    front=str(item["front"]), back=str(item["back"]), citation_order=citation_order
                )
            )
        return drafts
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _parse_viva_json(raw: str) -> VivaTurnDraft | None:
    try:
        item = json.loads(_strip_code_fence(raw))
        is_complete = bool(item["isComplete"])
        return VivaTurnDraft(
            evaluation_verdict=item.get("evaluationVerdict"),
            evaluation_feedback=item.get("evaluationFeedback"),
            next_question=None if is_complete else item.get("nextQuestion"),
            next_question_rubric=None if is_complete else item.get("nextQuestionRubric"),
            is_complete=is_complete,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _parse_narration_json(raw: str, expected_count: int) -> list[str] | None:
    try:
        items = json.loads(_strip_code_fence(raw))
        if not isinstance(items, list) or len(items) != expected_count:
            return None
        return [str(i) for i in items]
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _strip_code_fence(raw: str) -> str:
    """Models occasionally wrap JSON in a ```json ... ``` fence despite
    being told not to -- strip it defensively rather than failing parsing
    outright."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


class OpenAIChatProvider(LLMProvider):
    name = "openai"

    def __init__(self):
        self._client = httpx.Client(
            base_url=settings.OPENAI_BASE_URL,
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            timeout=60.0,
        )

    def answer(self, question: str, evidence: list[EvidenceChunk]) -> str:
        prompt = _build_prompt(question, evidence)
        response = self._client.post(
            "/chat/completions",
            json={
                "model": settings.OPENAI_CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def answer_general_knowledge(self, question: str) -> str:
        response = self._client.post(
            "/chat/completions",
            json={
                "model": settings.OPENAI_CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": GENERAL_KNOWLEDGE_SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": question},
                ],
                "temperature": 0.2,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def summarize(self, target_label: str, evidence: list[EvidenceChunk]) -> str:
        prompt = _build_summarize_prompt(target_label, evidence)
        response = self._client.post(
            "/chat/completions",
            json={
                "model": settings.OPENAI_CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": SUMMARIZE_SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def compare(self, targets: list[ComparisonEvidence]) -> str:
        prompt = _build_compare_prompt(targets)
        response = self._client.post(
            "/chat/completions",
            json={
                "model": settings.OPENAI_CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": COMPARE_SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def _chat(self, system_instructions: str, prompt: str, temperature: float = 0.1) -> str:
        response = self._client.post(
            "/chat/completions",
            json={
                "model": settings.OPENAI_CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def generate_quiz(
        self, target_label: str, evidence: list[EvidenceChunk], count: int
    ) -> list[QuizQuestionDraft]:
        prompt = _build_quiz_prompt(target_label, evidence, count)
        drafts = _parse_quiz_json(self._chat(QUIZ_SYSTEM_INSTRUCTIONS, prompt), evidence)
        if drafts is None:
            # One retry only, per the approved design (MILESTONE_10.md
            # Section 3.5) -- a malformed response is treated as a
            # transient model error, not silently ignored.
            drafts = _parse_quiz_json(self._chat(QUIZ_SYSTEM_INSTRUCTIONS, prompt), evidence)
        if drafts is None:
            raise RuntimeError("generate_quiz: model did not return valid quiz JSON after one retry.")
        return drafts[:count]

    def generate_flashcards(
        self, target_label: str, evidence: list[EvidenceChunk], count: int
    ) -> list[FlashcardDraft]:
        prompt = _build_flashcards_prompt(target_label, evidence, count)
        drafts = _parse_flashcards_json(self._chat(FLASHCARDS_SYSTEM_INSTRUCTIONS, prompt), evidence)
        if drafts is None:
            drafts = _parse_flashcards_json(self._chat(FLASHCARDS_SYSTEM_INSTRUCTIONS, prompt), evidence)
        if drafts is None:
            raise RuntimeError(
                "generate_flashcards: model did not return valid flashcard JSON after one retry."
            )
        return drafts[:count]

    def conduct_viva_turn(
        self, target_label: str, evidence: list[EvidenceChunk], transcript_so_far: list[VivaTurnRecord]
    ) -> VivaTurnDraft:
        prompt = _build_viva_prompt(target_label, evidence, transcript_so_far)
        draft = _parse_viva_json(self._chat(VIVA_SYSTEM_INSTRUCTIONS, prompt))
        if draft is None:
            draft = _parse_viva_json(self._chat(VIVA_SYSTEM_INSTRUCTIONS, prompt))
        if draft is None:
            raise RuntimeError("conduct_viva_turn: model did not return valid viva JSON after one retry.")
        return draft

    def narrate_study_plan(self, days: list[StudyDayDraft]) -> list[str]:
        if not days:
            return []
        prompt = _build_study_plan_narration_prompt(days)
        narrations = _parse_narration_json(self._chat(STUDY_PLAN_NARRATION_INSTRUCTIONS, prompt), len(days))
        if narrations is None:
            narrations = _parse_narration_json(
                self._chat(STUDY_PLAN_NARRATION_INSTRUCTIONS, prompt), len(days)
            )
        if narrations is None:
            # Non-critical polish call -- unlike quiz/flashcards/viva,
            # falling back to the deterministic reason text is honest and
            # safe rather than raising, since the schedule itself was
            # already fully computed before this call was made.
            return [d.reason for d in days]
        return narrations


_WORD_RE_4PLUS = re.compile(r"[a-zA-Z]{4,}")
_WORD_RE_5PLUS = re.compile(r"[A-Za-z]{5,}")


def _keyword_overlap(answer: str, rubric: str) -> float:
    """Milestone 10: ExtractiveFallbackProvider.conduct_viva_turn()'s
    honest-but-limited grading -- fraction of the rubric's distinctive
    words the user's answer also mentions. No semantic understanding,
    same "honest, not sophisticated" bar as this provider's other
    methods (ADR-0004)."""
    rubric_tokens = {w.lower() for w in _WORD_RE_4PLUS.findall(rubric)}
    if not rubric_tokens:
        return 0.0
    answer_tokens = {w.lower() for w in _WORD_RE_4PLUS.findall(answer)}
    return len(answer_tokens & rubric_tokens) / len(rubric_tokens)


class ExtractiveFallbackProvider(LLMProvider):
    name = "extractive-fallback"

    def answer(self, question: str, evidence: list[EvidenceChunk]) -> str:
        if not evidence:
            return "I could not find sufficient evidence in your authorized documents."
        lines = ["Here is what your documents say, based on the most relevant excerpts found:"]
        for e in evidence[:3]:
            snippet = e.content.strip()
            if len(snippet) > 320:
                snippet = snippet[:320].rsplit(" ", 1)[0] + "..."
            lines.append(f"{snippet} [{e.order}]")
        return "\n\n".join(lines)

    def answer_general_knowledge(self, question: str) -> str:
        # Honest degraded behavior (ADR-0004): never fabricate a
        # general-knowledge answer without a real model behind it.
        return (
            "General-knowledge answers require a configured AI provider "
            "(set OPENAI_API_KEY) -- this workspace is currently running "
            "without one, so I can only answer from your own documents."
        )

    def summarize(self, target_label: str, evidence: list[EvidenceChunk]) -> str:
        if not evidence:
            return f"No evidence was found to summarize for {target_label}."
        lines = [
            f"No synthesis model is configured, so here are the excerpts found for "
            f"{target_label} (set OPENAI_API_KEY for a real synthesized summary):"
        ]
        for e in evidence:
            snippet = e.content.strip()
            if len(snippet) > 320:
                snippet = snippet[:320].rsplit(" ", 1)[0] + "..."
            lines.append(f"{snippet} [{e.order}]")
        return "\n\n".join(lines)

    def compare(self, targets: list[ComparisonEvidence]) -> str:
        lines = [
            "No synthesis model is configured, so here is each target's evidence "
            "listed side by side (set OPENAI_API_KEY for a real synthesized comparison):"
        ]
        for target in targets:
            lines.append(f"\n{target.label}:")
            if not target.evidence:
                lines.append("(no local evidence found for this target)")
                continue
            for e in target.evidence:
                snippet = e.content.strip()
                if len(snippet) > 240:
                    snippet = snippet[:240].rsplit(" ", 1)[0] + "..."
                lines.append(f"{snippet} [{e.order}]")
        return "\n".join(lines)

    def generate_quiz(
        self, target_label: str, evidence: list[EvidenceChunk], count: int
    ) -> list[QuizQuestionDraft]:
        """Honest, not sophisticated (ADR-0004): cloze-deletion questions
        built directly from evidence sentences -- never fabricates
        content outside the evidence. Distractor choices are drawn from
        other evidence sentences' own words, so even the wrong answers
        are grounded in the same material, not invented."""
        sentences: list[tuple[str, int]] = []
        for e in evidence:
            for sent in re.split(r"(?<=[.!?])\s+", e.content.strip()):
                sent = sent.strip()
                if len(sent.split()) >= 4:
                    sentences.append((sent, e.order))
        if not sentences:
            return []

        all_words = sorted({w for sent, _ in sentences for w in _WORD_RE_5PLUS.findall(sent)})
        questions: list[QuizQuestionDraft] = []
        for sent, order in sentences[:count]:
            words = _WORD_RE_5PLUS.findall(sent)
            if not words:
                continue
            target_word = max(words, key=len)
            prompt = sent.replace(target_word, "_____", 1)
            distractors = [w for w in all_words if w.lower() != target_word.lower()][:3]
            choices = [target_word] + distractors
            questions.append(
                QuizQuestionDraft(
                    prompt=f"Fill in the blank: {prompt}",
                    choices=choices,
                    correct_choice=0,
                    citation_order=order,
                )
            )
        return questions

    def generate_flashcards(
        self, target_label: str, evidence: list[EvidenceChunk], count: int
    ) -> list[FlashcardDraft]:
        cards: list[FlashcardDraft] = []
        for e in evidence[:count]:
            snippet = e.content.strip()
            if len(snippet) > 300:
                snippet = snippet[:300].rsplit(" ", 1)[0] + "..."
            cards.append(
                FlashcardDraft(
                    front=f"{target_label}: what does source [{e.order}] say?",
                    back=snippet,
                    citation_order=e.order,
                )
            )
        return cards

    def conduct_viva_turn(
        self, target_label: str, evidence: list[EvidenceChunk], transcript_so_far: list[VivaTurnRecord]
    ) -> VivaTurnDraft:
        """Honest, not sophisticated (ADR-0004): asks the next unused
        evidence excerpt as a direct recall question, and grades the
        previous answer by keyword overlap against its own rubric (the
        evidence excerpt itself) -- explicitly weaker than the OpenAI
        path, same disclosed-limitation pattern as this provider's other
        methods."""
        evaluation_verdict: str | None = None
        evaluation_feedback: str | None = None
        if transcript_so_far:
            last = transcript_so_far[-1]
            overlap = _keyword_overlap(last.user_answer or "", last.rubric)
            if overlap >= 0.5:
                evaluation_verdict = "correct"
                evaluation_feedback = "Good -- your answer covers the key material in the source."
            elif overlap > 0:
                evaluation_verdict = "partial"
                evaluation_feedback = "Partially correct -- you covered some of it, but missed some detail."
            else:
                evaluation_verdict = "incorrect"
                evaluation_feedback = (
                    "That doesn't match the source material -- review the evidence for this question."
                )

        next_index = len(transcript_so_far)
        if next_index >= len(evidence):
            return VivaTurnDraft(evaluation_verdict, evaluation_feedback, None, None, True)

        chunk = evidence[next_index]
        next_question = f"In your own words, what does source [{chunk.order}] say about {target_label}?"
        return VivaTurnDraft(evaluation_verdict, evaluation_feedback, next_question, chunk.content, False)

    def narrate_study_plan(self, days: list[StudyDayDraft]) -> list[str]:
        # No synthesis model configured (ADR-0004): return the scheduler's
        # own deterministic reason text unchanged -- never a fabricated
        # narrative.
        return [d.reason for d in days]


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        _provider = OpenAIChatProvider()
    else:
        _provider = ExtractiveFallbackProvider()
    return _provider


def reset_llm_provider_cache() -> None:
    global _provider
    _provider = None
