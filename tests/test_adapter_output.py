from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cleanrag.models import Source
from cleanrag.pdf_adapters import ConfiguredCommandAdapter, PdfProfile, _document_from_adapter_output


class AdapterOutputTest(unittest.TestCase):
    def test_cleanrag_adapter_json_is_normalized_to_document_ir(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        try:
            payload = {
                "schema_version": "cleanrag.adapter_output.v1",
                "adapter": "paddleocr",
                "pages": [{"page_number": 1, "width": 612, "height": 792, "unit": "pt"}],
                "elements": [
                    {
                        "type": "paragraph",
                        "text": "OCR text line",
                        "markdown": "OCR text line",
                        "page_number": 1,
                        "bbox": [10, 20, 110, 40],
                        "confidence": 0.93,
                        "source_parser": "paddleocr",
                        "metadata": {"ocr_line_number": 1},
                    }
                ],
                "warnings": [
                    {
                        "severity": "low",
                        "scope": "page",
                        "page_number": 1,
                        "message": "Synthetic warning",
                        "source_parser": "paddleocr",
                    }
                ],
                "metadata": {"dpi": 200, "lang": "ch"},
            }
            (temp_dir / "adapter.json").write_text(json.dumps(payload), encoding="utf-8")
            document = _document_from_adapter_output(
                temp_dir,
                dataset_id="adapter_fixture",
                document_id="doc_0001",
                source=_source(),
                parser_name="paddleocr",
                profile=PdfProfile(
                    kind="scanned",
                    page_count=1,
                    text_pages=0,
                    image_pages=1,
                    image_count=1,
                ),
            )

            self.assertEqual(document.metadata["parser"], "paddleocr")
            self.assertEqual(document.metadata["adapter_output_schema"], "cleanrag.adapter_output.v1")
            self.assertEqual(document.pages[0].page_number, 1)
            self.assertEqual(document.elements[0].text, "OCR text line")
            self.assertEqual(document.elements[0].page_number, 1)
            self.assertEqual(document.elements[0].bbox, [10.0, 20.0, 110.0, 40.0])
            self.assertEqual(document.elements[0].confidence, 0.93)
            self.assertEqual(document.parse_warnings[0].message, "Synthetic warning")
        finally:
            shutil.rmtree(temp_dir)

    def test_cleanrag_adapter_json_preserves_partial_ocr_metadata(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        try:
            payload = {
                "schema_version": "cleanrag.adapter_output.v1",
                "adapter": "paddleocr",
                "pages": [{"page_number": 1, "width": 612, "height": 792, "unit": "pt"}],
                "elements": [
                    {
                        "type": "paragraph",
                        "text": "partial OCR text",
                        "page_number": 1,
                        "confidence": 0.42,
                        "source_parser": "paddleocr",
                    }
                ],
                "metadata": {
                    "source_page_count": 10,
                    "processed_pages": [1],
                    "processed_page_count": 1,
                    "partial_output": True,
                    "low_confidence_element_count": 1,
                },
            }
            (temp_dir / "paddleocr.json").write_text(json.dumps(payload), encoding="utf-8")
            document = _document_from_adapter_output(
                temp_dir,
                dataset_id="adapter_fixture",
                document_id="doc_0001",
                source=_source(),
                parser_name="paddleocr",
                profile=PdfProfile(
                    kind="scanned",
                    page_count=10,
                    text_pages=0,
                    image_pages=10,
                    image_count=10,
                ),
            )

            self.assertTrue(document.metadata["partial_output"])
            self.assertEqual(document.metadata["source_page_count"], 10)
            self.assertEqual(document.metadata["processed_page_count"], 1)
            self.assertEqual(document.metadata["processed_pages"], [1])
            self.assertEqual(document.metadata["low_confidence_element_count"], 1)
        finally:
            shutil.rmtree(temp_dir)

    def test_adapter_output_prefers_root_json_over_nested_checkpoint_json(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        try:
            nested_dir = temp_dir / "_windows" / "pages_0001_0001"
            nested_dir.mkdir(parents=True)
            nested_payload = {
                "schema_version": "cleanrag.adapter_output.v1",
                "adapter": "paddleocr",
                "pages": [{"page_number": 1, "width": 612, "height": 792, "unit": "pt"}],
                "elements": [{"type": "paragraph", "text": "nested", "page_number": 1}],
                "metadata": {"processed_pages": [1], "processed_page_count": 1},
            }
            root_payload = {
                "schema_version": "cleanrag.adapter_output.v1",
                "adapter": "paddleocr",
                "pages": [
                    {"page_number": 1, "width": 612, "height": 792, "unit": "pt"},
                    {"page_number": 2, "width": 612, "height": 792, "unit": "pt"},
                ],
                "elements": [{"type": "paragraph", "text": "merged", "page_number": 2}],
                "metadata": {
                    "processed_pages": [1, 2],
                    "processed_page_count": 2,
                    "windowed_bridge": True,
                },
            }
            (nested_dir / "paddleocr.json").write_text(json.dumps(nested_payload), encoding="utf-8")
            (temp_dir / "paddleocr.json").write_text(json.dumps(root_payload), encoding="utf-8")

            document = _document_from_adapter_output(
                temp_dir,
                dataset_id="adapter_fixture",
                document_id="doc_0001",
                source=_source(),
                parser_name="paddleocr",
                profile=PdfProfile(
                    kind="scanned",
                    page_count=2,
                    text_pages=0,
                    image_pages=2,
                    image_count=2,
                ),
            )

            self.assertEqual(document.elements[0].text, "merged")
            self.assertTrue(document.metadata["windowed_bridge"])
            self.assertEqual(document.metadata["processed_pages"], [1, 2])
        finally:
            shutil.rmtree(temp_dir)

    def test_command_adapter_recovers_partial_json_when_command_fails(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        old_command = os.environ.get("CLEANRAG_PARTIAL_TEST_COMMAND")
        try:
            script = temp_dir / "partial_writer.py"
            script.write_text(
                "\n".join(
                    [
                        "import json",
                        "import pathlib",
                        "import sys",
                        "output = pathlib.Path(sys.argv[1])",
                        "output.mkdir(parents=True, exist_ok=True)",
                        "payload = {",
                        "  'schema_version': 'cleanrag.adapter_output.v1',",
                        "  'adapter': 'partialocr',",
                        "  'pages': [{'page_number': 1, 'width': 612, 'height': 792, 'unit': 'pt'}],",
                        "  'elements': [{'type': 'paragraph', 'text': 'recovered text', 'page_number': 1, 'confidence': 0.8}],",
                        "  'metadata': {'source_page_count': 3, 'processed_pages': [1], 'processed_page_count': 1, 'partial_output': True},",
                        "}",
                        "(output / 'partialocr.json').write_text(json.dumps(payload), encoding='utf-8')",
                        "raise SystemExit(1)",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["CLEANRAG_PARTIAL_TEST_COMMAND"] = json.dumps([sys.executable, str(script), "{output}"])

            adapter = _PartialTestAdapter()
            result = adapter.parse(
                temp_dir / "scan.pdf",
                dataset_id="adapter_fixture",
                document_id="doc_0001",
                source=_source(),
                profile=PdfProfile(
                    kind="scanned",
                    page_count=3,
                    text_pages=0,
                    image_pages=3,
                    image_count=3,
                ),
            )

            self.assertEqual(result.status, "success")
            self.assertIsNotNone(result.document)
            assert result.document is not None
            self.assertEqual(result.document.elements[0].text, "recovered text")
            self.assertTrue(result.document.metadata["partial_output"])
            self.assertTrue(result.metadata["partial_recovery"])
            self.assertTrue(any("partial output" in warning.message.lower() for warning in result.document.parse_warnings))
        finally:
            if old_command is None:
                os.environ.pop("CLEANRAG_PARTIAL_TEST_COMMAND", None)
            else:
                os.environ["CLEANRAG_PARTIAL_TEST_COMMAND"] = old_command
            shutil.rmtree(temp_dir)

    def test_paddleocr_bridge_check_only_reports_dependency_keys(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "paddleocr_pdf_bridge.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--check-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(completed.stdout)
        self.assertIn("pymupdf_available", payload)
        self.assertIn("paddleocr_available", payload)


def _source() -> Source:
    return Source(
        path="scan.pdf",
        filename="scan.pdf",
        mime_type="application/pdf",
        sha256="0" * 64,
        size_bytes=100,
    )


class _PartialTestAdapter(ConfiguredCommandAdapter):
    name = "partialocr"
    role = "ocr"
    env_var = "CLEANRAG_PARTIAL_TEST_COMMAND"
    supported_kinds = ("scanned",)


if __name__ == "__main__":
    unittest.main()
