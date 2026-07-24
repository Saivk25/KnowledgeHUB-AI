"""
Milestone 12 (Section 4.3): populates a fresh workspace with every demo-data
fixture through the real running API -- registration, upload, and polling
only, exactly the same HTTP surface the frontend and any real user go
through. No database access, no shortcuts around
extraction/classification/chunking/embedding/indexing/concept-linking.

Usage (API must already be running, e.g. `docker compose up`):

    python3 demo-data/seed.py
    python3 demo-data/seed.py --base-url http://localhost:8000 --email demo@example.com

Idempotent: re-running against a workspace that already has these files
uploaded logs each 409 DUPLICATE_DOCUMENT as already-seeded rather than
failing, and registration falls back to login on 409 EMAIL_TAKEN. Uses only
httpx (already a backend dependency -- see apps/api/requirements.txt).

The seven source types this milestone's ingestion pipeline supports
(app/services/extraction.py's Extractor registry) are represented as:
  PDF          - the three existing demo-data PDFs (generate_demo_pdfs.py)
  DOCX/PPTX/
  Markdown/
  Code/Image   - the five data_retention_policy.* fixtures
                 (generate_demo_fixtures.py), deliberately sharing one
                 filename stem so they dedupe into a single Concept (see
                 that script's module docstring) -- this is what gives the
                 demo a concept with evidence from five different formats.
  YouTube      - NOT auto-ingested here. POST /documents/youtube fetches a
                 real transcript over the network from a specific public
                 video this project doesn't control, which is neither
                 deterministic nor something a seed script should depend on
                 succeeding. See demo-data/YOUTUBE_REFERENCE.md for the
                 documented reference URL and how to ingest it manually.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

DEMO_DATA_DIR = Path(__file__).parent

SEED_FILES = [
    "Expense_Policy.pdf",
    "Employee_Handbook_Excerpt.pdf",
    "Vendor_Contract_Summary.pdf",
    "data_retention_policy.docx",
    "data_retention_policy.pptx",
    "data_retention_policy.md",
    "data_retention_policy.py",
    "data_retention_policy.png",
]

TERMINAL_STATUSES = {"READY", "FAILED"}
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 120


def _register_or_login(client: httpx.Client, email: str, password: str, display_name: str) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "displayName": display_name},
    )
    if resp.status_code == 201:
        print(f"Registered new demo account: {email}")
        return
    if resp.status_code == 409:
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        resp.raise_for_status()
        print(f"Logged in to existing demo account: {email}")
        return
    resp.raise_for_status()


def _upload(client: httpx.Client, path: Path) -> str | None:
    mime_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".md": "text/markdown",
        ".py": "text/x-python",
        ".png": "image/png",
    }
    mime = mime_types.get(path.suffix.lower(), "application/octet-stream")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": (path.name, f, mime)})
    if resp.status_code == 409:
        print(f"  {path.name}: already seeded (DUPLICATE_DOCUMENT), skipping.")
        return None
    if resp.status_code != 201:
        print(f"  {path.name}: upload failed ({resp.status_code}): {resp.text}")
        return None
    document_id = resp.json()["id"]
    print(f"  {path.name}: uploaded (id={document_id})")
    return document_id


def _poll_until_ready(client: httpx.Client, document_id: str, filename: str) -> str:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    status = "QUEUED"
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/documents/{document_id}")
        resp.raise_for_status()
        detail = resp.json()
        status = detail["document"]["status"]
        if status in TERMINAL_STATUSES:
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    print(f"  {filename}: reached status={status}")
    return status


def run(base_url: str, email: str, password: str, display_name: str) -> int:
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _register_or_login(client, email, password, display_name)

        print(f"\nUploading {len(SEED_FILES)} fixtures through the real ingestion pipeline...")
        uploaded: list[tuple[str, str]] = []  # (filename, document_id)
        for name in SEED_FILES:
            path = DEMO_DATA_DIR / name
            if not path.exists():
                print(f"  {name}: MISSING on disk (run generate_demo_fixtures.py first?) -- skipping.")
                continue
            document_id = _upload(client, path)
            if document_id:
                uploaded.append((name, document_id))

        if not uploaded:
            print("\nNothing newly uploaded (workspace already fully seeded).")
            return 0

        print("\nWaiting for each resource to reach a terminal status...")
        failures = []
        for name, document_id in uploaded:
            status = _poll_until_ready(client, document_id, name)
            if status != "READY":
                failures.append(name)

        print(
            "\nYouTube (7th source type) is not auto-ingested by this script -- "
            "see demo-data/YOUTUBE_REFERENCE.md for the documented reference video "
            "and manual-ingestion steps."
        )

        if failures:
            print(f"\n{len(failures)} resource(s) did not reach READY: {', '.join(failures)}")
            return 1

        print(f"\nAll {len(uploaded)} newly uploaded resource(s) reached READY.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", default="demo@knowledgehub.local")
    parser.add_argument("--password", default="DemoPassword123")
    parser.add_argument("--display-name", default="Demo User")
    args = parser.parse_args()
    return run(args.base_url, args.email, args.password, args.display_name)


if __name__ == "__main__":
    sys.exit(main())
