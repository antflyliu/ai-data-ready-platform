from __future__ import annotations

from collections import Counter
from typing import Any

from .models import Chunk, CleaningEvent, DocumentIR


def score_dataset(
    dataset_id: str,
    documents: list[DocumentIR],
    events: list[CleaningEvent],
    chunks: list[Chunk],
) -> dict:
    total_elements = sum(len(document.elements) for document in documents)
    parse_warnings = sum(len(document.parse_warnings) for document in documents)
    excluded_count = len(events)
    chunk_count = len(chunks)
    mapped_chunks = sum(1 for chunk in chunks if chunk.element_ids)
    quality_chunks = sum(1 for chunk in chunks if chunk.quality_score >= 0.7)
    sensitive_chunks = sum(1 for chunk in chunks if chunk.flags)
    image_only_documents = sum(1 for document in documents if document.metadata.get("image_only"))
    fallback_documents = sum(1 for document in documents if document.metadata.get("fallback_parser"))
    opendataloader_documents = sum(1 for document in documents if document.metadata.get("parser") == "opendataloader")
    partial_ocr_documents = sum(1 for document in documents if _partial_ocr_counts(document) is not None)
    low_confidence_ocr_documents = sum(1 for document in documents if _low_confidence_ocr_count(document) > 0)
    pdf_adapter_summary = _pdf_adapter_summary(documents)

    parse_quality = _clamp(100 if total_elements else 20)
    parse_quality = _clamp(parse_quality - parse_warnings * 15)
    noise_control = _clamp(100 if total_elements else 0)
    chunk_quality = _pct(quality_chunks, chunk_count)
    traceability = _pct(mapped_chunks, chunk_count)
    safety = _clamp(100 - sensitive_chunks * 10)
    rag_eval = 0

    weighted_after = round(
        parse_quality * 0.2
        + noise_control * 0.2
        + chunk_quality * 0.25
        + traceability * 0.2
        + safety * 0.1
        + rag_eval * 0.05,
        2,
    )
    before_score = _clamp(weighted_after - min(20, excluded_count * 2))

    return {
        "dataset_id": dataset_id,
        "summary": {
            "documents": len(documents),
            "elements": total_elements,
            "excluded_elements": excluded_count,
            "chunks": chunk_count,
            "parse_warnings": parse_warnings,
            "image_only_documents": image_only_documents,
            "fallback_documents": fallback_documents,
            "opendataloader_documents": opendataloader_documents,
            "partial_ocr_documents": partial_ocr_documents,
            "low_confidence_ocr_documents": low_confidence_ocr_documents,
            "pdf_workflow_documents": pdf_adapter_summary["workflow_documents"],
            "pdf_adapter_successes": pdf_adapter_summary["status_counts"].get("success", 0),
            "pdf_adapter_skips": pdf_adapter_summary["status_counts"].get("skipped", 0),
            "pdf_adapter_failures": pdf_adapter_summary["status_counts"].get("failed", 0),
            "pdf_ocr_required_documents": pdf_adapter_summary["ocr_required_documents"],
        },
        "scores": {
            "before": before_score,
            "after": weighted_after,
            "parse_quality": parse_quality,
            "noise_control": noise_control,
            "chunk_quality": chunk_quality,
            "source_traceability": traceability,
            "safety_risk": safety,
            "rag_evaluation": rag_eval,
        },
        "risks": _risks(
            parse_warnings,
            sensitive_chunks,
            chunk_count,
            mapped_chunks,
            image_only_documents,
            fallback_documents,
            partial_ocr_documents,
            low_confidence_ocr_documents,
        ),
        "risk_details": _risk_details(documents, chunks),
        "pdf_adapter_summary": pdf_adapter_summary,
    }


def _risk_details(documents: list[DocumentIR], chunks: list[Chunk]) -> list[dict]:
    details: list[dict] = []
    for document in documents:
        filename = document.source.filename
        if document.metadata.get("image_only"):
            details.append(
                {
                    "type": "image_only_pdf",
                    "severity": "high",
                    "document_id": document.document_id,
                    "filename": filename,
                    "message": "Document appears to be image-only/scanned and needs OCR/hybrid parsing.",
                }
            )
        if document.metadata.get("fallback_parser"):
            details.append(
                {
                    "type": "parser_fallback",
                    "severity": "medium",
                    "document_id": document.document_id,
                    "filename": filename,
                    "message": "OpenDataLoader did not run successfully; fallback parser output should be reviewed.",
                }
            )
        partial_counts = _partial_ocr_counts(document)
        if partial_counts is not None:
            processed, total = partial_counts
            details.append(
                {
                    "type": "partial_pdf_ocr",
                    "severity": "medium",
                    "document_id": document.document_id,
                    "filename": filename,
                    "message": f"OCR processed {processed}/{total} PDF page(s); run full-document OCR before accepting.",
                    "processed_pages": document.metadata.get("processed_pages"),
                    "skipped_pages": document.metadata.get("skipped_pages"),
                }
            )
        low_confidence_count = _low_confidence_ocr_count(document)
        if low_confidence_count:
            threshold = _float_metadata(document.metadata, "min_confidence", 0.5)
            details.append(
                {
                    "type": "low_confidence_ocr",
                    "severity": "medium",
                    "document_id": document.document_id,
                    "filename": filename,
                    "message": (
                        f"{low_confidence_count} OCR element(s) are below confidence threshold "
                        f"{threshold:.2f}; review the extracted text against the source page image."
                    ),
                    "threshold": threshold,
                    "low_confidence_element_count": low_confidence_count,
                }
            )
        for warning in document.parse_warnings:
            details.append(
                {
                    "type": "parse_warning",
                    "severity": warning.severity,
                    "document_id": document.document_id,
                    "filename": filename,
                    "message": warning.message,
                    "source_parser": warning.source_parser,
                }
            )

    for chunk in chunks:
        if chunk.flags:
            details.append(
                {
                    "type": "sensitive_chunk",
                    "severity": "medium",
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                    "flags": chunk.flags,
                    "message": "Chunk contains sensitive detector flags and needs review or whitelist handling.",
                }
            )
    return details


