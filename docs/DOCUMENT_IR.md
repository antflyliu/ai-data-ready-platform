# DocumentIR Specification

## Purpose

`DocumentIR` is the normalized intermediate representation for documents. It decouples parser-specific output from cleaning, chunking, scoring, export, and reporting.

## Top-Level Shape

```json
{
  "schema_version": "0.1",
  "document_id": "doc_001",
  "dataset_id": "ds_001",
  "source": {},
  "pages": [],
  "elements": [],
  "tables": [],
  "images": [],
  "parse_warnings": [],
  "metadata": {}
}
```

## Source

```json
{
  "path": "source/manual.pdf",
  "filename": "manual.pdf",
  "mime_type": "application/pdf",
  "sha256": "...",
  "size_bytes": 123456,
  "imported_at": "2026-06-04T00:00:00Z"
}
```

## Page

```json
{
  "page_id": "page_001",
  "page_number": 1,
  "width": 595.0,
  "height": 842.0,
  "unit": "pt"
}
```

## Element

```json
{
  "element_id": "el_001",
  "type": "paragraph",
  "text": "Example text",
  "markdown": "Example text",
  "page_number": 1,
  "bbox": [72.0, 120.0, 520.0, 160.0],
  "title_path": ["Chapter 1", "Section 1.1"],
  "confidence": 0.97,
  "source_parser": "adapter_name",
  "metadata": {}
}
```

## Element Types

MVP element types:

```text
title
paragraph
list
table
image
header
footer
page_number
watermark
formula
unknown
```

## Table

```json
{
  "table_id": "tbl_001",
  "element_id": "el_010",
  "page_number": 2,
  "bbox": [50.0, 100.0, 550.0, 300.0],
  "headers": ["Name", "Value"],
  "rows": [["A", "1"], ["B", "2"]],
  "markdown": "| Name | Value |\\n|---|---|\\n| A | 1 |",
  "confidence": 0.82
}
```

## Parse Warning

```json
{
  "warning_id": "warn_001",
  "severity": "medium",
  "scope": "page",
  "page_number": 3,
  "message": "Low confidence table extraction",
  "source_parser": "adapter_name"
}
```

## Chunk

Chunks are derived records, not part of raw `DocumentIR`, but they must reference it.

```json
{
  "chunk_id": "chk_001",
  "document_id": "doc_001",
  "element_ids": ["el_001", "el_002"],
  "text": "Chunk text",
  "markdown": "Chunk markdown",
  "title_path": ["Chapter 1"],
  "page_range": [1, 2],
  "source_locations": [
    {
      "page_number": 1,
      "bbox": [72.0, 120.0, 520.0, 160.0]
    }
  ],
  "quality_score": 0.86,
  "flags": []
}
```

## Cleaning Event

Cleaning events record changes or projections over `DocumentIR`.

```json
{
  "event_id": "evt_001",
  "dataset_id": "ds_001",
  "document_id": "doc_001",
  "element_id": "el_003",
  "rule_id": "remove_repeated_header",
  "rule_version": 1,
  "action": "exclude_from_export",
  "before_snapshot": {},
  "after_snapshot": {},
  "confidence": 0.91,
  "review_status": "auto_accepted",
  "operator": "system",
  "created_at": "2026-06-04T00:00:00Z"
}
```

## Versioning Rules

- Increment `schema_version` when persisted fields change.
- Parser adapters may add metadata, but core fields must remain stable.
- Reports must include `schema_version` and parser metadata.
