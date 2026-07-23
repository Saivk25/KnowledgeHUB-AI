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
