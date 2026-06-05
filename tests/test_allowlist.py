from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cleanrag.pipeline import run_pipeline


class AllowlistTest(unittest.TestCase):
    def test_sensitive_allowlist_removes_known_false_positive(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures" / "input"
        temp_dir = Path(tempfile.mkdtemp())
        try:
            allowlist_path = temp_dir / "allowlist.json"
            allowlist_path.write_text(
                json.dumps({"sensitive_text": ["support@example.com"]}),
                encoding="utf-8-sig",
            )

            quality = run_pipeline(
                fixture_dir,
                temp_dir / "out",
                dataset_id="allowlist_fixture",
                allowlist_path=allowlist_path,
            )

            self.assertFalse(
                [detail for detail in quality["risk_details"] if detail["type"] == "sensitive_chunk"],
                quality["risk_details"],
            )
            self.assertFalse(
                [item for item in quality["review_items"] if item["type"] == "sensitive_chunk"],
                quality["review_items"],
            )
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
