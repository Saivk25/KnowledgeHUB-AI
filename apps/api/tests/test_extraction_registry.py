"""
Milestone 5 (Multi-Format Ingestion) -- Extractor registry unit tests.

Exercises each Extractor directly against real files (no mocks), plus the
registry lookup itself (get_extractor_for / is_supported_filename /
mime_type_for). Image OCR has its own test module
(test_ocr_extraction.py) since it's the one extractor with an optional
system-level dependency (the tesseract binary) that may not be installed
in every local dev environment.
"""

import pytest

from app.services.extraction import (
    CodeExtractor,
    DocxExtractor,
    ExtractionError,
    PdfExtractor,
    PptxExtractor,
    TextExtractor,
    get_extractor_for,
    is_supported_filename,
    mime_type_for,
)
from tests.extractor_fixtures import make_sample_docx, make_sample_pptx


def test_registry_resolves_every_supported_extension():
    assert isinstance(get_extractor_for("report.pdf"), PdfExtractor)
    assert isinstance(get_extractor_for("report.PDF"), PdfExtractor)  # case-insensitive
    assert isinstance(get_extractor_for("notes.docx"), DocxExtractor)
    assert isinstance(get_extractor_for("slides.pptx"), PptxExtractor)
    assert isinstance(get_extractor_for("readme.txt"), TextExtractor)
    assert isinstance(get_extractor_for("readme.md"), TextExtractor)
    assert isinstance(get_extractor_for("main.py"), CodeExtractor)
    assert isinstance(get_extractor_for("index.ts"), CodeExtractor)


def test_registry_returns_none_for_unsupported_extension():
    assert get_extractor_for("archive.zip") is None
    assert get_extractor_for("no_extension") is None


def test_is_supported_filename_and_mime_type_for():
    assert is_supported_filename("notes.docx") is True
    assert is_supported_filename("archive.zip") is False
    assert mime_type_for("slides.pptx") == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert mime_type_for("main.py") == "text/plain"


def test_docx_extraction_reads_all_paragraphs_as_one_unit(tmp_path):
    path = tmp_path / "notes.docx"
    make_sample_docx(str(path), ["First paragraph.", "Second paragraph with more content."])

    result = DocxExtractor().extract(str(path))

    assert result.page_count == 1
    assert result.confidence == 1.0
    assert "First paragraph." in result.units[0].text
    assert "Second paragraph with more content." in result.units[0].text
    assert result.units[0].unit_number == 1


def test_corrupt_docx_raises_extraction_error(tmp_path):
    path = tmp_path / "corrupt.docx"
    path.write_bytes(b"this is not a real docx file")

    with pytest.raises(ExtractionError) as excinfo:
        DocxExtractor().extract(str(path))
    assert excinfo.value.code == "UNREADABLE_DOCX"


def test_pptx_extraction_produces_one_unit_per_slide(tmp_path):
    path = tmp_path / "slides.pptx"
    make_sample_pptx(str(path), ["Introduction", "Gradient Descent Basics", "Summary"])

    result = PptxExtractor().extract(str(path))

    assert result.page_count == 3
    assert result.confidence == 1.0
    assert [u.unit_number for u in result.units] == [1, 2, 3]
    assert "Introduction" in result.units[0].text
    assert "Gradient Descent Basics" in result.units[1].text
    assert "Summary" in result.units[2].text


def test_corrupt_pptx_raises_extraction_error(tmp_path):
    path = tmp_path / "corrupt.pptx"
    path.write_bytes(b"this is not a real pptx file")

    with pytest.raises(ExtractionError) as excinfo:
        PptxExtractor().extract(str(path))
    assert excinfo.value.code == "UNREADABLE_PPTX"


def test_text_extractor_reads_txt_and_markdown_as_one_unit(tmp_path):
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("Plain text content for chunking.")
    md_path = tmp_path / "notes.md"
    md_path.write_text("# Heading\n\nSome markdown content.")

    txt_result = TextExtractor().extract(str(txt_path))
    md_result = TextExtractor().extract(str(md_path))

    assert txt_result.page_count == 1
    assert "Plain text content" in txt_result.units[0].text
    assert md_result.page_count == 1
    assert "Some markdown content" in md_result.units[0].text


def test_code_extractor_reads_source_file_as_one_unit(tmp_path):
    path = tmp_path / "main.py"
    path.write_text("def add(a, b):\n    return a + b\n")

    result = CodeExtractor().extract(str(path))

    assert result.page_count == 1
    assert result.confidence == 1.0
    assert "def add(a, b):" in result.units[0].text


def test_pdf_extractor_still_works_unchanged(tmp_path):
    """Regression check: the pre-existing PyMuPDF path is untouched by the
    registry refactor."""
    from tests.pdf_helpers import make_sample_pdf

    path = tmp_path / "policy.pdf"
    make_sample_pdf(str(path), ["Page one content.", "Page two content."])

    result = PdfExtractor().extract(str(path))

    assert result.page_count == 2
    assert result.units[0].unit_number == 1
    assert result.units[1].unit_number == 2
    assert result.confidence == 1.0
