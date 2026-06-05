# AI Data Readiness Platform

This repository is the product and implementation workspace for an AI data readiness platform. The first executable product is **CleanRAG**, a focused MVP for turning messy enterprise documents into RAG-ready, auditable, quality-scored datasets.

## Current Decision

Start narrow, build a reusable core, then expand.

```text
Narrow entry: RAG document dataset readiness
Reusable core: DocumentIR + rules + quality scoring + traceability + acceptance reports
Future platform: high-quality dataset factory + compliance packs + CleanOps
```

The first milestone is not a generic data governance platform. It is a product that helps teams clean PDF/Markdown/HTML knowledge-base documents, export RAG-ready data packages, and prove the improvement through reports.

## First Product: CleanRAG

CleanRAG processes enterprise documents through:

```text
Import -> Parse -> DocumentIR -> Clean -> Chunk -> Score -> Review -> Export -> Report
```

MVP capabilities:

- Batch import for PDF, Markdown, and HTML.
- Parser adapter layer with a unified `DocumentIR`.
- Header, footer, page number, watermark, and repeated paragraph cleanup.
- Heading hierarchy, table, and source-location preservation.
- Chunking and chunk-level quality scoring.
- Basic sensitive information detection.
- RAG-ready Markdown/JSONL export.
- Dataset card and acceptance report generation.

PDF workflow:

```text
PDF preflight
  -> digital/mixed workflow: OpenDataLoader, MinerU, Docling, Unstructured, DeepDoc/deepdoctection, PyMuPDF fallback
  -> scanned workflow: PaddleOCR, Textract, optional OCR/layout command adapters
  -> adapter metadata + OCR-needed risk when no OCR adapter is configured
```

Every PDF technology is represented as an independent adapter. The current tested in-process adapters are:

| Adapter | Role | Runtime behavior |
|---|---|---|
| OpenDataLoader | digital-primary | Uses `opendataloader_pdf.convert` when module and Java 11+ are available. |
| PyMuPDF | fallback/preflight | Profiles PDF type and extracts text blocks when higher-fidelity adapters are unavailable. |
| Docling | digital-primary | Uses `docling.document_converter` when installed. |
| Unstructured | digital-primary | Uses `unstructured.partition.pdf` when installed. |
| Textract | OCR | Uses `textract.process` when installed. |
| MinerU | digital-primary | Command bridge via `CLEANRAG_MINERU_COMMAND`. |
| DeepDoc | vision-layout | Command bridge via `CLEANRAG_DEEPDOC_COMMAND`. |
| deepdoctection | vision-layout | Command bridge via `CLEANRAG_DEEPDOCTECTION_COMMAND`. |
| PaddleOCR | OCR | Command bridge via `scripts/paddleocr_pdf_bridge.py`. |

Command bridge values are JSON arrays, not shell strings. Use `{input}` and `{output}` placeholders so adapters can run safely and read JSON/Markdown/text output from the generated output directory.

OpenDataLoader is optional but preferred for the current local digital-PDF path. Install it with:

```powershell
python -m pip install -e ".[opendataloader]"
```

It requires Java 11+ on `PATH`. Image-only/scanned PDFs require PaddleOCR, Textract, OpenDataLoader hybrid OCR, or another configured OCR backend.

On machines with multiple JDKs, point CleanRAG at Java 11 without changing the global shell:

```powershell
$env:CLEANRAG_JAVA_HOME = "C:\Program Files\Java\jdk-11.0.24"
```

By default, image-only PDFs are detected in a fast preflight and reported as `OCR/hybrid required` instead of running slow text extraction. To force OpenDataLoader hybrid handling for scanned PDFs:

```powershell
$env:CLEANRAG_FORCE_IMAGE_PDF_PARSING = "1"
$env:CLEANRAG_OPENDATALOADER_HYBRID = "docling-fast"
$env:CLEANRAG_OPENDATALOADER_HYBRID_MODE = "full"
```

To run every available adapter instead of stopping at the first successful parse:

```powershell
$env:CLEANRAG_PDF_RUN_ALL_AVAILABLE = "1"
```

