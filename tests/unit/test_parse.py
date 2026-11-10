"""HTML/PDF parsing and parser-cache tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_agent.cache import CacheStore
from research_agent.core.errors import CacheMissError, ToolResponseError
from research_agent.models.tools import ParseRequest
from research_agent.tools.parse import DocumentParser, parse_html, parse_pdf

HTML = """
<html>
<head>
  <title>Example Domain</title>
  <meta name="author" content="A. Author">
  <meta property="article:published_time" content="2024-01-02T03:04:05Z">
</head>
<body>
  <article>
    <h1>Example Domain</h1>
    <p>This domain is for use in illustrative examples in documents. You may use
    this domain in literature without prior coordination or asking for permission.</p>
  </article>
</body>
</html>
"""


def _request(
    body: bytes, content_type: str = "text/html", url: str = "https://example.com/"
) -> ParseRequest:
    return ParseRequest(url=url, content_type=content_type, body=body)


def _minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_offset = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    )
    out.extend(trailer.encode())
    return bytes(out)


def test_parse_html_extracts_text_and_metadata() -> None:
    parsed = parse_html(_request(HTML.encode()))
    assert "Example Domain" in parsed.text
    assert parsed.title == "Example Domain"
    assert parsed.author is not None
    assert parsed.published_at is not None
    assert parsed.word_count > 0
    assert parsed.content_hash.startswith("sha256:")


def test_parse_html_rejects_empty_content() -> None:
    with pytest.raises(ToolResponseError):
        parse_html(_request(b"<html><body></body></html>"))


def test_parse_pdf_extracts_text() -> None:
    parsed = parse_pdf(_request(_minimal_pdf("Hello PDF"), content_type="application/pdf"))
    assert "Hello PDF" in parsed.text
    assert parsed.page_count == 1
    assert parsed.parser.startswith("pypdf")


def test_parse_pdf_rejects_invalid_bytes() -> None:
    with pytest.raises(ToolResponseError):
        parse_pdf(_request(b"not a pdf", content_type="application/pdf"))


def test_document_parser_record_replay(tmp_path: Path) -> None:
    record = CacheStore(tmp_path / "cache", mode="record")
    parser = DocumentParser(record)
    request = _request(HTML.encode())
    first = parser.parse(request)
    replay = DocumentParser(CacheStore(tmp_path / "cache", mode="replay"))
    second = replay.parse(request)
    assert first.text == second.text
    with pytest.raises(CacheMissError):
        replay.parse(_request(HTML.encode() + b"<!-- different -->"))


def test_document_parser_chooses_pdf_by_extension() -> None:
    parser = DocumentParser()
    parsed = parser.parse(
        _request(
            _minimal_pdf("PDF by extension"),
            content_type="application/octet-stream",
            url="https://example.com/x.pdf",
        )
    )
    assert "PDF by extension" in parsed.text
