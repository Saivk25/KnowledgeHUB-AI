"""
Milestone 5 -- image OCR extraction tests.

Unlike every other extractor, ImageOcrExtractor depends on a system-level
binary (tesseract-ocr) that the Dockerfile installs (see ADR-0012) but that
may not be present in every local dev environment -- notably, plain Windows
without a separate Tesseract install. Rather than mock the OCR engine
(which would defeat the point of testing it), these tests skip cleanly when
the binary isn't found on PATH, and run for real whenever it is -- inside
Docker, in CI, or locally if Tesseract has been installed
(see app/core/config.py's TESSERACT_CMD for a local-Windows escape hatch).
"""

import shutil

import pytest

from app.services.extraction import ExtractionError, ImageOcrExtractor
from tests.extractor_fixtures import make_sample_image

TESSERACT_AVAILABLE = shutil.which("tesseract") is not None

pytestmark = pytest.mark.skipif(
    not TESSERACT_AVAILABLE,
    reason="tesseract binary not found on PATH -- install Tesseract OCR to run this test locally",
)


def test_ocr_extracts_printed_text_with_a_real_confidence_score(tmp_path):
    path = tmp_path / "note.png"
    make_sample_image(str(path), "HELLO WORLD")

    result = ImageOcrExtractor().extract(str(path))

    assert result.page_count == 1
    unit = result.units[0]
    assert "HELLO" in unit.text.upper()
    assert "WORLD" in unit.text.upper()
    # A real per-word Tesseract confidence, normalized 0-1 -- not 1.0 (that
    # would mean we invented the number rather than reporting the engine's).
    assert 0.0 <= unit.confidence <= 1.0
    assert result.confidence == unit.confidence


def test_corrupt_image_raises_extraction_error(tmp_path):
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"this is not a real image file")

    with pytest.raises(ExtractionError) as excinfo:
        ImageOcrExtractor().extract(str(path))
    assert excinfo.value.code == "UNREADABLE_IMAGE"
