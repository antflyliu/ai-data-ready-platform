from __future__ import annotations

import shutil
import os
import tempfile
import unittest
from pathlib import Path

from cleanrag.pdf_adapters import default_pdf_adapters, inspect_pdf_profile, select_pdf_workflow
from cleanrag.pipeline import run_pipeline


try:
    import fitz  # type: ignore[import-not-found]
except Exception:
    fitz = None


@unittest.skipIf(fitz is None, "PyMuPDF is not available")
class PdfAdapterTest(unittest.TestCase):
    def test_registry_contains_requested_pdf_adapters(self) -> None:
        names = [adapter.name for adapter in default_pdf_adapters()]
        self.assertEqual(
            names,
            [
                "mineru",
                "opendataloader",
                "docling",
                "unstructured",
                "pymupdf",
                "deepdoc",
                "deepdoctection",
                "paddleocr",
                "textract",
            ],
        )

    def test_pdf_adapter_preserves_page_source_mapping(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        try:
            input_dir = temp_dir / "input"
            input_dir.mkdir()
            pdf_path = input_dir / "manual.pdf"
            _write_sample_pdf(pdf_path)

            output_dir = temp_dir / "out"
            quality = run_pipeline(input_dir, output_dir, dataset_id="pdf_fixture")

            self.assertEqual(quality["summary"]["documents"], 1)
            self.assertEqual(quality["summary"]["pdf_workflow_documents"], 1)
            self.assertGreaterEqual(quality["summary"]["pdf_adapter_successes"], 1)
            self.assertGreater(quality["summary"]["elements"], 0)
            self.assertGreater(quality["summary"]["chunks"], 0)
            self.assertGreaterEqual(quality["summary"]["parse_warnings"], 0)
            self.assertGreaterEqual(quality["summary"]["fallback_documents"], 0)
            self.assertGreater(quality["scores"]["source_traceability"], 0)
            self.assertIn("pdf_adapter_summary", quality)
        finally:
            shutil.rmtree(temp_dir)

    def test_image_only_pdf_is_reported_as_ocr_risk(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        old_disable = os.environ.get("CLEANRAG_DISABLE_PADDLEOCR_AUTO")
        os.environ["CLEANRAG_DISABLE_PADDLEOCR_AUTO"] = "1"
        try:
            input_dir = temp_dir / "input"
            input_dir.mkdir()
            pdf_path = input_dir / "scan.pdf"
            _write_image_only_pdf(pdf_path)
            profile = inspect_pdf_profile(pdf_path)
            workflow_names = [adapter.name for adapter in select_pdf_workflow(profile, default_pdf_adapters())]

            output_dir = temp_dir / "out"
            quality = run_pipeline(input_dir, output_dir, dataset_id="scan_fixture")

            self.assertEqual(quality["summary"]["documents"], 1)
            self.assertEqual(quality["summary"]["image_only_documents"], 1)
            self.assertEqual(quality["summary"]["pdf_ocr_required_documents"], 1)
            self.assertEqual(quality["summary"]["chunks"], 0)
            self.assertEqual(profile.kind, "scanned")
            self.assertEqual(workflow_names[:2], ["paddleocr", "textract"])
            self.assertTrue(
                any("OCR/hybrid" in risk for risk in quality["risks"]),
                quality["risks"],
            )
        finally:
            if old_disable is None:
                os.environ.pop("CLEANRAG_DISABLE_PADDLEOCR_AUTO", None)
            else:
                os.environ["CLEANRAG_DISABLE_PADDLEOCR_AUTO"] = old_disable
            shutil.rmtree(temp_dir)


def _write_sample_pdf(path: Path) -> None:
    assert fitz is not None
    doc = fitz.open()
    for page_number in range(1, 3):
        page = doc.new_page()
        page.insert_text((72, 40), "Header: ACME Internal Manual")
        page.insert_text(
            (72, 120),
            f"Reset procedure page {page_number}. Hold the reset button for five seconds.",
        )
        page.insert_text((72, 760), "Footer: ACME Internal Manual")
    doc.save(path)
    doc.close()


def _write_image_only_pdf(path: Path) -> None:
    assert fitz is not None
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 160, 80), 0)
    pix.clear_with(230)
    page.insert_image(fitz.Rect(72, 72, 232, 152), pixmap=pix)
    doc.save(path)
    doc.close()
