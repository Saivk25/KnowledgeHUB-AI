# Milestone 1 + Milestone 2 + Milestone 3 + Milestone 4 image. Only
# requirements.txt is installed -- no dev tooling (pytest/ruff/black).
# PyMuPDF's wheel bundles MuPDF statically; empirically verified (see
# Milestone 3 verification) to need no extra OS packages for text extraction
# on python:3.11-slim, so none are added here. If a later milestone renders
# PDF pages as images (thumbnails, OCR), revisit this -- that path can need
# libgl1/libglib2.0-0.
FROM python:3.11-slim

WORKDIR /app

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
