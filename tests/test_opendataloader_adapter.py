from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

from cleanrag.parsers import parse_file


class OpenDataLoaderAdapterTest(unittest.TestCase):
    def test_opendataloader_output_is_normalized_to_document_ir(self) -> None:
        temp_dir = Path(tempfile.mkdtemp())
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        fake_module = types.ModuleType("opendataloader_pdf")

        def convert(input_path: str, output_dir: str, format: str, quiet: bool, **kwargs) -> None:
            self.assertEqual(Path(input_path), pdf_path)
            self.assertIn("json", format)
            out = Path(output_dir)
            payload = {
                "number of pages": 1,
                "kids": [
                    {
                        "id": "h1",
                        "type": "heading",
                        "content": "Manual",
                        "heading level": 1,
                        "page number": 1,
                        "bounding box": [1, 2, 3, 4],
                    },
                    {
                        "id": "p1",
                        "type": "paragraph",
                        "content": "Reset the device.",
                        "page number": 1,
                        "bounding box": [5, 6, 7, 8],
                    },
                ],
            }
            (out / "sample.json").write_text(json.dumps(payload), encoding="utf-8")
            (out / "sample.md").write_text("# Manual\n\nReset the device.", encoding="utf-8")

        fake_module.convert = convert  # type: ignore[attr-defined]
        old_module = sys.modules.get("opendataloader_pdf")
        old_skip_java = os.environ.get("CLEANRAG_OPENDATALOADER_SKIP_JAVA_CHECK")
        sys.modules["opendataloader_pdf"] = fake_module
        os.environ["CLEANRAG_OPENDATALOADER_SKIP_JAVA_CHECK"] = "1"
        try:
            document = parse_file(pdf_path, dataset_id="fake", index=1)
        finally:
            if old_skip_java is None:
                os.environ.pop("CLEANRAG_OPENDATALOADER_SKIP_JAVA_CHECK", None)
            else:
                os.environ["CLEANRAG_OPENDATALOADER_SKIP_JAVA_CHECK"] = old_skip_java
            if old_module is None:
                sys.modules.pop("opendataloader_pdf", None)
            else:
                sys.modules["opendataloader_pdf"] = old_module

        self.assertEqual(document.metadata["parser"], "opendataloader")
        self.assertEqual(document.metadata["pdf_profile"]["kind"], "unknown")
        self.assertEqual(document.metadata["pdf_workflow"]["adapter_results"][0]["adapter_name"], "opendataloader")
        self.assertEqual(document.metadata["pdf_workflow"]["adapter_results"][0]["status"], "success")
        self.assertEqual(len(document.pages), 1)
        self.assertEqual([element.type for element in document.elements], ["title", "paragraph"])
        self.assertEqual(document.elements[1].title_path, ["Manual"])
        self.assertEqual(document.elements[1].bbox, [5.0, 6.0, 7.0, 8.0])


if __name__ == "__main__":
    unittest.main()
