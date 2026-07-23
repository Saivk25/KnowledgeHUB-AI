"""
Application configuration.

Decision: pydantic-settings reading from environment variables / .env.
Why over hardcoded config: keeps configuration out of source control and
matches the Docker Compose / cloud deployment model described in the SRS.

Milestone scoping note: declaring a settings field costs nothing and is
not "implementing" the feature it belongs to -- it's just typed config
schema with a safe default. Several dormant modules under app/services/,
app/core/security.py, and app/api/v1/routes/ (see app/README.md) already
reference fields below; those modules are not imported by app.main in
Milestone 1, but when they ARE imported in their milestone, they must find
a working settings object rather than raising AttributeError. Fields are
grouped by which milestone actually consumes them; only the "Milestone 1"
group is read by any code path that runs today.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # -- Milestone 1 (Project Foundation) -- actively read today ----------
    APP_NAME: str = "KnowledgeHub AI"
    ENV: str = "development"
    WEB_ORIGIN: str = "http://localhost:3000"  # CORS: the Next.js origin allowed to call this API
    DATABASE_URL: str = "sqlite:///./knowledgehub.db"
    QDRANT_URL: str = "http://localhost:6333"

    # -- Milestone 2 (Authentication) -- not read until auth router is mounted
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # -- Milestone 3 (Document Ingestion) -- not read until documents router is mounted
    QDRANT_COLLECTION: str = "document_chunks_v1"
    EMBEDDING_DIMENSION: int = 384
    STORAGE_DIR: str = "./storage"
    MAX_UPLOAD_MB: int = 25
    CHUNK_TOKEN_SIZE: int = 500
    CHUNK_OVERLAP: int = 60

    # -- Milestone 4 (RAG Chat) -- not read until chat router is mounted
    TOP_K: int = 6
    EMBEDDING_PROVIDER: str = "local"  # local | openai
    LLM_PROVIDER: str = "openai"  # openai | extractive
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # -- Milestone 5 (Multi-Format Ingestion) -- read by
    # app/services/extraction.py's ImageOcrExtractor whenever an image is
    # ingested. Left unset by default: on Linux (Docker, per the Dockerfile's
    # tesseract-ocr apt package) pytesseract finds the `tesseract` binary on
    # PATH with no configuration. Set this only for local Windows development
    # where Tesseract isn't on PATH (e.g. the default UB-Mannheim installer
    # path, `C:\Program Files\Tesseract-OCR\tesseract.exe`).
    TESSERACT_CMD: str | None = None

    # -- Milestone 6 (Metadata, Classification & Confidence) -- read by
    # app/services/classification.py. Mirrors EMBEDDING_PROVIDER/
    # LLM_PROVIDER's exact pattern: the OpenAI-backed classifier is only
    # ever selected when this is "openai" AND OPENAI_API_KEY is set;
    # otherwise the dependency-free LocalHeuristicClassifier is used, so
    # `docker compose up` with zero configuration still classifies every
    # upload (with a real, if simple, signal -- see the classifier's own
    # docstring).
    CLASSIFICATION_PROVIDER: str = "local"  # local | openai

    # -- Milestone 7 (Concept Graph) -- read by app/services/concept_linking.py
    # and app/services/concept_graph.py. CONCEPT_LINKER_PROVIDER mirrors
    # CLASSIFICATION_PROVIDER's exact pattern: OpenAIConceptLinker is only
    # ever selected when this is "openai" AND OPENAI_API_KEY is set;
    # otherwise LocalConceptLinker runs (evidence links only, no typed
    # relationships -- see concept_linking.py's docstring for why).
    CONCEPT_LINKER_PROVIDER: str = "local"  # local | openai
    # A second Qdrant collection, reusing the same deployment (DRR Section
    # 3: "reusing the existing vector store, not a new index") rather than
    # a dedicated similarity index or graph database.
    QDRANT_CONCEPT_COLLECTION: str = "concept_vectors_v1"
    # Three-zone dedup/entity-resolution thresholds (DRR Section 11).
    # Above this, a candidate concept is treated as an existing one:
    SIMILARITY_MERGE_THRESHOLD: float = 0.85
    # Between this and SIMILARITY_MERGE_THRESHOLD, a new concept is still
    # created but flagged `possible_duplicate_of_concept_id` for manual
    # review via POST /concepts/{id}/merge -- never auto-merged:
    POSSIBLE_DUPLICATE_THRESHOLD: float = 0.65
    # Belt-and-suspenders bound on every recursive concept-graph traversal,
    # independent of the visited-node guard (DRR Section 11):
    MAX_TRAVERSAL_DEPTH: int = 5

    # -- Milestone 8 (Local-First Retrieval & Provenance) -- read by
    # app/services/sufficiency.py and app/services/retrieval_service.py.
    # Ranking formula (approved design; ADR-0003 kept intact -- additive
    # boosts on top of dense similarity, no BM25/reranker/learned ranking):
    CONCEPT_MATCH_BOOST: float = 0.15
    METADATA_MATCH_BOOST: float = 0.10
    # One-hop concept expansion width (approved design: no recursive
    # traversal during retrieval -- see concept_graph.find_nearby_concepts).
    CONCEPT_EXPANSION_TOP_K: int = 5
    # Sufficiency scorer thresholds (DRR Section 10 -- fail-closed by
    # construction; a candidate list scoring below SUFFICIENCY_MIN_SCORE
    # is never labeled Local, regardless of any other signal). See
    # app/services/sufficiency.py for how these combine.
    SUFFICIENCY_MIN_SCORE: float = 0.35
    SUFFICIENCY_STRONG_SCORE: float = 0.75
    SUFFICIENCY_SECONDARY_FLOOR: float = 0.20
    SUFFICIENCY_MIN_SUPPORTING_HITS: int = 2
    # DRR Section 5: the first concrete, testable retrieval latency target
    # in this codebase ("reasonable latency" was not testable before this).
    # Local-only answer, P95. Used by tests, not enforced by any runtime
    # code path.
    RETRIEVAL_LATENCY_TARGET_MS: int = 2000

    # -- Milestone 9 (Intent Workflows) -- read by app/services/intents/.
    # Search returns this many ranked hits (no sufficiency gate applies to
    # Search itself -- see search.py's docstring).
    SEARCH_TOP_K: int = 10
    # Below this score, Search additionally calls the LLM for a grounded,
    # clearly-labeled low-confidence synthesis on top of the always-
    # returned ranked hits (approved design, MILESTONE_9.md Section 4
    # decision 3). At or above it, Search never calls an LLM at all.
    # Defaults to SUFFICIENCY_MIN_SCORE's value, not a reference to it, so
    # the two can be tuned independently later without a hidden coupling.
    SEARCH_LLM_CONFIDENCE_THRESHOLD: float = 0.35
    # Concept-target Summarize pulls at most this many evidence chunks
    # (highest ResourceConcept.confidence first) across every resource
    # that evidences the concept.
    SUMMARIZE_MAX_EVIDENCE_CHUNKS: int = 20
    # Compare accepts at most this many targets per request.
    COMPARE_MAX_TARGETS: int = 4
    # ...and at most this many evidence chunks resolved per target.
    COMPARE_MAX_EVIDENCE_PER_TARGET: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()
