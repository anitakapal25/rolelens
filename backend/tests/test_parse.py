import io

import docx
import pymupdf
import pytest

from app.ingest.parse import (
    EmptyDocument,
    FileTooLarge,
    TooManyPages,
    UnsupportedFileType,
    parse_document,
)

MB = 1024 * 1024


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def make_docx(paragraphs: list[str]) -> bytes:
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def test_txt_is_decoded_and_normalized() -> None:
    parsed = parse_document("job.txt", "Requirements\r\n\r\n\r\n•  Python".encode(), MB, 10)
    assert parsed.text == "Requirements\n\n• Python"
    assert parsed.page_count == 1


def test_pdf_text_and_page_count() -> None:
    parsed = parse_document("cv.pdf", make_pdf(["Experience", "Skills"]), MB, 10)
    assert "Experience" in parsed.text and "Skills" in parsed.text
    assert parsed.page_count == 2


def test_docx_paragraphs() -> None:
    parsed = parse_document("cv.docx", make_docx(["Education", "BSc"]), MB, 10)
    assert parsed.text == "Education\nBSc"


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFileType):
        parse_document("cv.png", b"data", MB, 10)


def test_rejects_oversized_file() -> None:
    with pytest.raises(FileTooLarge):
        parse_document("cv.txt", b"x" * (MB + 1), MB, 10)


def test_rejects_too_many_pdf_pages() -> None:
    with pytest.raises(TooManyPages):
        parse_document("cv.pdf", make_pdf(["p"] * 3), MB, max_pages=2)


def test_rejects_corrupt_pdf() -> None:
    with pytest.raises(UnsupportedFileType):
        parse_document("cv.pdf", b"not a pdf", MB, 10)


def test_rejects_empty_text() -> None:
    with pytest.raises(EmptyDocument):
        parse_document("cv.txt", b"   \n\n ", MB, 10)
