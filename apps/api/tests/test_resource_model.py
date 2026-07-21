"""
Milestone 4: Resource model behavior.

Uses the same `registered_client` fixture and real ingestion pipeline as
tests/test_ingestion.py (no mocks -- see that module's docstring) to prove
the three DRR-approved properties of the new model:

1. Every resource created through the existing (file-only) upload route is
   content_source=FILE.
2. The nullable storage columns really are nullable at the schema level --
   proven directly against the model/DB, since the current API never
   constructs a CAPTURE resource (that ingestion path is a later milestone;
   see app/models/resource.py's docstring).
3. text_hash is populated by the real ingestion pipeline once extraction
   completes, and is stable for identical text content.
"""

from tests.pdf_helpers import make_sample_pdf

POLICY_TEXT = "The expense approval threshold for department managers is five thousand dollars."


def test_uploaded_resource_has_content_source_file(registered_client, tmp_path):
    from app.db.session import SessionLocal
    from app.models.resource import Resource, ResourceContentSource

    client, _ = registered_client
    pdf_path = tmp_path / "policy.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT])

    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("policy.pdf", f, "application/pdf")})
    resource_id = resp.json()["id"]

    db = SessionLocal()
    try:
        resource = db.get(Resource, resource_id)
        assert resource.content_source == ResourceContentSource.FILE
    finally:
        db.close()


def test_resource_storage_columns_are_nullable_at_schema_level(registered_client):
    """
    Proves the schema itself supports a fileless (CAPTURE) resource, even
    though no route builds one yet -- the DRR's actual requirement (nullable
    storage columns) is a schema property, independent of whether a capture
    ingestion pipeline exists. Constructs a Resource directly (bypassing the
    upload route, which only ever produces FILE resources today) to prove
    the database will accept it.
    """
    from app.db.session import SessionLocal
    from app.models.resource import Resource, ResourceContentSource, ResourceStatus

    client, payload = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    db = SessionLocal()
    try:
        captured = Resource(
            workspace_id=workspace_id,
            content_source=ResourceContentSource.CAPTURE,
            status=ResourceStatus.READY,
            # filename/storage_key/mime_type/size_bytes/checksum intentionally
            # omitted -- this is exactly the "fileless" case the DRR asked
            # the schema to support.
        )
        db.add(captured)
        db.commit()
        db.refresh(captured)

        assert captured.filename is None
        assert captured.storage_key is None
        assert captured.mime_type is None
        assert captured.size_bytes is None
        assert captured.checksum is None
        assert captured.text_hash is None
        assert captured.content_source == ResourceContentSource.CAPTURE
    finally:
        db.close()


def test_ingestion_populates_text_hash(registered_client, tmp_path):
    from app.db.session import SessionLocal
    from app.models.resource import Resource, compute_text_hash

    client, _ = registered_client
    pdf_path = tmp_path / "policy.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT])

    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("policy.pdf", f, "application/pdf")})
    resource_id = resp.json()["id"]

    db = SessionLocal()
    try:
        resource = db.get(Resource, resource_id)
        assert resource.status == "READY"
        assert resource.text_hash is not None
        assert resource.text_hash == compute_text_hash(POLICY_TEXT)
    finally:
        db.close()


def test_compute_text_hash_is_pure_and_content_addressed():
    """
    Unit-level check of the dedup primitive itself (deliberately not routed
    through file upload/PDF generation, which would make byte-level
    determinism depend on PyMuPDF's embedded save timestamp -- not something
    this test should assert on): identical text always hashes the same;
    different text (or the same text uploaded via two different files, which
    is exactly the "content-level, not byte-level, dedup" case the DRR asked
    for -- see resource.py's docstring) must not collide; incidental leading/
    trailing whitespace does not change the hash (matches the ".strip()"
    normalization documented in compute_text_hash).
    """
    from app.models.resource import compute_text_hash

    assert compute_text_hash(POLICY_TEXT) == compute_text_hash(POLICY_TEXT)
    # Leading/trailing whitespace (e.g. a stray newline from a different PDF's
    # layout) does not change the hash -- this is what makes the same
    # sentence uploaded via two different files land on the same text_hash.
    assert compute_text_hash(POLICY_TEXT) == compute_text_hash(f"  {POLICY_TEXT}\n")
    assert compute_text_hash(POLICY_TEXT) != compute_text_hash(POLICY_TEXT + " and more.")
    assert compute_text_hash(POLICY_TEXT) != compute_text_hash("A completely different sentence.")