def _risks(
    parse_warnings: int,
    sensitive_chunks: int,
    chunk_count: int,
    mapped_chunks: int,
    image_only_documents: int,
    fallback_documents: int,
    partial_ocr_documents: int,
    low_confidence_ocr_documents: int,
) -> list[str]:
    risks: list[str] = []
    if image_only_documents:
        risks.append(f"{image_only_documents} image-only/scanned PDF document(s) require OCR/hybrid parsing.")
    if fallback_documents:
        risks.append(f"{fallback_documents} PDF document(s) used fallback parser instead of OpenDataLoader.")
    if partial_ocr_documents:
        risks.append(f"{partial_ocr_documents} PDF document(s) have partial OCR output.")
    if low_confidence_ocr_documents:
        risks.append(f"{low_confidence_ocr_documents} PDF document(s) contain low-confidence OCR text.")
    if parse_warnings:
        risks.append(f"{parse_warnings} parser warning(s) require review.")
    if sensitive_chunks:
        risks.append(f"{sensitive_chunks} chunk(s) contain sensitive flags.")
    if chunk_count and mapped_chunks < chunk_count:
        risks.append("Some chunks are missing source mapping.")
    if not chunk_count:
        risks.append("No chunks were generated.")
    return risks


def _partial_ocr_counts(document: DocumentIR) -> tuple[int, int] | None:
    total = _int_metadata(document.metadata, "source_page_count")
    if total is None:
        profile = document.metadata.get("pdf_profile")
        if isinstance(profile, dict):
            total = _int_metadata(profile, "page_count")
    processed = _int_metadata(document.metadata, "processed_page_count")
    processed_pages = document.metadata.get("processed_pages")
    if processed is None and isinstance(processed_pages, list):
        processed = len(processed_pages)
    partial_output = bool(document.metadata.get("partial_output"))
    if total is None or processed is None:
        return None if not partial_output else (processed or 0, total or 0)
    if partial_output or processed < total:
        return processed, total
    return None


def _low_confidence_ocr_count(document: DocumentIR) -> int:
    metadata_count = _int_metadata(document.metadata, "low_confidence_element_count")
    if metadata_count is not None:
        return metadata_count
    threshold = _float_metadata(document.metadata, "min_confidence", 0.5)
    return sum(
        1
        for element in document.elements
        if _is_ocr_parser(element.source_parser) and element.confidence < threshold
    )


def _is_ocr_parser(parser_name: str) -> bool:
    return parser_name.lower() in {"paddleocr", "textract", "ocr"}


def _int_metadata(metadata: dict[str, Any], key: str) -> int | None:
    try:
        return int(metadata[key])
    except (KeyError, TypeError, ValueError):
        return None


def _float_metadata(metadata: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(metadata[key])
    except (KeyError, TypeError, ValueError):
        return default


def _pdf_adapter_summary(documents: list[DocumentIR]) -> dict:
    status_counts: Counter[str] = Counter()
    adapter_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    workflow_documents = 0
    ocr_required_documents = 0
    document_summaries: list[dict] = []

    for document in documents:
        workflow = document.metadata.get("pdf_workflow")
        profile = document.metadata.get("pdf_profile") or {}
        if not workflow:
            continue
        workflow_documents += 1
        kind = str(profile.get("kind") or workflow.get("profile", {}).get("kind") or "unknown")
        kind_counts[kind] += 1
        if document.metadata.get("ocr_required"):
            ocr_required_documents += 1
        results = workflow.get("adapter_results", [])
        for result in results:
            status = str(result.get("status") or "unknown")
            adapter_name = str(result.get("adapter_name") or "unknown")
            status_counts[status] += 1
            adapter_counts[f"{adapter_name}:{status}"] += 1
        document_summaries.append(
            {
                "document_id": document.document_id,
                "filename": document.source.filename,
                "kind": kind,
                "parser": document.metadata.get("parser"),
                "selected_adapters": workflow.get("selected_adapters", []),
                "adapter_results": results,
            }
        )

    return {
        "workflow_documents": workflow_documents,
        "ocr_required_documents": ocr_required_documents,
        "status_counts": dict(status_counts),
        "adapter_counts": dict(adapter_counts),
        "pdf_kind_counts": dict(kind_counts),
        "documents": document_summaries,
    }


def _pct(part: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(part / total * 100, 2)


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)
