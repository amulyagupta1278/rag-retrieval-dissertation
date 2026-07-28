"""Integrity tests for frozen Phase 5F Prompt-RAG pool contribution."""

from __future__ import annotations

import json
from pathlib import Path

from src.utils.hashing import sha256_file


ROOT = Path(__file__).parents[1]
RUN = ROOT / "runs/v2/phase5f_prompt_rag_pool"
OLD_BLIND = ROOT / "runs/v2/phase4_hybrid/pool/provisional_blind_top10_bm25_faiss_graph_hybrid.jsonl"
OLD_SEALED = ROOT / "runs/v2/phase4_hybrid/pool/sealed_provenance_bm25_faiss_graph_hybrid.jsonl"
RANKINGS = ROOT / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/complete_primary_rankings.jsonl"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_counts_and_deduplication() -> None:
    design = json.loads((RUN / "pool_design.json").read_text())
    assert design["existing_pair_count"] == 620
    assert design["prompt_rag_top10_pair_count"] == 340
    assert design["prompt_rag_unseen_pair_count"] == 135
    assert design["final_pair_count"] == 755
    final = rows(RUN / "blind/provisional_all_systems_pool.jsonl")
    assert len(final) == 755
    assert len({(row["query_id"], row["chunk_id"]) for row in final}) == 755
    safe_fields = {
        "chunk_id",
        "chunk_text",
        "display_id",
        "query_id",
        "question",
        "relevance_judgment",
        "reviewer_notes",
    }
    assert all(set(row) == safe_fields for row in final)
    assert all(not row["relevance_judgment"] and not row["reviewer_notes"] for row in final)


def test_existing_pool_rows_are_byte_identical_after_blind_interleave() -> None:
    old_blind = OLD_BLIND.read_bytes().splitlines(keepends=True)
    old_sealed = OLD_SEALED.read_bytes().splitlines(keepends=True)
    final_blind = (RUN / "blind/provisional_all_systems_pool.jsonl").read_bytes().splitlines(keepends=True)
    final_sealed = (RUN / "sealed/provisional_all_systems_provenance.jsonl").read_bytes().splitlines(keepends=True)
    assert sha256_file(OLD_BLIND) == "5c424b6a0bbca1343499621c5fd705a904eaf11c1109824c3ec6094c0dc643e2"
    assert sha256_file(OLD_SEALED) == "f15084529a8def018747947f2d48ea14a626ddcb75e1930e19927b759bf3e1fa"
    assert len(set(old_blind)) == len(old_blind) == 620
    assert len(set(old_sealed)) == len(old_sealed) == 620
    assert set(old_blind).issubset(set(final_blind))
    assert set(old_sealed).issubset(set(final_sealed))
    assert final_blind[:620] != old_blind


def test_blind_contribution_has_only_owner_safe_fields() -> None:
    contribution = rows(RUN / "blind/prompt_rag_unseen_contribution.jsonl")
    expected = {
        "chunk_id",
        "chunk_text",
        "display_id",
        "query_id",
        "question",
        "relevance_judgment",
        "reviewer_notes",
    }
    assert len(contribution) == 135
    assert all(set(row) == expected for row in contribution)
    assert all(not row["relevance_judgment"] and not row["reviewer_notes"] for row in contribution)
    serialized = "\n".join(json.dumps(row, sort_keys=True) for row in contribution).casefold()
    assert "prompt_rag" not in serialized
    assert "claude" not in serialized
    assert "source_system" not in serialized
    assert '"rank"' not in serialized
    assert '"score"' not in serialized
    assert "current_gold" not in serialized
    assert "predicted_relevance" not in serialized


