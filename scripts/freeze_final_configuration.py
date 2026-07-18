#!/usr/bin/env python3
"""Freeze code/config/selection hashes before holdout questions are visible."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.holdout_lock import create_lock, verify_lock


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-file", action="append", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--bm25-index", required=True)
    parser.add_argument("--bm25-config", required=True)
    parser.add_argument("--faiss-index", required=True)
    parser.add_argument("--faiss-config", required=True)
    parser.add_argument("--graph-index", required=True)
    parser.add_argument("--graph-config", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--output", default="locks/final_configuration.json")
    parser.add_argument("--holdout", default="data/queries/holdout_qa.jsonl")
    args = parser.parse_args()
    if (ROOT / args.holdout).exists():
        raise RuntimeError("Refusing to freeze after the holdout dataset already exists")
    roots = ["src", "experiments", "scripts", "configs"]
    required_artifacts = [
        args.chunks, args.qrels, args.bm25_index, args.bm25_config,
        args.faiss_index, args.faiss_config, args.graph_index, args.graph_config,
        args.environment,
    ]
    lock = create_lock(
        ROOT, roots, args.selection_file + required_artifacts + args.artifact,
        ROOT / args.output,
    )
    verify_lock(ROOT / args.output, ROOT)
    print(json.dumps({"lock_id": lock["lock_id"], "files": len(lock["files"]), "status": lock["status"]}, indent=2))


if __name__ == "__main__":
    main()
