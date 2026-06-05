# PRD: CleanRAG MVP

## Product Positioning

CleanRAG is an enterprise RAG document dataset readiness tool. It converts messy documents into clean, traceable, quality-scored RAG datasets with evidence reports.

## Target Users

| User | Need |
|---|---|
| RAG integration team | Prepare customer documents for vector database ingestion. |
| Enterprise knowledge-base owner | Know whether documents are clean enough for AI search and QA. |
| Solution architect | Prove document cleanup improves RAG retrieval and answer quality. |
| Compliance or security reviewer | Inspect sensitive hits, source lineage, and cleanup changes. |

## Problem

Enterprise RAG projects often fail because source documents contain noisy headers, footers, page numbers, repeated text, broken tables, bad chunk boundaries, and missing source references. Teams can parse documents, but they cannot easily prove whether the resulting dataset is usable, traceable, or safe.

## MVP Goal

Given a batch of documents, produce:

```text
RAG-ready dataset package
+ cleaning diff evidence
+ quality scores
+ source traceability
+ dataset card
+ acceptance report
```

## Supported Inputs

MVP:

- PDF.
- Markdown.
- HTML.

Deferred:

- Word.
- PPT.
- Excel.
- Image-only document batches.
- Database tables.

## Core Workflow

```text
1. Create dataset project
2. Import documents
3. Parse into DocumentIR
4. Run cleaning rules
5. Generate chunks
6. Score document and chunk quality
7. Flag review items
8. Export RAG-ready package
9. Generate dataset card and acceptance report
```

## MVP Features

| Feature | Description | Acceptance Criteria |
|---|---|---|
| Batch import | Import a document folder into one dataset project. | Supports at least PDF, Markdown, and HTML files. |
| Parser adapter | Normalize parser output into DocumentIR. | Each parsed element has type, page, text, source parser, and confidence where available. |
| Noise cleanup | Detect and exclude header, footer, page number, watermark, and repeated paragraph noise. | Every excluded element is linked to a rule and trace event. |
| Chunking | Generate RAG chunks with source mapping. | Every chunk stores document id, element ids, page range, title path, and quality score. |
| Quality scoring | Score documents, chunks, and dataset readiness. | Scores can be traced to concrete metrics and evidence. |
| Sensitive detection | Detect basic PII and sensitive keywords. | Hits include location, confidence, and review status. |
| Export | Export Markdown and JSONL packages. | Output includes documents, chunks, metadata, quality report, and dataset card. |
| Reporting | Generate acceptance report. | Report compares before/after cleanup and lists risks, metrics, and recommended next actions. |

## Review Queue Scope

MVP only supports exception review:

- Low-confidence cleaning decisions.
- Sensitive information hits.
- High-impact chunks with poor score.

Review actions:

- Accept.
- Revert.
- Mark false positive.
- Add allow rule.
- Add block rule.

## Output Package

```text
dataset.json
documents.jsonl
elements.jsonl
chunks.jsonl
cleaning_events.jsonl
quality_report.json
quality_report.md
dataset_card.md
acceptance_report.md
```

## Success Metrics

| Metric | MVP Target |
|---|---|
| Parse completion rate | >= 90% on benchmark documents |
| Source traceability rate | >= 95% chunks have source document and element mapping |
| Noise cleanup precision | >= 85% on manually labeled benchmark |
| Chunk quality pass rate | >= 80% chunks pass configured quality thresholds |
| Report generation | 100% datasets produce dataset card and acceptance report |

## Explicit Non-Goals

- Full data governance platform.
- SQL/database data quality.
- General-purpose annotation system.
- Full RAG application hosting.
- Automatic LLM-only cleanup without rules and evidence.
- Data marketplace or data exchange workflow.

## Open Decisions

| Decision | Default |
|---|---|
| First primary PDF parser | OpenDataLoader first, PyMuPDF fallback when OpenDataLoader is unavailable. |
| External LLM usage | Disabled by default; all sensitive customer data paths must support local-only mode. |
| Web UI timing | After CLI pipeline and reports are proven. |

## Known MVP Risks To Surface In Reports

- OpenDataLoader unavailable or Java version below 11.
- PDF fallback parser used instead of OpenDataLoader.
- Image-only or scanned PDFs requiring OCR/hybrid parsing.
- Sensitive detector hits that may be true positives or benchmark/example false positives.
- Low-confidence parser warnings.
