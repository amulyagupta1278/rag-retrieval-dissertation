#!/usr/bin/env python3
"""Create question-ID/text-only R5 input for leakage-safe retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    qa, output, manifest = args.qa.resolve(), args.output.resolve(), args.manifest.resolve()
    approved = (
        (ROOT / "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl").resolve(),
        (ROOT / "runs/v2/phase3_graph_v3_1/inputs/r5_queries_only.jsonl").resolve(),
        (ROOT / "runs/v2/phase3_graph_v3_1/inputs/r5_queries_only_manifest.json").resolve(),
    )
    if (qa, output, manifest) != approved:
        raise ValueError("query extraction requires approved R5/new output paths")
    rows = [json.loads(line) for line in qa.read_text(encoding="utf-8").splitlines() if line.strip()]
    queries = [{"query_id": str(row["question_id"]), "question": str(row["question"])} for row in rows]
    if len(queries) != 34 or len({row["query_id"] for row in queries}) != 34:
        raise ValueError("R5 query input must contain 34 unique questions")
    write_jsonl(output, queries, key="query_id", overwrite=args.overwrite)
    write_json(manifest, {
        "status": "question_id_and_text_only",
        "source_qa_path": str(qa.relative_to(ROOT)),
        "source_qa_sha256": sha256_file(qa),
        "output_path": str(output.relative_to(ROOT)),
        "output_sha256": sha256_file(output),
        "query_count": len(queries),
        "output_fields": ["query_id", "question"],
        "excluded_fields": sorted(set().union(*(set(row) for row in rows)) - {"question_id", "question"}),
    }, overwrite=args.overwrite)
    print(stable_json({"queries": len(queries), "output_sha256": sha256_file(output)}))


if __name__ == "__main__":
    main()
