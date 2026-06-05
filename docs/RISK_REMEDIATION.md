# Risk Remediation

CleanRAG reports risks as review items. The goal is to make every remaining risk actionable and auditable.

## Review Queue

Every run exports:

```text
review_items.jsonl
review_items.md
```

Review items are generated from risk details and include:

- stable item id.
- type.
- severity.
- target file or chunk.
- message.
- recommended action.

## Image-Only Or Scanned PDFs

Default behavior:

```text
PDF preflight detects image-only pages
-> normal text extraction is skipped
-> report marks OCR/hybrid required
```

This avoids long-running default extraction on scanned PDFs such as `数据清洗 (黑马程序员).pdf`.

When OpenDataLoader hybrid OCR is available, run with:

```powershell
$env:CLEANRAG_JAVA_HOME = "C:\Program Files\Java\jdk-11.0.24"
$env:CLEANRAG_FORCE_IMAGE_PDF_PARSING = "1"
$env:CLEANRAG_OPENDATALOADER_HYBRID = "docling-fast"
$env:CLEANRAG_OPENDATALOADER_HYBRID_MODE = "full"
.\.venv\Scripts\python.exe -m cleanrag run <input_dir> --out <output_dir>
```

Without a running hybrid/OCR backend, image-only PDFs remain a high-severity review item.

When another OCR adapter is available, configure its adapter bridge or module dependency instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ocr]"
.\.venv\Scripts\python.exe scripts\paddleocr_pdf_bridge.py --check-only
```

After those dependencies are installed, CleanRAG auto-uses `scripts/paddleocr_pdf_bridge.py`. Use `CLEANRAG_PADDLEOCR_COMMAND` only to override the command, language, DPI, or wrapper script.

Current Windows CPU-safe defaults are:

```powershell
$env:CLEANRAG_PADDLEOCR_DPI = "30"
$env:CLEANRAG_PADDLEOCR_TEXT_DET_LIMIT_SIDE_LEN = "320"
$env:CLEANRAG_PADDLEOCR_MODEL_SOURCE = "aistudio"
$env:CLEANRAG_PADDLEOCR_MAX_PAGES = "1"
$env:CLEANRAG_PADDLEOCR_START_PAGE = "1"
$env:CLEANRAG_PADDLEOCR_END_PAGE = "20"
$env:CLEANRAG_PADDLEOCR_CHECKPOINT_EVERY = "1"
$env:CLEANRAG_PADDLEOCR_MIN_CONFIDENCE = "0.5"
$env:CLEANRAG_PADDLEOCR_WINDOW_SIZE = "20"
$env:CLEANRAG_PADDLEOCR_MAX_WINDOWS = "1"
$env:CLEANRAG_PADDLEOCR_WINDOW_CACHE_DIR = ".tmp/paddleocr-window-cache/data-cleaning-book"
$env:CLEANRAG_PADDLEOCR_REUSE_EXISTING_WINDOWS = "1"
$env:CLEANRAG_ADAPTER_COMMAND_TIMEOUT = "3600"
```

`CLEANRAG_PADDLEOCR_MAX_PAGES` is only for smoke tests or sampling. Unset it for full-document OCR.

For long scanned books, prefer page-window runs while tuning CPU-safe settings, then run the whole document:

```powershell
$env:CLEANRAG_PADDLEOCR_START_PAGE = "1"
$env:CLEANRAG_PADDLEOCR_END_PAGE = "20"
.\.venv\Scripts\python.exe -m cleanrag run <input_dir> --out <output_dir>
```

The PaddleOCR bridge checkpoints JSON/Markdown/text output after each processed page. If the OCR subprocess exits non-zero after producing text, CleanRAG recovers that partial output and emits review items:

- `partial_pdf_ocr` when the OCR output covers only a subset of source pages or skipped pages exist.
- `low_confidence_ocr` when OCR elements fall below the configured confidence threshold.

Treat those as unresolved acceptance risks. Do not accept sampled OCR output for production RAG datasets until the run processes the full source page count and low-confidence lines are reviewed.

For long PDFs, use the windowed bridge before attempting full-document acceptance:

```powershell
$env:CLEANRAG_PADDLEOCR_WINDOW_SIZE = "20"
$env:CLEANRAG_PADDLEOCR_MAX_WINDOWS = "1" # smoke test only
.\.venv\Scripts\python.exe -m cleanrag run <input_dir> --out <output_dir>
```

After smoke settings are stable, remove `CLEANRAG_PADDLEOCR_MAX_PAGES`, `CLEANRAG_PADDLEOCR_MAX_WINDOWS`, `CLEANRAG_PADDLEOCR_START_PAGE`, and `CLEANRAG_PADDLEOCR_END_PAGE` for a full run. The wrapper will merge window outputs into one `paddleocr.json` payload while preserving page numbers, bounding boxes, confidence, skipped pages, and failed window metadata.

Use a stable cache directory for long runs:

```powershell
$env:CLEANRAG_PADDLEOCR_WINDOW_CACHE_DIR = ".tmp/paddleocr-window-cache/data-cleaning-book"
$env:CLEANRAG_PADDLEOCR_REUSE_EXISTING_WINDOWS = "1"
```

If a full run is interrupted, rerun the same command. Existing window folders with `paddleocr.json` are reused, and only missing windows are executed again. Set `CLEANRAG_PADDLEOCR_REUSE_EXISTING_WINDOWS=0` only when you intentionally want to recompute every window.

The generic adapter timeout defaults to 300 seconds. A 10-page calibration on this Windows CPU setup took about 306 seconds with `WINDOW_SIZE=5`, so full-document runs should explicitly raise `CLEANRAG_ADAPTER_COMMAND_TIMEOUT`.

`quality_report.json` and `quality_report.md` include `pdf_workflow.adapter_results` so skipped adapters and failed adapters are auditable without treating every optional missing dependency as a data-quality risk.

## Sensitive False Positives

Use a narrow allowlist for known benchmark/example content.

Example `allowlist.json`:

```json
{
  "sensitive_text": ["support@example.com"],
  "sensitive_patterns": ["@example\\.com"],
  "chunk_ids": [],
  "document_ids": []
}
```

Run:

```powershell
.\.venv\Scripts\python.exe -m cleanrag run tests/fixtures/input --out .tmp/fixture --dataset-id fixture --allowlist allowlist.json
```

Prefer narrow entries:

- exact text before regex.
- chunk id before document id.
- document id only for benchmark/demo material.

## Parser Fallback

Parser fallback means the preferred adapter did not produce output and another parser was used. Review fallback output before accepting.

Expected healthy digital PDF path with the current local setup:

```text
opendataloader_documents > 0
fallback_documents = 0
pdf_adapter_failures = 0
```
