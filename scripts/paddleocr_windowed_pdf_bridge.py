from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cleanrag.adapter_output.v1"


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_page_count = _pdf_page_count(Path(args.input))
    selected_pages = _selected_pages(
        source_page_count=source_page_count,
        start_page=args.start_page,
        end_page=args.end_page,
        max_pages=args.max_pages,
        max_windows=args.max_windows,
        window_size=args.window_size,
    )
    window_results: list[dict[str, Any]] = []
    failed_windows: list[dict[str, Any]] = []
    work_dir = Path(args.work_dir) if args.work_dir else _default_work_dir(Path(args.input), args)
    work_dir.mkdir(parents=True, exist_ok=True)

    for window_index, (start_page, end_page) in enumerate(_windows(selected_pages, args.window_size), start=1):
        window_output = work_dir / f"pages_{start_page:04d}_{end_page:04d}"
        window_output.mkdir(parents=True, exist_ok=True)
        payload = _read_payload(window_output)
        if payload is not None and args.reuse_existing:
            window_results.append(payload)
            _write_payload(
                output_dir,
                merge_payloads(
                    input_name=Path(args.input).name,
                    source_page_count=source_page_count,
                    selected_pages=selected_pages,
                    window_size=args.window_size,
                    window_results=window_results,
                    failed_windows=failed_windows,
                    min_confidence=args.min_confidence,
                    work_dir=str(work_dir),
                ),
            )
            continue

        command = _bridge_command(args, window_output, start_page, end_page)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        payload = _read_payload(window_output)
        if payload is not None:
            window_results.append(payload)
        if completed.returncode != 0:
            failed_windows.append(
                {
                    "window_index": window_index,
                    "start_page": start_page,
                    "end_page": end_page,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr.strip(),
                    "stdout": completed.stdout.strip(),
                    "recovered_output": payload is not None,
                }
            )
            if not args.continue_on_error:
                break
        _write_payload(
            output_dir,
            merge_payloads(
                input_name=Path(args.input).name,
                source_page_count=source_page_count,
                selected_pages=selected_pages,
                window_size=args.window_size,
                window_results=window_results,
                failed_windows=failed_windows,
                min_confidence=args.min_confidence,
                work_dir=str(work_dir),
            ),
        )

    payload = merge_payloads(
        input_name=Path(args.input).name,
        source_page_count=source_page_count,
        selected_pages=selected_pages,
        window_size=args.window_size,
        window_results=window_results,
        failed_windows=failed_windows,
        min_confidence=args.min_confidence,
        work_dir=str(work_dir),
    )
    _write_payload(output_dir, payload)
    processed = payload["metadata"]["processed_page_count"]
    print(
        f"processed_pages={processed}/{source_page_count} "
        f"windows={payload['metadata']['completed_window_count']}/{payload['metadata']['window_count']} "
        f"failed_windows={len(failed_windows)}"
    )
    if failed_windows or not payload["elements"]:
        return 1
    return 0


