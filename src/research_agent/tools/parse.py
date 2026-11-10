"""HTML and PDF parsing with a record/replay cache.

Parsing is deterministic, so it is cached by content hash + parser version.
Scanned PDFs are explicitly unsupported (no OCR in v0.1); they raise a typed
error instead of silently yielding an empty document.
"""

from __future__ import annotations

import io
import time
from datetime import UTC, datetime
from typing import Any

import trafilatura
from pypdf import PdfReader

from research_agent.cache.store import CacheStore, make_cache_key
from research_agent.core.errors import ToolResponseError
from research_agent.core.ids import content_hash, content_hash_bytes
from research_agent.models.tools import ParsedDocument, ParseRequest

HTML_PARSER_VERSION = "trafilatura-2.3.1"
PDF_PARSER_VERSION = "pypdf-6"
PARSER_CACHE_VERSION = "1"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_html(request: ParseRequest) -> ParsedDocument:
    raw = request.body
    html_text = raw.decode(request.encoding or "utf-8", errors="replace")
    text = trafilatura.extract(
        raw,
        url=request.url,
        output_format="txt",
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    metadata = trafilatura.extract_metadata(html_text, default_url=request.url, extensive=True)
    title = (metadata.title or "") if metadata else ""
    author = (metadata.author or None) if metadata else None
    published_at = _parse_date(metadata.date if metadata else None)
    language = (metadata.language or None) if metadata else None
    if not text or not text.strip():
        raise ToolResponseError(
            "no extractable text in HTML document",
            details={"url": request.url},
        )
    cleaned = text.strip()
    return ParsedDocument(
        url=request.url,
        text=cleaned,
        title=title.strip(),
        author=author,
        published_at=published_at,
        language=language,
        content_type=request.content_type,
        page_count=None,
        word_count=len(cleaned.split()),
        content_hash=content_hash(cleaned),
        parser=HTML_PARSER_VERSION,
    )


def parse_pdf(request: ParseRequest) -> ParsedDocument:
    try:
        reader = PdfReader(io.BytesIO(request.body))
    except Exception as exc:
        raise ToolResponseError(
            "invalid PDF document",
            details={"url": request.url, "error": type(exc).__name__},
        ) from exc

    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise ToolResponseError("encrypted PDF is not supported") from exc
        if not unlocked:
            raise ToolResponseError("encrypted PDF is not supported")

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append((page.extract_text() or "").strip())
        except Exception:
            pages.append("")
    text = "\n\n".join(part for part in pages if part).strip()
    if not text:
        raise ToolResponseError(
            "PDF has no extractable text layer; OCR is not supported",
            details={"url": request.url, "pages": str(len(reader.pages))},
        )

    info: dict[str, Any] = {}
    try:
        info = dict(reader.metadata or {})
    except Exception:
        info = {}
    title = str(info.get("/Title") or "").strip()
    author = str(info.get("/Author") or "").strip() or None
    return ParsedDocument(
        url=request.url,
        text=text,
        title=title,
        author=author,
        content_type=request.content_type,
        page_count=len(reader.pages),
        word_count=len(text.split()),
        content_hash=content_hash(text),
        parser=PDF_PARSER_VERSION,
    )


class DocumentParser:
    """Choose a parser by content type and optionally use the record/replay cache."""

    def __init__(self, cache: CacheStore | None = None) -> None:
        self.cache = cache

    def parse(self, request: ParseRequest) -> ParsedDocument:
        content_type = request.content_type.split(";")[0].strip().lower()
        is_pdf = content_type == "application/pdf" or request.url.lower().endswith(".pdf")
        parser_version = PDF_PARSER_VERSION if is_pdf else HTML_PARSER_VERSION
        key = make_cache_key(
            tool="parse",
            version=PARSER_CACHE_VERSION,
            request={
                "url": request.url,
                "content_type": content_type,
                "content_hash": content_hash_bytes(request.body),
            },
            config={"parser": parser_version},
        )

        if self.cache is not None and self.cache.mode == "replay":
            envelope = self.cache.get_response(tool="parse", key=key)
            return ParsedDocument.model_validate(envelope.response)

        started = time.perf_counter()
        parsed = parse_pdf(request) if is_pdf else parse_html(request)
        latency_ms = (time.perf_counter() - started) * 1000

        if self.cache is not None and self.cache.mode == "record":
            self.cache.put(
                tool="parse",
                version=PARSER_CACHE_VERSION,
                request={
                    "url": request.url,
                    "content_type": content_type,
                    "content_hash": content_hash_bytes(request.body),
                },
                response=parsed.model_dump(mode="json"),
                provider=parsed.parser,
                latency_ms=latency_ms,
                config={"parser": parser_version},
            )
        return parsed
