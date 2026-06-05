from __future__ import annotations

from collections import Counter
from pathlib import Path

from .models import Chunk, CleaningEvent, DocumentIR


def write_reports(
    output_dir: Path,
    dataset_id: str,
    documents: list[DocumentIR],
    events: list[CleaningEvent],
    chunks: list[Chunk],
    quality: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "quality_report.md").write_text(
        quality_report(dataset_id, quality, events),
        encoding="utf-8",
    )
    (output_dir / "dataset_card.md").write_text(
        dataset_card(dataset_id, documents, events, chunks, quality),
        encoding="utf-8",
    )
    (output_dir / "acceptance_report.md").write_text(
        acceptance_report(dataset_id, documents, events, chunks, quality),
        encoding="utf-8",
    )


def quality_report(dataset_id: str, quality: dict, events: list[CleaningEvent]) -> str:
    scores = quality["scores"]
    rule_counts = Counter(event.rule_id for event in events)
    lines = [
        f"# Quality Report: {dataset_id}",
        "",
        "## Score Summary",
        "",
        f"- Before score: {scores['before']}",
        f"- After score: {scores['after']}",
        f"- Parse quality: {scores['parse_quality']}",
        f"- Noise control: {scores['noise_control']}",
        f"- Chunk quality: {scores['chunk_quality']}",
        f"- Source traceability: {scores['source_traceability']}",
        f"- Safety risk: {scores['safety_risk']}",
        f"- OpenDataLoader documents: {quality['summary'].get('opendataloader_documents', 0)}",
        f"- Fallback parser documents: {quality['summary'].get('fallback_documents', 0)}",
        f"- Image-only documents: {quality['summary'].get('image_only_documents', 0)}",
        f"- PDF workflow documents: {quality['summary'].get('pdf_workflow_documents', 0)}",
        f"- PDF adapter successes: {quality['summary'].get('pdf_adapter_successes', 0)}",
        f"- PDF adapter failures: {quality['summary'].get('pdf_adapter_failures', 0)}",
        f"- PDF adapter skips: {quality['summary'].get('pdf_adapter_skips', 0)}",
        f"- Review items: {quality['summary'].get('review_items', 0)}",
        "",
        "## Rule Hits",
        "",
    ]
    if rule_counts:
        lines.extend(f"- {rule}: {count}" for rule, count in sorted(rule_counts.items()))
    else:
        lines.append("- No cleaning rules matched.")
    lines.extend(["", "## Risks", ""])
    risks = quality.get("risks", [])
    lines.extend(f"- {risk}" for risk in risks) if risks else lines.append("- No known risks.")
    lines.extend(["", "## Risk Details", ""])
    details = quality.get("risk_details", [])
    if details:
        lines.extend(_format_risk_detail(detail) for detail in details[:50])
        if len(details) > 50:
            lines.append(f"- {len(details) - 50} additional risk detail(s) omitted from markdown report.")
    else:
        lines.append("- No detailed risks.")
    lines.extend(["", "## PDF Adapter Workflow", ""])
    lines.extend(_pdf_adapter_lines(quality))
    return "\n".join(lines) + "\n"


def dataset_card(
    dataset_id: str,
    documents: list[DocumentIR],
    events: list[CleaningEvent],
    chunks: list[Chunk],
    quality: dict,
) -> str:
    summary = quality["summary"]
    return "\n".join(
        [
            f"# Dataset Card: {dataset_id}",
            "",
            "## Basic Information",
            "",
            f"- Dataset id: {dataset_id}",
            "- Intended use: RAG document dataset readiness pilot.",
            "- Not intended for: model training or legal compliance certification without review.",
            "",
            "## Source Data",
            "",
            f"- Documents: {summary['documents']}",
            f"- Parsed elements: {summary['elements']}",
            f"- Generated chunks: {summary['chunks']}",
            f"- OpenDataLoader parsed documents: {summary.get('opendataloader_documents', 0)}",
            f"- Fallback parser documents: {summary.get('fallback_documents', 0)}",
            f"- Image-only documents: {summary.get('image_only_documents', 0)}",
            f"- PDF workflow documents: {summary.get('pdf_workflow_documents', 0)}",
            f"- PDF OCR-required documents: {summary.get('pdf_ocr_required_documents', 0)}",
            "",
            "## Processing",
            "",
            "Import -> Parse -> DocumentIR -> Clean -> Chunk -> Score -> Export -> Report",
            "",
            "## Quality",
            "",
            f"- After score: {quality['scores']['after']}",
            f"- Excluded elements: {len(events)}",
            f"- Chunks with sensitive flags: {sum(1 for chunk in chunks if chunk.flags)}",
            f"- Review items: {quality['summary'].get('review_items', 0)}",
            "",
            "## Limitations",
            "",
            "- PDF parsing uses optional PyMuPDF when available; otherwise it records parser warnings.",
            "- PDF workflows select independent adapters by PDF profile: digital, mixed, scanned, or unknown.",
            "- OpenDataLoader is the preferred tested digital PDF adapter when installed with Java 11+ available.",
            "- Image-only PDFs require PaddleOCR, Textract, OpenDataLoader hybrid, or another configured OCR backend.",
            "- RAG answer evaluation requires a customer question set.",
        ]
    ) + "\n"


