from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from re import Pattern
from typing import Any


@dataclass
class Allowlist:
    sensitive_text: set[str] = field(default_factory=set)
    sensitive_patterns: list[Pattern[str]] = field(default_factory=list)
    chunk_ids: set[str] = field(default_factory=set)
    document_ids: set[str] = field(default_factory=set)

    def allows_sensitive_chunk(self, document_id: str, chunk_id: str, text: str, flags: list[str]) -> bool:
        if not flags:
            return False
        if document_id in self.document_ids or chunk_id in self.chunk_ids:
            return True
        lowered = text.lower()
        if any(item.lower() in lowered for item in self.sensitive_text):
            return True
        return any(pattern.search(text) for pattern in self.sensitive_patterns)


def load_allowlist(path: Path | None) -> Allowlist:
    if path is None:
        return Allowlist()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return Allowlist(
        sensitive_text=set(_strings(payload.get("sensitive_text", []))),
        sensitive_patterns=[re.compile(pattern) for pattern in _strings(payload.get("sensitive_patterns", []))],
        chunk_ids=set(_strings(payload.get("chunk_ids", []))),
        document_ids=set(_strings(payload.get("document_ids", []))),
    )


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
