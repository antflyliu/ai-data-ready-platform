from __future__ import annotations

import unittest

from cleanrag.models import DocumentIR, Element, Source
from cleanrag.scoring import score_dataset


class ScoringRiskTest(unittest.TestCase):
    def test_partial_and_low_confidence_ocr_are_reported_as_review_risks(self) -> None:
        document = DocumentIR(
            schema_version="0.1",
            document_id="doc_0001",
            dataset_id="scan_fixture",
            source=Source(
                path="scan.pdf",
                filename="scan.pdf",
                mime_type="application/pdf",
                sha256="0" * 64,
                size_bytes=100,
            ),
            elements=[
                Element(
                    element_id="doc_0001_el_0001",
                    type="paragraph",
                    text="low confidence text",
                    markdown="low confidence text",
                    page_number=1,
                    confidence=0.31,
                    source_parser="paddleocr",
                )
            ],
            metadata={
                "parser": "paddleocr",
                "source_page_count": 10,
                "processed_page_count": 1,
                "processed_pages": [1],
                "partial_output": True,
                "low_confidence_element_count": 1,
            },
        )

        quality = score_dataset("scan_fixture", [document], [], [])
        risk_types = {detail["type"] for detail in quality["risk_details"]}

        self.assertIn("partial_pdf_ocr", risk_types)
        self.assertIn("low_confidence_ocr", risk_types)


if __name__ == "__main__":
    unittest.main()