def merge_payloads(
    input_name: str,
    source_page_count: int,
    selected_pages: list[int],
    window_size: int,
    window_results: list[dict[str, Any]],
    failed_windows: list[dict[str, Any]],
    min_confidence: float,
    work_dir: str | None = None,
) -> dict[str, Any]:
    pages_by_number: dict[int, dict[str, Any]] = {}
    elements: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    processed_pages: set[int] = set()
    skipped_pages: set[int] = set()
    low_confidence_element_count = 0
    metadata_low_confidence_element_count = 0

    for payload in window_results:
        for page in _dict_items(payload.get("pages")):
            page_number = _int_value(page.get("page_number"))
            if page_number is not None:
                pages_by_number.setdefault(page_number, page)
                processed_pages.add(page_number)
        for element in _dict_items(payload.get("elements")):
            elements.append(element)
            if _float_value(element.get("confidence"), 1.0) < min_confidence:
                low_confidence_element_count += 1
        warnings.extend(_dict_items(payload.get("warnings")))
        tables.extend(_dict_items(payload.get("tables")))
        images.extend(_dict_items(payload.get("images")))
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        for page_number in _int_list(metadata.get("processed_pages")):
            processed_pages.add(page_number)
        for page_number in _int_list(metadata.get("skipped_pages")):
            skipped_pages.add(page_number)
        metadata_low_confidence = _int_value(metadata.get("low_confidence_element_count"))
        if metadata_low_confidence is not None:
            metadata_low_confidence_element_count += metadata_low_confidence

    low_confidence_element_count = max(low_confidence_element_count, metadata_low_confidence_element_count)

    for failed in failed_windows:
        warnings.append(
            {
                "severity": "high",
                "scope": "document",
                "message": (
                    "PaddleOCR window failed for pages "
                    f"{failed.get('start_page')}-{failed.get('end_page')}."
                ),
                "source_parser": "paddleocr",
            }
        )

    selected_page_set = set(selected_pages)
    missing_selected_pages = selected_page_set - processed_pages
    skipped_pages.update(missing_selected_pages)
    ordered_pages = [pages_by_number[page_number] for page_number in sorted(pages_by_number)]
    ordered_elements = sorted(
        elements,
        key=lambda item: (
            _int_value(item.get("page_number")) or 0,
            _bbox_sort_key(item.get("bbox")),
            str(item.get("text") or ""),
        ),
    )
    partial_output = bool(
        failed_windows
        or skipped_pages
        or len(processed_pages) < source_page_count
        or len(selected_pages) < source_page_count
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "adapter": "paddleocr",
        "pages": ordered_pages,
        "elements": ordered_elements,
        "tables": tables,
        "images": images,
        "warnings": warnings,
        "metadata": {
            "input_file": input_name,
            "source_page_count": source_page_count,
            "selected_page_count": len(selected_pages),
            "window_size": window_size,
            "window_count": len(list(_windows(selected_pages, window_size))),
            "completed_window_count": len(window_results),
            "failed_windows": failed_windows,
            "processed_pages": sorted(processed_pages),
            "processed_page_count": len(processed_pages),
            "skipped_pages": sorted(skipped_pages),
            "skipped_page_count": len(skipped_pages),
            "partial_output": partial_output,
            "min_confidence": min_confidence,
            "low_confidence_element_count": low_confidence_element_count,
            "page_count": len(ordered_pages),
            "windowed_bridge": True,
            "window_cache_dir": work_dir,
        },
    }


def _bridge_command(args: argparse.Namespace, output_dir: Path, start_page: int, end_page: int) -> list[str]:
    command = [
        sys.executable,
        str(Path(args.bridge_script)),
        "--input",
        str(Path(args.input)),
        "--output",
        str(output_dir),
        "--lang",
        args.lang,
        "--dpi",
        str(args.dpi),
        "--det-model-name",
        args.det_model_name,
        "--rec-model-name",
        args.rec_model_name,
        "--text-det-limit-side-len",
        str(args.text_det_limit_side_len),
        "--start-page",
        str(start_page),
        "--end-page",
        str(end_page),
        "--checkpoint-every",
        str(args.checkpoint_every),
        "--min-confidence",
        str(args.min_confidence),
    ]
    if args.cache_dir:
        command.extend(["--cache-dir", args.cache_dir])
    if args.model_source:
        command.extend(["--model-source", args.model_source])
    return command


def _pdf_page_count(path: Path) -> int:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError(f"PyMuPDF is required for windowed OCR page counting: {exc}") from exc
    pdf = fitz.open(path)
    try:
        return len(pdf)
    finally:
        pdf.close()


def _selected_pages(
    source_page_count: int,
    start_page: int,
    end_page: int | None,
    max_pages: int | None,
    max_windows: int | None,
    window_size: int,
) -> list[int]:
    start = max(1, start_page)
    end = min(source_page_count, end_page if end_page is not None else source_page_count)
    if start > end:
        return []
    pages = list(range(start, end + 1))
    if max_pages is not None:
        pages = pages[: max(0, max_pages)]
    if max_windows is not None:
        pages = pages[: max(0, max_windows) * window_size]
    return pages


def _windows(pages: list[int], window_size: int) -> list[tuple[int, int]]:
    size = max(1, window_size)
    return [(chunk[0], chunk[-1]) for chunk in (pages[index : index + size] for index in range(0, len(pages), size)) if chunk]


