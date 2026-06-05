from __future__ import annotations

from .models import Chunk, DocumentIR, Element
from .rules import detect_sensitive


def build_chunks(
    document: DocumentIR,
    excluded_element_ids: set[str],
    max_chars: int = 900,
    allowlist=None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[Element] = []
    buffer_len = 0

    for element in document.elements:
        if element.element_id in excluded_element_ids:
            continue
        if element.type in {"header", "footer", "page_number", "watermark"}:
            continue
        if buffer and buffer_len + len(element.text) > max_chars:
            chunks.append(_chunk_from(document, buffer, len(chunks) + 1, allowlist))
            buffer = []
            buffer_len = 0
        buffer.append(element)
        buffer_len += len(element.text) + 1

    if buffer:
        chunks.append(_chunk_from(document, buffer, len(chunks) + 1, allowlist))

    return chunks


def _chunk_from(document: DocumentIR, elements: list[Element], index: int, allowlist=None) -> Chunk:
    chunk_id = f"{document.document_id}_chk_{index:04d}"
    text = "\n".join(element.text for element in elements).strip()
    markdown = "\n".join(element.markdown for element in elements).strip()
    pages = [element.page_number for element in elements if element.page_number is not None]
    title_path = _last_title_path(elements)
    flags = detect_sensitive(text)
    if allowlist is not None and allowlist.allows_sensitive_chunk(document.document_id, chunk_id, text, flags):
        flags = []
    score = _quality_score(text, title_path, flags)
    return Chunk(
        chunk_id=chunk_id,
        document_id=document.document_id,
        element_ids=[element.element_id for element in elements],
        text=text,
        markdown=markdown,
        title_path=title_path,
        page_range=[min(pages), max(pages)] if pages else [None, None],
        source_locations=[
            {
                "element_id": element.element_id,
                "page_number": element.page_number,
                "bbox": element.bbox,
            }
            for element in elements
        ],
        quality_score=score,
        flags=flags,
    )


def _last_title_path(elements: list[Element]) -> list[str]:
    for element in reversed(elements):
        if element.title_path:
            return list(element.title_path)
    return []


def _quality_score(text: str, title_path: list[str], flags: list[str]) -> float:
    score = 0.65
    if 120 <= len(text) <= 1200:
        score += 0.2
    elif len(text) < 40:
        score -= 0.2
    if title_path:
        score += 0.1
    if flags:
        score -= 0.15
    return max(0.0, min(1.0, round(score, 3)))
