from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any


try:
    import fitz  # type: ignore[import-not-found]
except Exception:
    fitz = None


class PaddleOCRWindowedBridgeTest(unittest.TestCase):
    def test_merge_payloads_orders_pages_and_marks_partial_output(self) -> None:
        module = _load_windowed_bridge()
        payload = module.merge_payloads(  # type: ignore[attr-defined]
            input_name="scan.pdf",
            source_page_count=4,
            selected_pages=[1, 2, 3],
            window_size=2,
            window_results=[
                _payload([3], ["page 3"], source_page_count=4, low_confidence=1),
                _payload([1, 2], ["page 1", "page 2"], source_page_count=4),
            ],
            failed_windows=[],
            min_confidence=0.5,
        )

        self.assertEqual([page["page_number"] for page in payload["pages"]], [1, 2, 3])
        self.assertEqual([element["text"] for element in payload["elements"]], ["page 1", "page 2", "page 3"])
        self.assertEqual(payload["metadata"]["processed_pages"], [1, 2, 3])
        self.assertEqual(payload["metadata"]["processed_page_count"], 3)
        self.assertTrue(payload["metadata"]["partial_output"])
        self.assertEqual(payload["metadata"]["low_confidence_element_count"], 1)

    @unittest.skipIf(fitz is None, "PyMuPDF is not available")
    def test_windowed_cli_runs_fake_bridge_and_merges_windows(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        try:
            input_pdf = temp_dir / "scan.pdf"
            _write_blank_pdf(input_pdf, page_count=4)
            fake_bridge = temp_dir / "fake_bridge.py"
            fake_bridge.write_text(_fake_bridge_source(), encoding="utf-8")
            output_dir = temp_dir / "out"
            script = Path(__file__).resolve().parents[1] / "scripts" / "paddleocr_windowed_pdf_bridge.py"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--input",
                    str(input_pdf),
                    "--output",
                    str(output_dir),
                    "--bridge-script",
                    str(fake_bridge),
                    "--window-size",
                    "2",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            self.assertIn("processed_pages=4/4", completed.stdout)
            payload = json.loads((output_dir / "paddleocr.json").read_text(encoding="utf-8"))
            self.assertFalse(payload["metadata"]["partial_output"])
            self.assertEqual(payload["metadata"]["processed_pages"], [1, 2, 3, 4])
            self.assertEqual(len(payload["elements"]), 4)
        finally:
            shutil.rmtree(temp_dir)

    @unittest.skipIf(fitz is None, "PyMuPDF is not available")
    def test_windowed_cli_reuses_existing_window_payloads(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        try:
            input_pdf = temp_dir / "scan.pdf"
            _write_blank_pdf(input_pdf, page_count=2)
            fake_bridge = temp_dir / "fake_bridge.py"
            fake_bridge.write_text(_fake_bridge_source(), encoding="utf-8")
            work_dir = temp_dir / "window-cache"
            output_dir = temp_dir / "out"
            script = Path(__file__).resolve().parents[1] / "scripts" / "paddleocr_windowed_pdf_bridge.py"
            command = [
                sys.executable,
                str(script),
                "--input",
                str(input_pdf),
                "--output",
                str(output_dir),
                "--bridge-script",
                str(fake_bridge),
                "--window-size",
                "1",
                "--work-dir",
                str(work_dir),
            ]

            subprocess.run(command, capture_output=True, text=True, check=True)
            fake_bridge.write_text("raise SystemExit(99)\n", encoding="utf-8")
            completed = subprocess.run(command, capture_output=True, text=True, check=True)

            self.assertIn("failed_windows=0", completed.stdout)
            payload = json.loads((output_dir / "paddleocr.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["processed_pages"], [1, 2])
            self.assertEqual(payload["metadata"]["window_cache_dir"], str(work_dir))
        finally:
            shutil.rmtree(temp_dir)


def _load_windowed_bridge() -> Any:
    script = Path(__file__).resolve().parents[1] / "scripts" / "paddleocr_windowed_pdf_bridge.py"
    spec = spec_from_file_location("paddleocr_windowed_pdf_bridge", script)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(
    page_numbers: list[int],
    texts: list[str],
    source_page_count: int,
    low_confidence: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "cleanrag.adapter_output.v1",
        "adapter": "paddleocr",
        "pages": [
            {"page_number": page_number, "width": 612, "height": 792, "unit": "pt"}
            for page_number in page_numbers
        ],
        "elements": [
            {
                "type": "paragraph",
                "text": text,
                "page_number": page_number,
                "confidence": 0.4 if index < low_confidence else 0.8,
                "source_parser": "paddleocr",
            }
            for index, (page_number, text) in enumerate(zip(page_numbers, texts))
        ],
        "warnings": [],
        "metadata": {
            "source_page_count": source_page_count,
            "processed_pages": page_numbers,
            "processed_page_count": len(page_numbers),
            "low_confidence_element_count": low_confidence,
        },
    }


def _write_blank_pdf(path: Path, page_count: int) -> None:
    assert fitz is not None
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    doc.save(path)
    doc.close()


def _fake_bridge_source() -> str:
    return r'''
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input")
parser.add_argument("--output")
parser.add_argument("--start-page", type=int, default=1)
parser.add_argument("--end-page", type=int, required=True)
parser.add_argument("--min-confidence", type=float, default=0.5)
args, _ = parser.parse_known_args()

output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)
pages = list(range(args.start_page, args.end_page + 1))
payload = {
    "schema_version": "cleanrag.adapter_output.v1",
    "adapter": "paddleocr",
    "pages": [{"page_number": page, "width": 612, "height": 792, "unit": "pt"} for page in pages],
    "elements": [
        {
            "type": "paragraph",
            "text": f"page {page}",
            "page_number": page,
            "confidence": 0.8,
            "source_parser": "paddleocr",
        }
        for page in pages
    ],
    "warnings": [],
    "metadata": {
        "source_page_count": 4,
        "processed_pages": pages,
        "processed_page_count": len(pages),
        "partial_output": False,
        "low_confidence_element_count": 0,
        "min_confidence": args.min_confidence,
    },
}
(output / "paddleocr.json").write_text(json.dumps(payload), encoding="utf-8")
'''


if __name__ == "__main__":
    unittest.main()
