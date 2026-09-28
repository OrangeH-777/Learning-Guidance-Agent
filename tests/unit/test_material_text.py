import re
from io import BytesIO

import pytest
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.app.core.config import PROJECT_ROOT
from backend.app.services.material_text import MaterialError, extract_text, preview_document


def word_bytes():
    document = Document()
    document.add_heading("栈与队列", level=1)
    document.add_paragraph("栈采用后进先出。")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "队列", "先进先出"
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def pdf_bytes(*, blank=False, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if not blank:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 30 250 Td (A stack is LIFO.) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("test-only-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    "suffix,content,expected",
    [
        (".md", "# 栈\n\n后进先出".encode(), "后进先出"),
        (".docx", word_bytes(), "先进先出"),
        (".pdf", pdf_bytes(), "LIFO"),
    ],
    ids=["markdown", "word", "pdf"],
)
def test_three_formats_extract_in_disposable_worker(suffix, content, expected):
    result = preview_document(content, "../../ignored-name" + suffix)
    assert expected in result["content"]
    assert result["characters"] == len(result["content"])


@pytest.mark.parametrize(
    "data,suffix",
    [
        (b"", ".md"),
        (b"\xff", ".md"),
        (b"abc\x00", ".md"),
        (pdf_bytes(blank=True), ".pdf"),
        (pdf_bytes(encrypted=True), ".pdf"),
        (b"not a pdf", ".pdf"),
        (b"legacy", ".doc"),
    ],
    ids=["empty", "encoding", "null-byte", "scanned", "encrypted", "fake-pdf", "legacy-word"],
)
def test_invalid_or_scanned_material_is_not_published(data, suffix):
    with pytest.raises(MaterialError):
        extract_text(data, suffix)


def test_corrupt_docx_returns_generic_error_and_process_timeout_is_handled(monkeypatch):
    import subprocess

    with pytest.raises(MaterialError, match="损坏"):
        preview_document(b"secret corrupt bytes", "book.docx")

    def expired(*args, **kwargs):
        raise subprocess.TimeoutExpired("parser", 30)

    monkeypatch.setattr(subprocess, "run", expired)
    with pytest.raises(MaterialError, match="超时"):
        preview_document(b"# demo", "book.md")


def test_original_teaching_code_examples_cover_boundaries():
    namespace = {}
    for path in (PROJECT_ROOT / "knowledge/data_structure/content").glob("*.md"):
        for snippet in re.findall(r"```python\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S):
            exec(compile(snippet, str(path), "exec"), namespace)
    assert namespace["brackets_match"]("([])")
    assert namespace["brackets_match"]("")
    assert not namespace["brackets_match"]("([)]")
    assert not namespace["brackets_match"]("a")
    search = namespace["binary_search_first"]
    assert search([2, 4, 4, 7, 9], 4) == 1
    assert search([2, 4, 4, 7, 9], 8) == -1
    assert search([], 1) == -1
    assert search([4], 4) == 0
    assert namespace["insertion_sort"]([5, 2, 4, 1]) == [1, 2, 4, 5]
    assert namespace["insertion_sort"]([]) == []
