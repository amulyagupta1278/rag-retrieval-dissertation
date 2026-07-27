"""Checks for Phase 6 owner judging package.

Lifecycle note (2026-07-27):
  Phase 6 owner judging is COMPLETE. The package CSV now carries final
  adjudicated grades (0=572, 1=88, 2=95). Two tests below that asserted
  the pre-judging blank state have been formally retired in-place; their
  assertions are replaced with a skip and an explicit rationale so the
  historical expectation remains readable. The blank-state evidence is
  preserved in owner_judging_package_snapshot.csv (SHA
  d02c08df6cfc5a43dedfbbcd3248e199671c067654f8971cae63f2342c2faaf8).
  Historical manifest hash mismatches are documented in
  audits/phase6/freeze_manifest.json and must NOT be silently rewritten.
"""

from __future__ import annotations

import csv
import json
import pytest
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


@pytest.mark.skip(
    reason=(
        "RETIRED 2026-07-27: asserted pre-judging blank state. "
        "Phase 6 judging is complete; grades 0=572/1=88/2=95 are now present. "
        "Blank-state evidence preserved in owner_judging_package_snapshot.csv "
        "(SHA d02c08df6cfc5a43dedfbbcd3248e199671c067654f8971cae63f2342c2faaf8). "
        "Structural assertions (row count, field names, unique IDs) remain live "
        "in test_package_structure_post_judging below."
    )
)
def test_package_has_755_unique_blank_rows_and_safe_columns() -> None:
    rows = package_rows()
    assert len(rows) == 755
    assert list(rows[0]) == FIELDS
    assert len({row["display_id"] for row in rows}) == 755
    assert len({(row["query_id"], row["chunk_id"]) for row in rows}) == 755
    assert all(not row["relevance_grade"] and not row["rationale"] for row in rows)


def test_package_structure_post_judging() -> None:
    """Live replacement: structural checks that survive post-judging state."""
    rows = package_rows()
    assert len(rows) == 755
    assert list(rows[0]) == FIELDS
    assert len({row["display_id"] for row in rows}) == 755
    assert len({(row["query_id"], row["chunk_id"]) for row in rows}) == 755
    grades = {row["relevance_grade"] for row in rows}
    assert grades <= {"0", "1", "2", "U"}, f"Unexpected grade values: {grades - {'0','1','2','U'}}"
    counts = {g: sum(1 for r in rows if r["relevance_grade"] == g) for g in ["0", "1", "2", "U"]}
    assert counts == {"0": 572, "1": 88, "2": 95, "U": 0}, f"Unexpected distribution: {counts}"


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


@pytest.mark.skip(
    reason=(
        "RETIRED 2026-07-27: asserted pre-judging manifest state "
        "('phase6_blank_judging_package_frozen', owner_judging_performed=False). "
        "Manifest now reflects post-judging freeze "
        "('phase6_owner_judging_frozen_and_adjudicated'). "
        "Historical artifact hashes in manifest point to package-generation "
        "state and intentionally do NOT match current post-judging files; "
        "this mismatch is documented by owner instruction and must not be "
        "silently rewritten. Live manifest checks are in "
        "test_freeze_manifest_post_judging below."
    )
)
def test_freeze_manifest_hashes_every_artifact() -> None:
    manifest = json.loads((ROOT / "audits/phase6/freeze_manifest.json").read_text())
    assert manifest["status"] == "phase6_blank_judging_package_frozen"
    assert manifest["package_row_n"] == 755
    assert manifest["owner_judging_performed"] is False
    assert manifest["manifest_self_hash_excluded"] is True
    assert manifest["artifact_n"] == len(manifest["artifact_hashes"])
    for relative, digest in manifest["artifact_hashes"].items():
        assert sha256_file(ROOT / relative) == digest


def test_freeze_manifest_post_judging() -> None:
    """Live replacement: manifest checks valid for post-judging frozen state."""
    manifest = json.loads((ROOT / "audits/phase6/freeze_manifest.json").read_text())
    assert manifest["phase6_status"] == "phase6_owner_judging_frozen_and_adjudicated"
    assert manifest["owner_judging_performed"] is True
    assert manifest["adjudication_performed"] is True
    assert manifest["total_rows"] == 755
    assert manifest["final_grade_distribution"] == {"0": 572, "1": 88, "2": 95, "U": 0}
    assert manifest["phase7_gate"] == "OPEN"
    assert manifest["intra_rater_agreement"] == pytest.approx(0.9823, abs=1e-4)


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
