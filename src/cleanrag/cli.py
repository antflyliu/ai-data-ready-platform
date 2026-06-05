from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_pipeline, summary_line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cleanrag")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full CleanRAG MVP pipeline")
    run_parser.add_argument("input_dir", type=Path)
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--dataset-id", default=None)
    run_parser.add_argument("--allowlist", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "run":
        quality = run_pipeline(args.input_dir, args.out, args.dataset_id, args.allowlist)
        print(summary_line(quality))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
