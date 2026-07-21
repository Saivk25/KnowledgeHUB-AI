# Milestone 1 + 2 + 3 + 4 + 5 image. Only requirements.txt is installed --
# no dev tooling (pytest/ruff/black). PyMuPDF's wheel bundles MuPDF
# statically, so PDF extraction needs no extra OS packages.
#
# Milestone 5 (Multi-Format Ingestion) adds one real OS-level dependency:
# the `tesseract-ocr` system package, required by pytesseract for image OCR
# (app/services/extraction.py's ImageOcrExtractor). This is the first
# departure from "pure Python wheels only" in this image, landing exactly in
# the milestone that needs it, per this project's established dependency
# discipline (see app/README.md).
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Milestone 4: schema is now Alembic-managed (ADR-0010), not
# Base.metadata.create_all. `alembic upgrade head` runs once, synchronously,
# before uvicorn starts -- correct for this single-api-replica Compose setup
# (see docs/adr/0009-docker-compose-not-kubernetes.md); a multi-replica
# deployment should instead run migrations as a separate one-shot job/init
# container ahead of scaling the api service, not on every replica's boot.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
