from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "cleanrag.adapter_output.v1"


def main() -> int:
    args = _parse_args()
    _configure_paddlex_cache(args.cache_dir, args.model_source)
    availability = _availability()
    if args.check_only:
        print(json.dumps(availability, ensure_ascii=False, indent=2))
        return 0

    if not availability["pymupdf_available"]:
        print("PyMuPDF is required to render PDF pages for OCR.", file=sys.stderr)
        return 2
    if not availability["paddleocr_available"]:
        print("PaddleOCR is required. Install optional OCR dependencies before running this bridge.", file=sys.stderr)
        return 2
    if args.input is None or args.output is None:
        print("--input and --output are required unless --check-only is used.", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = run_bridge(
        input_path=input_path,
        output_dir=output_dir,
        dpi=args.dpi,
        lang=args.lang,
        det_model_name=args.det_model_name,
        rec_model_name=args.rec_model_name,
        text_det_limit_side_len=args.text_det_limit_side_len,
        max_pages=args.max_pages,
        start_page=args.start_page,
        end_page=args.end_page,
        min_confidence=args.min_confidence,
        checkpoint_every=args.checkpoint_every,
    )
    _write_payload(output_dir, payload)
    return 0


def run_bridge(
    input_path: Path,
    output_dir: Path,
    dpi: int,
    lang: str,
    det_model_name: str,
    rec_model_name: str,
    text_det_limit_side_len: int,
    max_pages: int | None = None,
    start_page: int = 1,
    end_page: int | None = None,
    min_confidence: float = 0.5,
    checkpoint_every: int = 1,
) -> dict[str, Any]:
    import fitz  # type: ignore[import-not-found]

    engine = _build_paddleocr(lang, det_model_name, rec_model_name, text_det_limit_side_len)
    pages: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    processed_pages: list[int] = []
    skipped_pages: list[int] = []
    low_confidence_element_count = 0
    matrix_scale = dpi / 72
    point_scale = 72 / dpi
    source_page_count = 0
    selected_page_indexes: list[int] = []

    with tempfile.TemporaryDirectory(prefix="cleanrag-paddleocr-pages-") as temp:
        image_dir = Path(temp)
        pdf = fitz.open(input_path)
        try:
            source_page_count = len(pdf)
            selected_page_indexes = _page_indexes(source_page_count, start_page, end_page, max_pages)
            if not selected_page_indexes:
                warnings.append(
                    {
                        "severity": "high",
                        "scope": "document",
                        "message": "No PDF pages were selected for PaddleOCR processing.",
                        "source_parser": "paddleocr",
                    }
                )
            checkpoint_interval = max(1, checkpoint_every)
            for offset, page_index in enumerate(selected_page_indexes, start=1):
                page_number = page_index + 1
                processed_pages.append(page_number)
                try:
                    page = pdf[page_index]
                    rect = page.rect
                    pages.append(
                        {
                            "page_number": page_number,
                            "width": float(rect.width),
                            "height": float(rect.height),
                            "unit": "pt",
                        }
                    )
                    image_path = image_dir / f"page_{page_number:04d}.png"
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(matrix_scale, matrix_scale), alpha=False)
                    pixmap.save(image_path)
                    raw_result = _predict_page(engine, image_path)
                    page_lines = list(_iter_ocr_lines(raw_result))
                    if not page_lines:
                        warnings.append(
                            {
                                "severity": "medium",
                                "scope": "page",
                                "page_number": page_number,
                                "message": "PaddleOCR returned no text lines for this page.",
                                "source_parser": "paddleocr",
                            }
                        )
                        continue
                    for line_index, item in enumerate(_sort_lines(page_lines), start=1):
                        bbox = _scale_bbox(item["bbox"], point_scale)
                        text = " ".join(item["text"].split())
                        if not text:
                            continue
                        confidence = _float(item.get("confidence", 0.0))
                        if confidence < min_confidence:
                            low_confidence_element_count += 1
                        elements.append(
                            {
                                "type": "paragraph",
                                "text": text,
                                "markdown": text,
                                "page_number": page_number,
                                "bbox": bbox,
                                "confidence": confidence,
                                "source_parser": "paddleocr",
                                "metadata": {
                                    "ocr_line_number": line_index,
                                    "ocr_bbox_unit": "pt",
                                    "ocr_input_dpi": dpi,
                                },
                            }
                        )
                except Exception as exc:
                    skipped_pages.append(page_number)
                    warnings.append(
                        {
                            "severity": "high",
                            "scope": "page",
                            "page_number": page_number,
                            "message": f"PaddleOCR failed on this page: {exc}",
                            "source_parser": "paddleocr",
                        }
                    )
                    continue
                finally:
                    if offset % checkpoint_interval == 0:
                        _write_payload(
                            output_dir,
                            _build_payload(
                                input_path=input_path,
                                dpi=dpi,
                                lang=lang,
                                det_model_name=det_model_name,
                                rec_model_name=rec_model_name,
                                text_det_limit_side_len=text_det_limit_side_len,
                                source_page_count=source_page_count,
                                selected_page_count=len(selected_page_indexes),
                                start_page=start_page,
                                end_page=end_page,
                                max_pages=max_pages,
                                processed_pages=processed_pages,
                                skipped_pages=skipped_pages,
                                pages=pages,
                                elements=elements,
                                warnings=warnings,
                                min_confidence=min_confidence,
                                low_confidence_element_count=low_confidence_element_count,
                            ),
                        )
        finally:
            pdf.close()

    if not elements:
        warnings.append(
            {
                "severity": "high",
                "scope": "document",
                "message": "PaddleOCR completed but produced no text elements.",
                "source_parser": "paddleocr",
            }
        )

    payload = _build_payload(
        input_path=input_path,
        dpi=dpi,
        lang=lang,
        det_model_name=det_model_name,
        rec_model_name=rec_model_name,
        text_det_limit_side_len=text_det_limit_side_len,
        source_page_count=source_page_count,
        selected_page_count=len(selected_page_indexes),
        start_page=start_page,
        end_page=end_page,
        max_pages=max_pages,
        processed_pages=processed_pages,
        skipped_pages=skipped_pages,
        pages=pages,
        elements=elements,
        warnings=warnings,
        min_confidence=min_confidence,
        low_confidence_element_count=low_confidence_element_count,
    )
    _write_payload(output_dir, payload)
    return payload


