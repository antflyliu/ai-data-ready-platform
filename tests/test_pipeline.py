from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cleanrag.pipeline import run_pipeline


class PipelineTest(unittest.TestCase):
    def test_run_pipeline_exports_traceable_dataset(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures" / "input"
        temp_dir = Path(tempfile.mkdtemp())
        try:
            output_dir = temp_dir / "out"
            quality = run_pipeline(fixture_dir, output_dir, dataset_id="fixture")

            self.assertEqual(quality["dataset_id"], "fixture")
            self.assertGreaterEqual(quality["summary"]["documents"], 2)
            self.assertGreater(quality["summary"]["chunks"], 0)
            self.assertGreater(quality["summary"]["excluded_elements"], 0)

            for filename in [
                "dataset.json",
                "documents.jsonl",
                "elements.jsonl",
                "chunks.jsonl",
                "cleaning_events.jsonl",
                "review_items.jsonl",
                "review_items.md",
                "quality_report.json",
                "quality_report.md",
                "dataset_card.md",
                "acceptance_report.md",
            ]:
                self.assertTrue((output_dir / filename).exists(), filename)

            chunks = _read_jsonl(output_dir / "chunks.jsonl")
            self.assertTrue(all(chunk["element_ids"] for chunk in chunks))
            self.assertTrue(all("source_locations" in chunk for chunk in chunks))

            events = _read_jsonl(output_dir / "cleaning_events.jsonl")
            self.assertTrue(all(event["rule_id"] for event in events))
            self.assertTrue(any(event["action"] == "exclude_from_export" for event in events))

            review_items = _read_jsonl(output_dir / "review_items.jsonl")
            self.assertGreater(len(review_items), 0)
            self.assertTrue(all(item["status"] == "needs_review" for item in review_items))
        finally:
            shutil.rmtree(temp_dir)


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


if __name__ == "__main__":
    unittest.main()
