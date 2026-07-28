#!/usr/bin/env python3
"""Build blank Phase 6 owner judging package from approved blind inputs."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import stable_json, write_bytes, write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


BASE_COMMIT = "3a9633340ae215e6d6fbee1621a1afe4370975c5"
BLIND_POOL = ROOT / "runs/v2/phase5f_prompt_rag_pool/blind/provisional_all_systems_pool.jsonl"
QA = ROOT / "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl"
CHUNKS = ROOT / "data/v2/pilot/chunks/chunks.jsonl"
DOCUMENTS = ROOT / "data/v2/pilot/extracted/documents.jsonl"
OUTPUT = ROOT / "runs/v2/phase6_blind_judging_package"
AUDIT = ROOT / "audits/phase6"
PACKAGE = OUTPUT / "owner_judging_package.csv"

EXPECTED_HASHES = {
    BLIND_POOL: "ff48c3413e891377b3b7e035a35902146d2e9e3be088457f9d37f91d0b6c468f",
    QA: "0abd328ff639a05e80559202a018df0bd50aaf875f8d6b7753af925cc8a89c4b",
    CHUNKS: "70c1e3b8b0380809adea000654333a5921132ab7608ff328a9fa7934e8f43aa6",
    DOCUMENTS: "a3a3ceeba8f62cf4d387f7fe8f16ad5a6e167d05259ecb1c50afbaaa42d36773",
}
FIELDS = [
    "display_id",
    "query_id",
    "question",
    "reference_answer",
    "chunk_id",
    "source_document_title",
    "candidate_chunk",
    "relevance_grade",
    "rationale",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"expected JSONL objects: {path}")
    return rows


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=FIELDS,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def build(*, overwrite: bool = False) -> dict[str, Any]:
    for path, digest in EXPECTED_HASHES.items():
        if sha256_file(path) != digest:
            raise ValueError(f"approved input hash mismatch: {path.relative_to(ROOT)}")
    blind = load_jsonl(BLIND_POOL)
    qa_rows = load_jsonl(QA)
    chunk_rows = load_jsonl(CHUNKS)
    document_rows = load_jsonl(DOCUMENTS)
    if len(blind) != 755:
        raise ValueError("blind pool must contain 755 rows")
    if len({row["display_id"] for row in blind}) != 755:
        raise ValueError("blind pool display IDs must be unique")
    if len({(row["query_id"], row["chunk_id"]) for row in blind}) != 755:
        raise ValueError("blind pool query/chunk pairs must be unique")
    if any(row["relevance_judgment"] or row["reviewer_notes"] for row in blind):
        raise ValueError("blind pool contains an existing owner label")

    qa = {row["question_id"]: row for row in qa_rows}
    chunks = {row["chunk_id"]: row for row in chunk_rows}
    documents = {row["document_id"]: row for row in document_rows}
    if len(qa) != 34 or len(chunks) != 140 or len(documents) != 22:
        raise ValueError("frozen metadata counts invalid")

    package_rows: list[dict[str, str]] = []
    for blind_row in blind:
        query_id = blind_row["query_id"]
        chunk_id = blind_row["chunk_id"]
        query = qa.get(query_id)
        chunk = chunks.get(chunk_id)
        if query is None or chunk is None:
            raise ValueError(f"blind row references unknown frozen ID: {blind_row['display_id']}")
        document = documents.get(chunk["document_id"])
        if document is None:
            raise ValueError(f"chunk references unknown document: {chunk_id}")
        if blind_row["question"] != query["question"]:
            raise ValueError(f"blind question differs from R5: {query_id}")
        if blind_row["chunk_text"] != chunk["text"]:
            raise ValueError(f"blind chunk differs from frozen corpus: {chunk_id}")
        package_rows.append(
            {
                "candidate_chunk": chunk["text"],
                "chunk_id": chunk_id,
                "display_id": blind_row["display_id"],
                "query_id": query_id,
                "question": query["question"],
                "rationale": "",
                "reference_answer": query["reference_answer"],
                "relevance_grade": "",
                "source_document_title": document["title"],
            }
        )

    write_bytes(PACKAGE, csv_bytes(package_rows), overwrite=overwrite)
    summary = {
        "allowed_grades_after_separate_owner_authorization": ["2", "1", "0", "U"],
        "blank_grade_n": 755,
        "blank_rationale_n": 755,
        "package_row_n": 755,
        "query_n": 34,
        "schema_version": 1,
        "status": "offline_blank_package_frozen_before_owner_judging",
    }
    integrity = {
        "allowed_input_hashes": {
            str(path.relative_to(ROOT)): digest
            for path, digest in EXPECTED_HASHES.items()
        },
        "checks": {
            "blind_order_preserved": [row["display_id"] for row in blind]
            == [row["display_id"] for row in package_rows],
            "candidate_text_matches_frozen_chunks": all(
                row["candidate_chunk"] == chunks[row["chunk_id"]]["text"]
                for row in package_rows
            ),
            "every_grade_blank": all(not row["relevance_grade"] for row in package_rows),
            "every_rationale_blank": all(not row["rationale"] for row in package_rows),
            "questions_match_r5": all(
                row["question"] == qa[row["query_id"]]["question"]
                for row in package_rows
            ),
            "reference_answers_match_r5": all(
                row["reference_answer"] == qa[row["query_id"]]["reference_answer"]
                for row in package_rows
            ),
            "source_titles_match_documents": all(
                row["source_document_title"]
                == documents[chunks[row["chunk_id"]]["document_id"]]["title"]
                for row in package_rows
            ),
        },
        "agreement_calculated": False,
        "api_or_network_calls": 0,
        "existing_owner_labels_read": False,
        "generation_performed": False,
        "hypothesis_tests_calculated": False,
        "owner_judging_performed": False,
        "provenance_files_accessed": False,
        "relevance_metrics_calculated": False,
        "schema_version": 1,
        "status": "passed",
    }
    if not all(integrity["checks"].values()):
        raise ValueError("Phase 6 package integrity check failed")
    commands = {
        "deterministic_rebuild": [
            "python",
            "scripts/build_phase6_blind_judging_package.py",
            "--overwrite",
        ],
        "schema_version": 1,
    }
    write_json(OUTPUT / "package_summary.json", summary, overwrite=overwrite)
    write_json(OUTPUT / "commands.json", commands, overwrite=overwrite)
    write_json(AUDIT / "package_integrity.json", integrity, overwrite=overwrite)

    manifest_paths = sorted(
        list(EXPECTED_HASHES)
        + [
            PACKAGE,
            OUTPUT / "package_summary.json",
            OUTPUT / "commands.json",
            AUDIT / "package_integrity.json",
            AUDIT / "package_generation_approval.json",
            ROOT / "docs/PHASE6_BLIND_JUDGING_PACKAGE_PROTOCOL.md",
            ROOT / "scripts/build_phase6_blind_judging_package.py",
            ROOT / "tests/test_phase6_blind_judging_package.py",
        ]
    )
    manifest = {
        "artifact_hashes": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in manifest_paths
        },
        "artifact_n": len(manifest_paths),
        "base_commit": BASE_COMMIT,
        "manifest_self_hash_excluded": True,
        "owner_judging_performed": False,
        "package_row_n": 755,
        "schema_version": 1,
        "status": "phase6_blank_judging_package_frozen",
    }
    write_json(AUDIT / "freeze_manifest.json", manifest, overwrite=overwrite)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(stable_json(build(overwrite=args.overwrite)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
