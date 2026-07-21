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


@lru_cache
def get_settings() -> Settings:
    return Settings()