To enable the local PaddleOCR bridge for scanned PDFs:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ocr]"
.\.venv\Scripts\python.exe scripts\paddleocr_pdf_bridge.py --check-only
```

When `paddleocr`, `paddlepaddle`, and PyMuPDF are installed, CleanRAG can auto-use the built-in bridge. Set `CLEANRAG_PADDLEOCR_COMMAND` only when you want to override the command:

```powershell
$env:CLEANRAG_PADDLEOCR_DPI = "30"
$env:CLEANRAG_PADDLEOCR_TEXT_DET_LIMIT_SIDE_LEN = "320"
$env:CLEANRAG_PADDLEOCR_MODEL_SOURCE = "aistudio"
$env:CLEANRAG_PADDLEOCR_MAX_PAGES = "1"  # optional smoke-test limiter; creates partial OCR risk
$env:CLEANRAG_PADDLEOCR_START_PAGE = "1" # optional 1-based range start
$env:CLEANRAG_PADDLEOCR_END_PAGE = "20"  # optional 1-based range end
$env:CLEANRAG_PADDLEOCR_CHECKPOINT_EVERY = "1"
$env:CLEANRAG_PADDLEOCR_MIN_CONFIDENCE = "0.5"
$env:CLEANRAG_PADDLEOCR_WINDOW_SIZE = "20" # optional long-PDF mode
$env:CLEANRAG_PADDLEOCR_MAX_WINDOWS = "1"  # optional window-mode smoke limiter
$env:CLEANRAG_PADDLEOCR_WINDOW_CACHE_DIR = ".tmp/paddleocr-window-cache/data-cleaning-book"
$env:CLEANRAG_PADDLEOCR_REUSE_EXISTING_WINDOWS = "1"
$env:CLEANRAG_ADAPTER_COMMAND_TIMEOUT = "3600"
$env:CLEANRAG_PADDLEOCR_COMMAND = '["./.venv/Scripts/python.exe", "scripts/paddleocr_pdf_bridge.py", "--input", "{input}", "--output", "{output}", "--lang", "ch", "--dpi", "30", "--text-det-limit-side-len", "320", "--model-source", "aistudio"]'
```

The built-in PaddleOCR bridge writes `paddleocr.json`, `paddleocr.md`, and `paddleocr.txt` after every processed page by default. If OCR stops mid-run, CleanRAG can recover the partial adapter output and marks it as a review risk instead of silently discarding recognized pages. Full acceptance still requires removing smoke-test/range limits and resolving `partial_pdf_ocr` plus `low_confidence_ocr` review items.

For long scanned books, set `CLEANRAG_PADDLEOCR_WINDOW_SIZE` instead of overriding the full command. CleanRAG will call `scripts/paddleocr_windowed_pdf_bridge.py`, run the single-page/range bridge in smaller subprocess windows, and merge all window outputs into the same CleanRAG adapter JSON contract. Window outputs are cached by default under `.tmp/paddleocr-window-cache`; set `CLEANRAG_PADDLEOCR_WINDOW_CACHE_DIR` when you want a stable resume location for a specific source PDF.

The generic adapter command timeout defaults to 300 seconds. For full-document OCR, set `CLEANRAG_ADAPTER_COMMAND_TIMEOUT` high enough for the batch. If the command is interrupted or times out, the window cache lets the next run reuse completed windows.

## Repository Docs

- [MVP PRD](docs/PRD-CleanRAG-MVP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [DocumentIR](docs/DOCUMENT_IR.md)
- [Quality Score Model](docs/QUALITY_SCORE_MODEL.md)
- [Rule Engine Spec](docs/RULE_ENGINE_SPEC.md)
- [RAG Evaluation Plan](docs/RAG_EVALUATION_PLAN.md)
- [Dataset Card Template](docs/DATASET_CARD_TEMPLATE.md)
- [Acceptance Report Template](docs/ACCEPTANCE_REPORT_TEMPLATE.md)
- [Roadmap](docs/ROADMAP.md)
- [Risk Remediation](docs/RISK_REMEDIATION.md)
- [Extensibility Analysis](docs/AI%20Data%20Readiness%20Platform%20可扩展与优化分析.md)

## Implementation Order

1. Define the data contracts and report templates.
2. Build a CLI prototype for document import, parsing, cleanup, scoring, and export.
3. Add benchmark fixtures and regression tests.
4. Add a lightweight web console only after the CLI flow proves value.

## Non-Goals For The MVP

- Full structured database quality platform.
- Full visual workflow builder.
- Full annotation platform.
- Data exchange marketplace.
- Agent CleanOps.
- Deep integrations with every RAG platform.

## Source Material

Raw PDFs and long exported research conversations are kept local and ignored by git. Curated project decisions and specs are tracked.