def _build_payload(
    input_path: Path,
    dpi: int,
    lang: str,
    det_model_name: str,
    rec_model_name: str,
    text_det_limit_side_len: int,
    source_page_count: int,
    selected_page_count: int,
    start_page: int,
    end_page: int | None,
    max_pages: int | None,
    processed_pages: list[int],
    skipped_pages: list[int],
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    min_confidence: float,
    low_confidence_element_count: int,
) -> dict[str, Any]:
    partial_output = bool(
        source_page_count
        and (
            len(processed_pages) < source_page_count
            or bool(skipped_pages)
            or selected_page_count < source_page_count
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter": "paddleocr",
        "pages": pages,
        "elements": elements,
        "warnings": warnings,
        "metadata": {
            "input_file": input_path.name,
            "dpi": dpi,
            "lang": lang,
            "det_model_name": det_model_name,
            "rec_model_name": rec_model_name,
            "text_det_limit_side_len": text_det_limit_side_len,
            "source_page_count": source_page_count,
            "selected_page_count": selected_page_count,
            "start_page": start_page,
            "end_page": end_page,
            "max_pages": max_pages,
            "processed_pages": list(processed_pages),
            "processed_page_count": len(processed_pages),
            "skipped_pages": list(skipped_pages),
            "skipped_page_count": len(skipped_pages),
            "partial_output": partial_output,
            "min_confidence": min_confidence,
            "low_confidence_element_count": low_confidence_element_count,
            "page_count": len(pages),
        },
    }


def _write_payload(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "paddleocr.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "paddleocr.md").write_text(_payload_to_markdown(payload), encoding="utf-8")
    (output_dir / "paddleocr.txt").write_text(_payload_to_text(payload), encoding="utf-8")


def _page_indexes(
    source_page_count: int,
    start_page: int,
    end_page: int | None,
    max_pages: int | None,
) -> list[int]:
    if source_page_count <= 0:
        return []
    start = max(1, start_page)
    end = min(source_page_count, end_page if end_page is not None else source_page_count)
    if start > end:
        return []
    indexes = list(range(start - 1, end))
    if max_pages is not None:
        indexes = indexes[: max(0, max_pages)]
    return indexes


def _configure_paddlex_cache(cache_dir: str | None, model_source: str | None) -> None:
    default_cache = Path(__file__).resolve().parents[1] / ".tmp" / "paddleocr-cache"
    cache_path = Path(cache_dir) if cache_dir else default_cache
    cache_path.mkdir(parents=True, exist_ok=True)
    import os

    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_path.resolve()))
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    if model_source:
        os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", model_source)


def _build_paddleocr(lang: str, det_model_name: str, rec_model_name: str, text_det_limit_side_len: int) -> Any:
    from paddleocr import PaddleOCR  # type: ignore[import-not-found]

    attempts = [
        {
            "text_detection_model_name": det_model_name,
            "text_recognition_model_name": rec_model_name,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "text_det_limit_side_len": text_det_limit_side_len,
            "text_recognition_batch_size": 1,
        },
        {
            "lang": lang,
            "ocr_version": "PP-OCRv4",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "text_det_limit_side_len": text_det_limit_side_len,
            "text_recognition_batch_size": 1,
        },
        {"lang": lang},
        {"lang": lang, "use_angle_cls": True},
        {},
    ]
    errors: list[str] = []
    for kwargs in attempts:
        try:
            return PaddleOCR(**kwargs)
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
    raise RuntimeError("Could not initialize PaddleOCR with supported constructor shapes: " + " | ".join(errors))


def _predict_page(engine: Any, image_path: Path) -> Any:
    if hasattr(engine, "predict"):
        try:
            return engine.predict(input=str(image_path))
        except TypeError:
            return engine.predict(str(image_path))
    if hasattr(engine, "ocr"):
        try:
            return engine.ocr(str(image_path), cls=True)
        except TypeError:
            return engine.ocr(str(image_path))
    raise RuntimeError("PaddleOCR engine exposes neither ocr() nor predict().")


