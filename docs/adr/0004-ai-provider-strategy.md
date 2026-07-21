# ADR-0004: Pluggable AI providers with automatic zero-config fallback

**Status:** Accepted (MVP)

**Decision:** Both embeddings and generation sit behind a small provider
interface (`EmbeddingProvider`, `LLMProvider`) with two implementations
each:

- **Embeddings:** `LocalHashEmbeddingProvider` (default) — a deterministic,
  dependency-free bag-of-hashed-words vector, no download, no API key.
  `OpenAIEmbeddingProvider` activates automatically when
  `EMBEDDING_PROVIDER=openai` and `OPENAI_API_KEY` is set.
- **Generation:** `ExtractiveFallbackProvider` (default without a key) —
  composes an answer directly from retrieved evidence, never calling an
  external model. `OpenAIChatProvider` activates automatically when
  `OPENAI_API_KEY` is set.

**Alternatives considered:**
- **Require an OpenAI key outright:** best answer quality, but breaks the
  "one command, no configuration" promise that matters for a portfolio
  project a recruiter will actually try to run.
- **Ship a local transformer embedding model (e.g. sentence-transformers)
  as the zero-config default:** better semantic quality than hashing, but a
  ~400MB first-run model download is a poor default experience and a
  CI/offline risk.
- **BAAI/bge-m3 + a hosted LLM as the only supported path** (the enterprise
  SRS recommendation): the right choice at scale, and this exact interface
  is what makes swapping to it later a one-file change instead of a rewrite.

**Why this wins:** `docker compose up` with zero configuration produces a
fully working golden path — upload, index, ask, verify — end to end.
Setting `OPENAI_API_KEY` upgrades both embedding and answer quality with no
code changes, which is the intended production path.

**Revisit when:** moving to BAAI/bge-m3 or another production embedding
model for better-than-lexical local search, or adding a reranker (Phase 2).
