"""
Embedding provider adapter.

Decision: a small provider interface with two implementations.

1. LocalHashEmbeddingProvider (default) -- a deterministic, dependency-free
   bag-of-hashed-words vector. No API key, no model download, no GPU. It
   gives genuine (if lexical, not deep-semantic) similarity: documents that
   share vocabulary with the question score higher than unrelated documents.
   This is what makes `docker compose up` produce a working demo with zero
   configuration -- critical for a recruiter running this cold.

2. OpenAIEmbeddingProvider -- calls an OpenAI-compatible embeddings endpoint
   (default model text-embedding-3-small, per the SRS). This is the
   production-quality path: swap in by setting OPENAI_API_KEY and
   EMBEDDING_PROVIDER=openai. The interface is intentionally identical to
   BAAI/bge-m3-style providers so that path is a drop-in replacement later
   (see ADR-0004).

Why not ship a real local transformer model (e.g. sentence-transformers)
as the zero-config default: a ~400MB first-time model download is a poor
experience for a 2-day portfolio MVP and risks failing in offline/CI
environments. It remains the natural Phase 2 upgrade for local-only
deployments that still want better-than-lexical quality without an API key.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

import httpx

from app.core.config import get_settings

settings = get_settings()

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A short stopword list so common function words don't dominate the hashed
# bag-of-words vector and drown out the content words that actually
# distinguish one chunk from another. This is the difference between "every
# chunk looks similar because they all contain 'the' and 'is'" and citations
# that reliably rank the most topically relevant page first.
_STOPWORDS = frozenset(
    """
    a an the this that these those is are was were be been being
    of to in on at for with by from as and or but if then so
    it its their his her they he she we you your our my
    not no do does did will would can could should shall may might
    per without additional up
    """.split()
)


class EmbeddingProvider(ABC):
    dimension: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class LocalHashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int | None = None):
        self.dimension = dimension or settings.EMBEDDING_DIMENSION

    def _vector_for(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            bucket = int(digest, 16) % self.dimension
            # Unsigned feature hashing: content words that appear in both the
            # query and a chunk always add constructively to the dot product.
            # (A signed hashing-trick variant reduces collision bias in
            # theory, but for short chunks it can cancel out exactly the
            # word overlap we want to reward -- see ADR-0004.)
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector_for(t) for t in texts]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self._client = httpx.Client(
            base_url=settings.OPENAI_BASE_URL,
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            timeout=30.0,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.post(
            "/embeddings",
            json={"model": settings.OPENAI_EMBEDDING_MODEL, "input": texts},
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in data]


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is not None:
        return _provider
    if settings.EMBEDDING_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        _provider = OpenAIEmbeddingProvider()
    else:
        _provider = LocalHashEmbeddingProvider()
    return _provider


def reset_embedding_provider_cache() -> None:
    """Used by tests to force re-evaluation after changing settings."""
    global _provider
    _provider = None
