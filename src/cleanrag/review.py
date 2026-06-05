from __future__ import annotations

import hashlib
from pathlib import Path


def build_review_items(risk_details: list[dict]) -> list[dict]:
    return [_review_item(detail) for detail in risk_details]


def write_review_items_markdown(path: Path, review_items: list[dict]) -> None:
    lines = ["# Review Items", ""]
    if not review_items:
        lines.append("- No review items.")
    else:
        for item in review_items[:100]:
            lines.extend(
                [
                    f"## {item['item_id']}",
                    "",
                    f"- Type: {item['type']}",
                    f"- Severity: {item['severity']}",
                    f"- Status: {item['status']}",
                    f"- Target: {item['target']}",
                    f"- Message: {item['message']}",
                    f"- Recommended action: {item['recommended_action']}",
                    "",
                ]
            )
        if len(review_items) > 100:
            lines.append(f"- {len(review_items) - 100} additional review item(s) omitted.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _review_item(detail: dict) -> dict:
    target = detail.get("chunk_id") or detail.get("filename") or detail.get("document_id") or "dataset"
    item_type = detail.get("type", "risk")
    return {
        "item_id": _stable_id(detail),
        "type": item_type,
        "severity": detail.get("severity", "unknown"),
        "status": "needs_review",
        "target": target,
        "document_id": detail.get("document_id"),
        "chunk_id": detail.get("chunk_id"),
        "filename": detail.get("filename"),
        "flags": detail.get("flags", []),
        "message": detail.get("message", ""),
        "recommended_action": _recommended_action(item_type),
    }


def _recommended_action(item_type: str) -> str:
    if item_type == "image_only_pdf":
        return (
            "Run OCR/hybrid parsing for this PDF, or exclude it from RAG readiness scoring "
            "until an OCR backend is configured."
        )
    if item_type == "parse_warning":
        return "Inspect parser output and rerun with the appropriate parser or OCR configuration."
    if item_type == "parser_fallback":
        return "Verify OpenDataLoader runtime and compare fallback output before accepting."
    if item_type == "sensitive_chunk":
        return "Review the chunk; redact true positives or add a narrow allowlist entry for false positives."
    return "Review and either accept, remediate, or document the risk."


def _stable_id(detail: dict) -> str:
    raw = "|".join(
        str(detail.get(key, ""))
        for key in ("type", "severity", "document_id", "chunk_id", "filename", "message")
    )
    return "rev_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
