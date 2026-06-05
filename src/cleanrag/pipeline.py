from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .allowlist import load_allowlist
from .chunker import build_chunks
from .models import Chunk, CleaningEvent, DocumentIR
from .parsers import discover_files, parse_file
from .reports import write_reports
from .review import build_review_items, write_review_items_markdown
from .rules import apply_cleaning_rules
from .scoring import score_dataset
from .storage import write_json, write_jsonl


def run_pipeline(
    input_dir: Path,
    output_dir: Path,
    dataset_id: str | None = None,
    allowlist_path: Path | None = None,
) -> dict:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    dataset_id = dataset_id or input_dir.name.replace(" ", "_").lower()

    files = discover_files(input_dir)
    documents: list[DocumentIR] = []
    events: list[CleaningEvent] = []
    chunks: list[Chunk] = []
    allowlist = load_allowlist(allowlist_path)

    for index, path in enumerate(files, start=1):
        document = parse_file(path, dataset_id, index)
        documents.append(document)
        document_events, excluded = apply_cleaning_rules(document)
        events.extend(document_events)
        chunks.extend(build_chunks(document, excluded, allowlist=allowlist))

    quality = score_dataset(dataset_id, documents, events, chunks)
    quality["review_items"] = build_review_items(quality.get("risk_details", []))
    quality["summary"]["review_items"] = len(quality["review_items"])
    _write_outputs(output_dir, dataset_id, documents, events, chunks, quality)
    return quality


def _write_outputs(
    output_dir: Path,
    dataset_id: str,
    documents: list[DocumentIR],
    events: list[CleaningEvent],
    chunks: list[Chunk],
    quality: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "dataset.json", {"dataset_id": dataset_id, **quality["summary"]})
    write_jsonl(output_dir / "documents.jsonl", documents)
    write_jsonl(
        output_dir / "elements.jsonl",
        (element for document in documents for element in document.elements),
    )
    write_jsonl(output_dir / "chunks.jsonl", chunks)
    write_jsonl(output_dir / "cleaning_events.jsonl", events)
    write_jsonl(output_dir / "review_items.jsonl", quality.get("review_items", []))
    write_json(output_dir / "quality_report.json", quality)
    write_review_items_markdown(output_dir / "review_items.md", quality.get("review_items", []))
    write_reports(output_dir, dataset_id, documents, events, chunks, quality)


def summary_line(quality: dict) -> str:
    summary = quality["summary"]
    scores = quality["scores"]
    return (
        f"dataset={quality['dataset_id']} "
        f"documents={summary['documents']} chunks={summary['chunks']} "
        f"score_before={scores['before']} score_after={scores['after']}"
    )
