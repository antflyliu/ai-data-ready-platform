from __future__ import annotations

import mimetypes
import re
from html.parser import HTMLParser
from pathlib import Path

from .models import DocumentIR, Element, Source
from .pdf_adapters import parse_pdf
from .storage import sha256_file


SUPPORTED_SUFFIXES = {".md", ".markdown", ".html", ".htm", ".txt", ".pdf"}


def discover_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def parse_file(path: Path, dataset_id: str, index: int) -> DocumentIR:
    suffix = path.suffix.lower()
    source = Source(
        path=str(path),
        filename=path.name,
        mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )
    document_id = f"doc_{index:04d}"

    if suffix in {".md", ".markdown"}:
        return _parse_markdown(path, dataset_id, document_id, source)
    if suffix in {".html", ".htm"}:
        return _parse_html(path, dataset_id, document_id, source)
    if suffix == ".txt":
        return _parse_text(path, dataset_id, document_id, source)
    if suffix == ".pdf":
        return _parse_pdf(path, dataset_id, document_id, source)

    return DocumentIR("0.1", document_id, dataset_id, source)


def _parse_markdown(path: Path, dataset_id: str, document_id: str, source: Source) -> DocumentIR:
    text = path.read_text(encoding="utf-8")
    elements: list[Element] = []
    title_stack: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        element_type = _markdown_line_type(line)
        if element_type == "title":
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            title_stack = title_stack[: max(level - 1, 0)] + [title]
            markdown = raw_line
            content = title
        else:
            markdown = raw_line
            content = line
        elements.append(
            Element(
                element_id=f"{document_id}_el_{len(elements) + 1:04d}",
                type=_noise_hint_type(content, element_type),
                text=content,
                markdown=markdown,
                title_path=list(title_stack),
                source_parser="markdown",
                metadata={"line_number": line_number},
            )
        )
    return DocumentIR("0.1", document_id, dataset_id, source, elements=elements)


def _parse_text(path: Path, dataset_id: str, document_id: str, source: Source) -> DocumentIR:
    text = path.read_text(encoding="utf-8")
    elements = [
        Element(
            element_id=f"{document_id}_el_{index:04d}",
            type=_noise_hint_type(line.strip(), "paragraph"),
            text=line.strip(),
            markdown=line.strip(),
            source_parser="text",
            metadata={"line_number": index},
        )
        for index, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
    return DocumentIR("0.1", document_id, dataset_id, source, elements=elements)


class _BlockHtmlParser(HTMLParser):
    block_tags = {"p", "li", "th", "td", "caption", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self._active_tag: str | None = None
        self._buffer: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.block_tags:
            self._flush()
            self._active_tag = tag
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._active_tag:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._active_tag:
            self._flush()

    def close(self) -> None:
        self._flush()
        super().close()

    def _flush(self) -> None:
        if not self._active_tag:
            return
        text = " ".join(part.strip() for part in self._buffer if part.strip())
        if text:
            self.blocks.append((self._active_tag, text))
        self._active_tag = None
        self._buffer = []


def _parse_html(path: Path, dataset_id: str, document_id: str, source: Source) -> DocumentIR:
    parser = _BlockHtmlParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    title_stack: list[str] = []
    elements: list[Element] = []
    for index, (tag, text) in enumerate(parser.blocks, start=1):
        if re.fullmatch(r"h[1-6]", tag):
            level = int(tag[1])
            title_stack = title_stack[: max(level - 1, 0)] + [text]
            element_type = "title"
            markdown = f"{'#' * level} {text}"
        elif tag in {"th", "td", "caption"}:
            element_type = "table"
            markdown = text
        else:
            element_type = "paragraph"
            markdown = text
        elements.append(
            Element(
                element_id=f"{document_id}_el_{index:04d}",
                type=_noise_hint_type(text, element_type),
                text=text,
                markdown=markdown,
                title_path=list(title_stack),
                source_parser="html",
                metadata={"tag": tag},
            )
        )
    return DocumentIR("0.1", document_id, dataset_id, source, elements=elements)


def _parse_pdf(path: Path, dataset_id: str, document_id: str, source: Source) -> DocumentIR:
    return parse_pdf(path, dataset_id, document_id, source)


def _markdown_line_type(line: str) -> str:
    if line.startswith("#"):
        return "title"
    if "|" in line and line.count("|") >= 2:
        return "table"
    if line.startswith(("- ", "* ", "1. ")):
        return "list"
    return "paragraph"


def _noise_hint_type(text: str, default_type: str) -> str:
    lowered = text.strip().lower()
    if lowered.startswith("header:"):
        return "header"
    if lowered.startswith("footer:"):
        return "footer"
    if lowered.startswith("watermark:"):
        return "watermark"
    if re.fullmatch(r"(page\s*)?\d+(/\d+)?", lowered):
        return "page_number"
    return default_type
