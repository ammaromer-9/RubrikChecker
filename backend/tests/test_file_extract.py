import pytest

from app.services.file_extract import (
    FileExtractionError,
    FileTooLargeError,
    NoTextFoundError,
    UnsupportedFileTypeError,
    extract_text,
)
from tests.helpers import make_docx, make_pdf

LIMIT = 1_000_000


def test_txt_utf8() -> None:
    assert extract_text("a.txt", "héllo\n".encode(), max_bytes=LIMIT) == "héllo"


def test_txt_falls_back_to_cp1252() -> None:
    assert extract_text("a.txt", "café".encode("cp1252"), max_bytes=LIMIT) == "café"


def test_txt_strips_bom() -> None:
    assert extract_text("a.txt", b"\xef\xbb\xbfhi", max_bytes=LIMIT) == "hi"


def test_docx_paragraphs_and_tables() -> None:
    data = make_docx(["Intro paragraph"], table=[["Criterion", "Points"], ["Thesis", "10"]])
    text = extract_text("rubric.DOCX", data, max_bytes=LIMIT)
    assert "Intro paragraph" in text
    assert "Thesis | 10" in text


def test_pdf_text() -> None:
    assert "Hello rubric" in extract_text("a.pdf", make_pdf("Hello rubric"), max_bytes=LIMIT)


def test_pdf_without_text_layer_gives_clear_error() -> None:
    with pytest.raises(NoTextFoundError, match="scanned"):
        extract_text("scan.pdf", make_pdf(None), max_bytes=LIMIT)


def test_corrupt_pdf_and_docx() -> None:
    with pytest.raises(FileExtractionError):
        extract_text("a.pdf", b"not a pdf", max_bytes=LIMIT)
    with pytest.raises(FileExtractionError):
        extract_text("a.docx", b"not a zip", max_bytes=LIMIT)


def test_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        extract_text("a.png", b"x", max_bytes=LIMIT)


def test_empty_text_file() -> None:
    with pytest.raises(NoTextFoundError):
        extract_text("a.txt", b"  \n ", max_bytes=LIMIT)


def test_too_large() -> None:
    with pytest.raises(FileTooLargeError):
        extract_text("a.txt", b"x" * 11, max_bytes=10)