def _iter_ocr_lines(value: Any) -> Iterable[dict[str, Any]]:
    if value is None:
        return
    if hasattr(value, "json"):
        yield from _iter_ocr_lines(getattr(value, "json"))
        return
    if hasattr(value, "to_json"):
        try:
            yield from _iter_ocr_lines(value.to_json())
            return
        except Exception:
            pass
    if isinstance(value, dict):
        yielded = False
        texts = value.get("rec_texts") or value.get("texts")
        if isinstance(texts, list):
            scores = value.get("rec_scores") or value.get("scores") or []
            boxes = value.get("rec_polys") or value.get("dt_polys") or value.get("boxes") or value.get("rec_boxes") or []
            for index, text in enumerate(texts):
                bbox = _polygon_to_bbox(boxes[index] if index < len(boxes) else None)
                if isinstance(text, str) and bbox:
                    yielded = True
                    yield {
                        "text": text,
                        "confidence": _float(scores[index] if index < len(scores) else 0.0),
                        "bbox": bbox,
                    }
        if not yielded and isinstance(value.get("text"), str):
            bbox = _polygon_to_bbox(value.get("bbox") or value.get("box") or value.get("points"))
            if bbox:
                yield {
                    "text": value["text"],
                    "confidence": _float(value.get("confidence") or value.get("score") or 0.0),
                    "bbox": bbox,
                }
                return
        for nested in value.values():
            yield from _iter_ocr_lines(nested)
        return
    if isinstance(value, (list, tuple)):
        legacy = _legacy_line(value)
        if legacy is not None:
            yield legacy
            return
        for item in value:
            yield from _iter_ocr_lines(item)


def _legacy_line(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    bbox = _polygon_to_bbox(value[0])
    if bbox is None:
        return None
    rec = value[1]
    if isinstance(rec, (list, tuple)) and rec and isinstance(rec[0], str):
        return {"text": rec[0], "confidence": _float(rec[1] if len(rec) > 1 else 0.0), "bbox": bbox}
    if isinstance(rec, str):
        return {"text": rec, "confidence": 0.0, "bbox": bbox}
    return None


def _polygon_to_bbox(value: Any) -> list[float] | None:
    if value is None:
        return None
    points: list[tuple[float, float]] = []
    if isinstance(value, (list, tuple)):
        if len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
            return [float(item) for item in value]
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                x = _float(item[0])
                y = _float(item[1])
                points.append((x, y))
    if not points:
        return None
    xs = [item[0] for item in points]
    ys = [item[1] for item in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _sort_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(lines, key=lambda item: ((item.get("bbox") or [0, 0, 0, 0])[1], (item.get("bbox") or [0, 0, 0, 0])[0]))


def _scale_bbox(bbox: list[float], scale: float) -> list[float]:
    return [round(value * scale, 3) for value in bbox]


def _payload_to_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    current_page: int | None = None
    for element in payload.get("elements", []):
        page_number = element.get("page_number")
        if page_number != current_page:
            current_page = page_number
            lines.extend(["", f"<!-- page: {page_number} -->", ""])
        lines.append(str(element.get("markdown") or element.get("text") or ""))
    return "\n".join(lines).strip() + "\n"


def _payload_to_text(payload: dict[str, Any]) -> str:
    return "\n".join(str(element.get("text") or "") for element in payload.get("elements", [])).strip() + "\n"


def _availability() -> dict[str, Any]:
    return {
        "pymupdf_available": _module_available("fitz"),
        "paddleocr_available": _module_available("paddleocr"),
    }


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render PDF pages and run PaddleOCR for CleanRAG.")
    parser.add_argument("--input", help="Input PDF path.")
    parser.add_argument("--output", help="Output directory for CleanRAG adapter files.")
    parser.add_argument("--dpi", type=int, default=30, help="Render DPI for PDF pages.")
    parser.add_argument("--lang", default="ch", help="PaddleOCR language code.")
    parser.add_argument("--det-model-name", default="PP-OCRv5_mobile_det", help="PaddleOCR text detection model name.")
    parser.add_argument("--rec-model-name", default="PP-OCRv5_mobile_rec", help="PaddleOCR text recognition model name.")
    parser.add_argument("--text-det-limit-side-len", type=int, default=320, help="Text detector max side length.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages for smoke tests.")
    parser.add_argument("--start-page", type=int, default=1, help="First 1-based page to process.")
    parser.add_argument("--end-page", type=int, default=None, help="Last 1-based page to process.")
    parser.add_argument("--checkpoint-every", type=int, default=1, help="Write partial output after this many pages.")
    parser.add_argument("--min-confidence", type=float, default=0.5, help="Confidence threshold for OCR review risks.")
    parser.add_argument("--cache-dir", default=None, help="PaddleX/PaddleOCR model cache directory.")
    parser.add_argument("--model-source", default=None, help="Optional PaddleX model source, for example aistudio.")
    parser.add_argument("--check-only", action="store_true", help="Print dependency availability and exit.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