def acceptance_report(
    dataset_id: str,
    documents: list[DocumentIR],
    events: list[CleaningEvent],
    chunks: list[Chunk],
    quality: dict,
) -> str:
    verdict = "accepted with remediation" if quality.get("risks") else "accepted"
    return "\n".join(
        [
            f"# Acceptance Report: {dataset_id}",
            "",
            "## Executive Result",
            "",
            f"- Before quality score: {quality['scores']['before']}",
            f"- After quality score: {quality['scores']['after']}",
            f"- Recommended verdict: {verdict}",
            "",
            "## Scope",
            "",
            f"- Documents: {len(documents)}",
            f"- Cleaning events: {len(events)}",
            f"- Generated chunks: {len(chunks)}",
            f"- OpenDataLoader parsed documents: {quality['summary'].get('opendataloader_documents', 0)}",
            f"- Fallback parser documents: {quality['summary'].get('fallback_documents', 0)}",
            f"- Image-only documents: {quality['summary'].get('image_only_documents', 0)}",
            f"- PDF workflow documents: {quality['summary'].get('pdf_workflow_documents', 0)}",
            f"- PDF adapter failures: {quality['summary'].get('pdf_adapter_failures', 0)}",
            f"- Review items: {quality['summary'].get('review_items', 0)}",
            "",
            "## Traceability",
            "",
            f"- Chunks with source mapping: {sum(1 for chunk in chunks if chunk.element_ids)}",
            "- Raw source files were not modified.",
            "",
            "## Remaining Risks",
            "",
            *[f"- {risk}" for risk in quality.get("risks", [])],
            "",
            "## Risk Details",
            "",
            *[_format_risk_detail(detail) for detail in quality.get("risk_details", [])[:50]],
        ]
    ) + "\n"


def _format_risk_detail(detail: dict) -> str:
    location = detail.get("filename") or detail.get("chunk_id") or detail.get("document_id") or "dataset"
    message = detail.get("message", "")
    severity = detail.get("severity", "unknown")
    risk_type = detail.get("type", "risk")
    extra = ""
    if detail.get("flags"):
        extra = f" flags={','.join(detail['flags'])}"
    return f"- [{severity}] {risk_type} @ {location}: {message}{extra}"


def _pdf_adapter_lines(quality: dict) -> list[str]:
    summary = quality.get("pdf_adapter_summary", {})
    documents = summary.get("documents", [])
    if not documents:
        return ["- No PDF workflow documents."]

    lines: list[str] = []
    kind_counts = summary.get("pdf_kind_counts", {})
    status_counts = summary.get("status_counts", {})
    if kind_counts:
        lines.append("- PDF kinds: " + ", ".join(f"{key}={value}" for key, value in sorted(kind_counts.items())))
    if status_counts:
        lines.append(
            "- Adapter statuses: "
            + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items()))
        )
    for item in documents[:20]:
        results = item.get("adapter_results", [])
        compact = ", ".join(
            f"{result.get('adapter_name')}:{result.get('status')}"
            for result in results[:8]
        )
        lines.append(
            f"- {item.get('filename')}: kind={item.get('kind')} parser={item.get('parser')} adapters={compact}"
        )
    if len(documents) > 20:
        lines.append(f"- {len(documents) - 20} additional PDF workflow document(s) omitted.")
    return lines
