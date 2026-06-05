# Architecture

## Architecture Principle

CleanRAG should not be coupled to one PDF parser or one RAG platform. The reusable core is:

```text
DocumentIR + Rule Engine + Quality Scoring + Trace Events + Export Contracts
```

## System Flow

```text
Input Documents
  -> Importer
  -> Parser Adapter
  -> DocumentIR Store
  -> Rule Engine
  -> Cleaning Event Store
  -> Chunker
  -> Quality Scorer
  -> Review Queue
  -> Exporter
  -> Reports
```

## Modules

| Module | Responsibility |
|---|---|
| Importer | Discover input files, compute source hashes, create dataset batches. |
| Parser Adapter | Convert parser-specific output into DocumentIR. |
| DocumentIR Store | Store normalized documents, pages, elements, tables, images, and warnings. |
| Rule Engine | Apply deterministic and configurable cleaning rules. |
| Cleaning Event Store | Record every mutation, exclusion, warning, and review action. |
| Chunker | Generate RAG-ready chunks with source mapping. |
| Quality Scorer | Compute document, chunk, and dataset-level quality metrics. |
| Review Queue | Surface low-confidence or high-risk decisions. |
| Exporter | Produce Markdown, JSONL, and metadata packages. |
| Report Generator | Produce dataset cards, quality reports, and acceptance reports. |

## Data Boundaries

```text
Raw source files: immutable
DocumentIR: normalized parser output
Cleaned view: rule-filtered projection of DocumentIR
Chunks: RAG-ready derived records
Reports: evidence-backed summaries
```

Raw source files must not be modified. Cleanup operates on derived records and export views.

## Storage Strategy For MVP

The MVP can start with filesystem-backed JSON/JSONL artifacts:

```text
.cleanrag/
  datasets/
    <dataset_id>/
      source/
      ir/
      events/
      exports/
      reports/
```

This keeps the first implementation simple while preserving contracts for a future database-backed service.

## Parser Adapter Contract

Every parser adapter returns:

```text
DocumentIR
parse_warnings[]
parser_metadata
```

Adapter selection should be configurable. Parser fallback should be recorded in `parse_warnings` and report metadata.

## PDF Adapter Workflow

PDF handling starts with a lightweight profile pass:

```text
PDF
  -> profile: digital | mixed | scanned | unknown
  -> select adapter workflow
  -> run available adapters in priority order
  -> normalize to DocumentIR
  -> record adapter_results in pdf_workflow metadata
```

Default digital/mixed workflow:

```text
OpenDataLoader
  -> MinerU command bridge when configured
  -> Docling
  -> Unstructured
  -> DeepDoc / deepdoctection command bridges when configured
  -> PyMuPDF fallback
```

Default scanned workflow:

```text
PaddleOCR command bridge
  -> Textract
  -> OCR-capable layout adapters when configured
  -> parser warning / OCR-needed risk
```

Adapters are independent and capability-scoped:

| Adapter | Role | Activation |
|---|---|---|
| OpenDataLoader | digital-primary | `opendataloader_pdf` module plus Java 11+. |
| PyMuPDF | preflight/fallback | `fitz` module. |
| Docling | digital-primary | `docling.document_converter` module. |
| Unstructured | digital-primary | `unstructured.partition.pdf` module. |
| Textract | OCR | `textract` module. |
| MinerU | digital-primary | `CLEANRAG_MINERU_COMMAND` JSON command bridge. |
| DeepDoc | vision-layout | `CLEANRAG_DEEPDOC_COMMAND` JSON command bridge. |
| deepdoctection | vision-layout | `CLEANRAG_DEEPDOCTECTION_COMMAND` JSON command bridge. |
| PaddleOCR | OCR | `scripts/paddleocr_pdf_bridge.py` by default; `scripts/paddleocr_windowed_pdf_bridge.py` when `CLEANRAG_PADDLEOCR_WINDOW_SIZE` is set. |

Command bridge adapters use JSON command arrays rather than shell strings. The adapter creates a temporary output directory and reads the first supported JSON, Markdown, or text output back into DocumentIR. This keeps uncertain CLI/API surfaces isolated while preserving a stable CleanRAG contract.

CleanRAG adapter JSON uses `schema_version=cleanrag.adapter_output.v1` with `pages[]`, `elements[]`, optional `tables[]`, `images[]`, `warnings[]`, and `metadata`. This lets OCR/layout bridges preserve page number, bbox, confidence, and adapter-specific metadata instead of collapsing to plain text.

For long scanned PDFs, the windowed PaddleOCR bridge runs smaller page ranges in separate subprocesses and merges their CleanRAG adapter payloads. This reduces the blast radius of PaddleOCR memory/runtime failures while preserving the same adapter contract for downstream `DocumentIR` normalization.

OpenDataLoader is currently the preferred tested local digital-PDF adapter because it outputs RAG-oriented Markdown and JSON with layout metadata. It is optional in this repo so the CLI can still run in constrained local environments. Runtime requirements are:

```text
pip install ".[opendataloader]"
Java 11+ on PATH
```

If the machine has multiple JDKs, set `CLEANRAG_JAVA_HOME` to a Java 11 installation. The adapter will use that value for the OpenDataLoader subprocess without requiring a global Java change.

Image-only or scanned PDFs must use PaddleOCR, Textract, OpenDataLoader hybrid OCR, or another OCR backend; local text extraction cannot recover text from image pages.

The MVP runs a fast PDF preflight before OpenDataLoader. If every page appears image-only, the default behavior is to skip normal text extraction and report `OCR/hybrid required`. Set `CLEANRAG_FORCE_IMAGE_PDF_PARSING=1` plus `CLEANRAG_OPENDATALOADER_HYBRID` when an OCR backend is available.

Set `CLEANRAG_PDF_RUN_ALL_AVAILABLE=1` to run every available adapter and retain all results in `pdf_workflow.adapter_results`. The default stops at the first successful parse to keep batch runs predictable.

## Extensibility Points

| Extension | Contract |
|---|---|
| New parser | Implement parser adapter -> DocumentIR. |
| New cleanup rule | Implement rule condition and action. |
| New quality metric | Add metric definition and score contribution. |
| New exporter | Read cleaned view and chunks. |
| New RAG integration | Consume standard output package. |
| New industry pack | Provide rules, thresholds, report wording, and benchmark questions. |

## Security Defaults

- Raw files are immutable.
- External LLM calls are off by default.
- Every derived record keeps source hash and trace mapping.
- Sensitive hits are exported as findings; masking policy is configurable.
- Reports must list unverified or low-confidence parser decisions.

## Future Platform Evolution

```text
CLI prototype
  -> local service + Web console
  -> multi-user project platform
  -> private deployment
  -> industry packs and compliance packs
```
