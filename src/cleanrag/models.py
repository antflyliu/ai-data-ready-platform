from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


JsonDict = dict[str, Any]


@dataclass
class Source:
    path: str
    filename: str
    mime_type: str
    sha256: str
    size_bytes: int


@dataclass
class Page:
    page_id: str
    page_number: int
    width: float | None = None
    height: float | None = None
    unit: str = "unknown"


@dataclass
class Element:
    element_id: str
    type: str
    text: str
    markdown: str
    page_number: int | None = None
    bbox: list[float] | None = None
    title_path: list[str] = field(default_factory=list)
    confidence: float = 1.0
    source_parser: str = "unknown"
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class ParseWarning:
    warning_id: str
    severity: str
    scope: str
    message: str
    page_number: int | None = None
    source_parser: str = "unknown"


@dataclass
class DocumentIR:
    schema_version: str
    document_id: str
    dataset_id: str
    source: Source
    pages: list[Page] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    tables: list[JsonDict] = field(default_factory=list)
    images: list[JsonDict] = field(default_factory=list)
    parse_warnings: list[ParseWarning] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class CleaningEvent:
    event_id: str
    dataset_id: str
    document_id: str
    element_id: str
    rule_id: str
    rule_version: int
    action: str
    before_snapshot: JsonDict
    after_snapshot: JsonDict
    confidence: float
    review_status: str
    operator: str
    reason: str
    created_at: str


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    element_ids: list[str]
    text: str
    markdown: str
    title_path: list[str]
    page_range: list[int | None]
    source_locations: list[JsonDict]
    quality_score: float
    flags: list[str] = field(default_factory=list)


def to_dict(value: Any) -> JsonDict:
    return asdict(value)