def _read_payload(output_dir: Path) -> dict[str, Any] | None:
    json_path = output_dir / "paddleocr.json"
    if not json_path.exists():
        matches = sorted(output_dir.rglob("*.json"))
        json_path = matches[0] if matches else json_path
    if not json_path.exists():
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _default_work_dir(input_path: Path, args: argparse.Namespace) -> Path:
    stat = input_path.stat()
    identity = "|".join(
        [
            str(input_path.resolve()),
            str(stat.st_size),
            str(int(stat.st_mtime)),
            str(args.window_size),
            str(args.start_page),
            str(args.end_page),
            str(args.max_pages),
            str(args.max_windows),
            str(args.dpi),
            str(args.text_det_limit_side_len),
            args.lang,
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in input_path.stem)[:80]
    return Path(__file__).resolve().parents[1] / ".tmp" / "paddleocr-window-cache" / f"{safe_stem}-{digest}"


def _write_payload(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "paddleocr.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "paddleocr.md").write_text(_payload_to_markdown(payload), encoding="utf-8")
    (output_dir / "paddleocr.txt").write_text(_payload_to_text(payload), encoding="utf-8")


def _payload_to_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    current_page: int | None = None
    for element in payload.get("elements", []):
        if not isinstance(element, dict):
            continue
        page_number = element.get("page_number")
        if page_number != current_page:
            current_page = page_number
            lines.extend(["", f"<!-- page: {page_number} -->", ""])
        lines.append(str(element.get("markdown") or element.get("text") or ""))
    return "\n".join(lines).strip() + "\n"


def _payload_to_text(payload: dict[str, Any]) -> str:
    return "\n".join(
        str(element.get("text") or "")
        for element in payload.get("elements", [])
        if isinstance(element, dict)
    ).strip() + "\n"


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        int_item = _int_value(item)
        if int_item is not None:
            result.append(int_item)
    return result


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bbox_sort_key(value: Any) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) < 2:
        return (0.0, 0.0)
    return (_float_value(value[1], 0.0), _float_value(value[0], 0.0))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PaddleOCR PDF bridge in page windows and merge outputs.")
    parser.add_argument("--input", required=True, help="Input PDF path.")
    parser.add_argument("--output", required=True, help="Output directory for merged CleanRAG adapter files.")
    parser.add_argument(
        "--bridge-script",
        default=str(Path(__file__).resolve().parent / "paddleocr_pdf_bridge.py"),
        help="Underlying single-window PaddleOCR bridge script.",
    )
    parser.add_argument("--window-size", type=int, default=20, help="Number of pages per OCR subprocess.")
    parser.add_argument("--start-page", type=int, default=1, help="First 1-based page to process.")
    parser.add_argument("--end-page", type=int, default=None, help="Last 1-based page to process.")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional smoke-test limiter for pages.")
    parser.add_argument("--max-windows", type=int, default=None, help="Optional smoke-test limiter for windows.")
    parser.add_argument("--lang", default="ch", help="PaddleOCR language code.")
    parser.add_argument("--dpi", type=int, default=30, help="Render DPI for PDF pages.")
    parser.add_argument("--det-model-name", default="PP-OCRv5_mobile_det", help="PaddleOCR text detection model name.")
    parser.add_argument("--rec-model-name", default="PP-OCRv5_mobile_rec", help="PaddleOCR text recognition model name.")
    parser.add_argument("--text-det-limit-side-len", type=int, default=320, help="Text detector max side length.")
    parser.add_argument("--checkpoint-every", type=int, default=1, help="Single-window checkpoint interval.")
    parser.add_argument("--min-confidence", type=float, default=0.5, help="Confidence threshold for OCR review risks.")
    parser.add_argument("--cache-dir", default=None, help="PaddleX/PaddleOCR model cache directory.")
    parser.add_argument("--work-dir", default=None, help="Persistent window output directory for resume/reuse.")
    parser.add_argument("--model-source", default=None, help="Optional PaddleX model source, for example aistudio.")
    parser.add_argument("--continue-on-error", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reuse-existing", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
