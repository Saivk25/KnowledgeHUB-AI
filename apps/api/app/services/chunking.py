"""
Page-aware chunking.

Decision: split each page's text into ~500-token (word-based approximation)
chunks with overlap, tagged with the originating page number.
Why over semantic/layout-aware chunking: it is simple, deterministic, and
directly citation-friendly — every chunk maps to exactly one page, which is
required by the frozen citation pipeline. Layout-aware chunking is deferred
to Phase 2 once real usage data exists to justify it.
"""

from __future__ import annotations

import hashlib

from app.core.config import get_settings

settings = get_settings()


class Chunk:
    def __init__(self, page_number: int, chunk_index: int, content: str):
        self.page_number = page_number
        self.chunk_index = chunk_index
        self.content = content
        self.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


def chunk_pages(
    pages: list[tuple[int, str]], chunk_size: int | None = None, overlap: int | None = None
) -> list[Chunk]:
    chunk_size = chunk_size or settings.CHUNK_TOKEN_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP

    chunks: list[Chunk] = []
    for page_number, text in pages:
        words = text.split()
        if not words:
            continue
        start = 0
        index = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            content = " ".join(words[start:end])
            if content.strip():
                chunks.append(Chunk(page_number=page_number, chunk_index=index, content=content))
                index += 1
            if end == len(words):
                break
            start = end - overlap
    return chunks
