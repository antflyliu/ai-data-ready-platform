from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone

from .models import CleaningEvent, DocumentIR, Element


NOISE_TYPES = {"header", "footer", "page_number", "watermark"}


def apply_cleaning_rules(document: DocumentIR) -> tuple[list[CleaningEvent], set[str]]:
    events: list[CleaningEvent] = []
    excluded: set[str] = set()
    frequencies = Counter(_normalize(element.text) for element in document.elements)

    for element in document.elements:
        rule = _matching_rule(element, frequencies)
        if not rule:
            continue
        event = _event_for(document, element, rule[0], rule[1], rule[2])
        events.append(event)
        excluded.add(element.element_id)

    return events, excluded


def detect_sensitive(text: str) -> list[str]:
    flags: list[str] = []
    if re.search(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", text):
        flags.append("email")
    if re.search(r"\b1[3-9]\d{9}\b", text):
        flags.append("china_mobile")
    if re.search(r"\b\d{17}[\dXx]\b", text):
        flags.append("id_like")
    return flags


def _matching_rule(element: Element, frequencies: Counter[str]) -> tuple[str, int, str] | None:
    normalized = _normalize(element.text)
    if element.type in NOISE_TYPES:
        return (f"exclude_{element.type}", 1, f"{element.type}_noise")
    if normalized and frequencies[normalized] > 1 and len(normalized) <= 160:
        return ("exclude_repeated_text", 1, "repeated_text")
    return None


def _event_for(
    document: DocumentIR,
    element: Element,
    rule_id: str,
    rule_version: int,
    reason: str,
) -> CleaningEvent:
    now = datetime.now(timezone.utc).isoformat()
    before = asdict(element)
    after = {**before, "excluded_from_export": True}
    return CleaningEvent(
        event_id=f"evt_{document.document_id}_{element.element_id}_{rule_id}",
        dataset_id=document.dataset_id,
        document_id=document.document_id,
        element_id=element.element_id,
        rule_id=rule_id,
        rule_version=rule_version,
        action="exclude_from_export",
        before_snapshot=before,
        after_snapshot=after,
        confidence=0.9,
        review_status="auto_accepted",
        operator="system",
        reason=reason,
        created_at=now,
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())