def test_every_new_pair_is_frozen_top10_and_absent_from_old_pool() -> None:
    old_pairs = {(row["query_id"], row["chunk_id"]) for row in rows(OLD_BLIND)}
    rankings = rows(RANKINGS)
    top10 = {
        (row["query_id"], item["chunk_id"])
        for row in rankings
        for item in row["ranking"][:10]
    }
    contribution = rows(RUN / "blind/prompt_rag_unseen_contribution.jsonl")
    new_pairs = {(row["query_id"], row["chunk_id"]) for row in contribution}
    assert len(top10) == 340
    assert len(new_pairs) == len(contribution) == 135
    assert new_pairs <= top10
    assert new_pairs.isdisjoint(old_pairs)


def test_sealed_provenance_maps_every_new_row_once() -> None:
    blind = rows(RUN / "blind/prompt_rag_unseen_contribution.jsonl")
    sealed = rows(RUN / "sealed/prompt_rag_unseen_provenance.jsonl")
    assert len(sealed) == 135
    assert {row["display_id"] for row in blind} == {row["display_id"] for row in sealed}
    assert {(row["query_id"], row["chunk_id"]) for row in blind} == {
        (row["query_id"], row["chunk_id"]) for row in sealed
    }
    assert all(row["contribution"]["source_system"] == "prompt_rag_claude_haiku_4_5_reranker" for row in sealed)
    assert all(1 <= row["contribution"]["rank"] <= 10 for row in sealed)
    assert all(isinstance(row["contribution"]["score"], int) for row in sealed)
    assert all(row["lineage"]["ranking_sha256"] == "e665aa4dc80b468a0fc2af06173ab0e6963786a578653c9a9083e6ffa6b1e04f" for row in sealed)
    frozen = {
        (query["query_id"], item["chunk_id"]): (item["rank"], item["score"])
        for query in rows(RANKINGS)
        for item in query["ranking"][:10]
    }
    for row in sealed:
        contribution = row["contribution"]
        assert (contribution["rank"], contribution["score"]) == frozen[
            (row["query_id"], row["chunk_id"])
        ]
        assert sha256_file(ROOT / row["lineage"]["source_record_path"]) == row["lineage"]["source_record_sha256"]


def test_integrity_audit_forbids_relevance_work_and_network() -> None:
    audit = json.loads((RUN / "integrity_audit.json").read_text())
    assert audit["status"] == "passed"
    assert all(audit["checks"].values())
    assert audit["forbidden_inputs_read"] == []
    assert audit["network_or_api_calls"] == 0
    assert audit["relevance_metrics_calculated"] is False
    assert audit["preserved_execution_evidence_modified"] is False
    assert audit["wrapper_correction"]["active_committed_wrapper_found"] is False
    assert audit["wrapper_correction"]["safe_exit_variable_for_documented_command"] == "run_exit"


def test_freeze_manifest_hashes_all_artifacts() -> None:
    manifest = json.loads((ROOT / "audits/phase5f/freeze_manifest.json").read_text())
    assert manifest["status"] == "phase5f_offline_artifacts_frozen"
    assert manifest["manifest_self_hash_excluded"] is True
    assert manifest["owner_judging_performed"] is False
    assert manifest["relevance_metrics_included"] is False
    assert manifest["generation_performed"] is False
    assert manifest["artifact_n"] == len(manifest["artifact_hashes"])
    for relative, digest in manifest["artifact_hashes"].items():
        assert sha256_file(ROOT / relative) == digest


def test_builder_has_no_relevance_or_judgment_file_dependency() -> None:
    source = (ROOT / "scripts/build_phase5f_prompt_rag_pool.py").read_text()
    assert "/qrels/" not in source.casefold()
    assert "data/v2/pilot/qrels" not in source.casefold()
    assert "owner_judgments.csv" not in source
    assert "reference_answer" not in source
    assert "metrics/" not in source
    assert "status=$?" not in source
    commands = json.loads((RUN / "commands.json").read_text())
    assert commands["deterministic_rebuild"] == [
        "python",
        "scripts/build_phase5f_prompt_rag_pool.py",
        "--overwrite",
    ]
    assert "run_exit=$?" in commands["safe_zsh_wrapper"]
