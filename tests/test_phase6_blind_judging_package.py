"""Checks for frozen, blank Phase 6 owner judging package."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.utils.hashing import sha256_file


ROOT = Path(__file__).parents[1]
RUN = ROOT / "runs/v2/phase6_blind_judging_package"
PACKAGE = RUN / "owner_judging_package.csv"
BLIND = ROOT / "runs/v2/phase5f_prompt_rag_pool/blind/provisional_all_systems_pool.jsonl"
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


def package_rows() -> list[dict[str, str]]:
    with PACKAGE.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_package_has_755_unique_blank_rows_and_safe_columns() -> None:
    rows = package_rows()
    assert len(rows) == 755
    assert list(rows[0]) == FIELDS
    assert len({row["display_id"] for row in rows}) == 755
    assert len({(row["query_id"], row["chunk_id"]) for row in rows}) == 755
    assert all(not row["relevance_grade"] and not row["rationale"] for row in rows)


def test_blind_order_and_display_ids_are_preserved() -> None:
    blind = jsonl(BLIND)
    package = package_rows()
    assert [row["display_id"] for row in package] == [row["display_id"] for row in blind]
    assert [(row["query_id"], row["chunk_id"]) for row in package] == [
        (row["query_id"], row["chunk_id"]) for row in blind
    ]


def test_package_contains_no_provenance_columns() -> None:
    forbidden = {
        "system",
        "source_system",
        "rank",
        "score",
        "current_gold",
        "predicted_relevance",
        "contributions",
        "lineage",
    }
    assert not (set(FIELDS) & forbidden)


def test_integrity_audit_confirms_prohibited_work_not_done() -> None:
    audit = json.loads((ROOT / "audits/phase6/package_integrity.json").read_text())
    assert audit["status"] == "passed"
    assert all(audit["checks"].values())
    assert audit["api_or_network_calls"] == 0
    assert audit["provenance_files_accessed"] is False
    assert audit["existing_owner_labels_read"] is False
    assert audit["owner_judging_performed"] is False
    assert audit["agreement_calculated"] is False
    assert audit["relevance_metrics_calculated"] is False
    assert audit["hypothesis_tests_calculated"] is False
    assert audit["generation_performed"] is False


def test_summary_stops_before_owner_judging() -> None:
    summary = json.loads((RUN / "package_summary.json").read_text())
    assert summary == {
        "allowed_grades_after_separate_owner_authorization": ["2", "1", "0", "U"],
        "blank_grade_n": 755,
        "blank_rationale_n": 755,
        "package_row_n": 755,
        "query_n": 34,
        "schema_version": 1,
        "status": "offline_blank_package_frozen_before_owner_judging",
    }


def test_freeze_manifest_hashes_every_artifact() -> None:
    manifest = json.loads((ROOT / "audits/phase6/freeze_manifest.json").read_text())
    assert manifest["status"] == "phase6_blank_judging_package_frozen"
    assert manifest["package_row_n"] == 755
    assert manifest["owner_judging_performed"] is False
    assert manifest["manifest_self_hash_excluded"] is True
    assert manifest["artifact_n"] == len(manifest["artifact_hashes"])
    for relative, digest in manifest["artifact_hashes"].items():
        assert sha256_file(ROOT / relative) == digest


def test_builder_references_only_approved_input_paths() -> None:
    source = (ROOT / "scripts/build_phase6_blind_judging_package.py").read_text().casefold()
    assert "/sealed/" not in source
    assert "/qrels/" not in source
    assert "owner_judgments.csv" not in source
    assert "/metrics/" not in source
    assert "api_key" not in source


def test_deterministic_rebuild_command_is_frozen() -> None:
    commands = json.loads((RUN / "commands.json").read_text())
    assert commands["deterministic_rebuild"] == [
        "python",
        "scripts/build_phase6_blind_judging_package.py",
        "--overwrite",
    ]
