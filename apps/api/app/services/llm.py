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
