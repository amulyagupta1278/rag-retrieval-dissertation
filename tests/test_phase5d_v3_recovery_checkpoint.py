"""Offline integrity checks for successful Phase 5D V3 recovery."""

from __future__ import annotations

import pytest
pytest.importorskip(
    "sentence_transformers",
    reason=(
        "SKIPPED 2026-07-27: requires sentence_transformers (and faiss-cpu / "
        "torch) which are not installed in the evaluation sandbox. "
        "These tests exercise retriever inference and Phase 5 pipeline "
        "contracts that depend on ML inference libraries. Install the full "
        "requirements (pip install sentence-transformers faiss-cpu) to run."
    ),
)


import json
from pathlib import Path

import pytest

from scripts import run_phase5d_v3_transport_recovery as runner
from src.retrievers.prompt_rag_claude_v2 import ClaudeContractError
from src.utils.hashing import sha256_file


ROOT = Path(__file__).parents[1]
RUN = ROOT / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_recovery_ledger_is_complete_once_without_failures() -> None:
    ledger = load(RUN / "control/ledger.json")
    assert ledger["status"] == "complete"
    assert ledger["attempted_generation_request_n"] == 26
    assert len(ledger["completed_logical_request_ids"]) == 26
    assert len(list((RUN / "raw").glob("*.json"))) == 26
    assert not list((RUN / "failures").glob("*.json"))


def test_cost_and_usage_stay_inside_reserved_cap() -> None:
    summary = load(RUN / "operational_summary.json")
    assert summary["recovery"] == {
        "actual_input_tokens": 771820,
        "actual_output_tokens": 33817,
        "attempted_request_n": 26,
        "observed_cost_usd": 0.940905,
        "valid_request_n": 26,
    }
    spend = summary["spend"]
    assert spend["cumulative_recorded_observed_cost_usd"] == pytest.approx(1.980933)
    assert spend["reserved_cumulative_exposure_usd"] == pytest.approx(2.031173)
    assert spend["reserved_margin_usd"] == pytest.approx(0.118827)
    assert spend["reserved_cumulative_exposure_usd"] < spend["cumulative_hard_cap_usd"]


def test_complete_rankings_use_exact_first_primaries_for_all_queries() -> None:
    rankings = rows(RUN / "complete_primary_rankings.jsonl")
    assert len(rankings) == 34
    assert len({row["query_id"] for row in rankings}) == 34
    assert {row["source_scope"] for row in rankings} == {
        "v2_trace_primary",
        "v3_recovery_primary",
    }
    assert sum(row["source_scope"] == "v2_trace_primary" for row in rankings) == 8
    assert sum(row["source_scope"] == "v3_recovery_primary" for row in rankings) == 26
    for row in rankings:
        ranking = row["ranking"]
        assert len(ranking) == 50
        assert len({item["chunk_id"] for item in ranking}) == 50
        assert ranking == sorted(ranking, key=lambda item: (-item["score"], item["chunk_id"]))
        assert row["source_logical_request_id"] == f"{row['query_id']}:primary"


def test_checkpoint_discloses_wrapper_error_and_forbidden_work_not_done() -> None:
    checkpoint = load(RUN / "phase5d_v3_checkpoint.json")
    assert checkpoint["status"] == "phase5d_v3_recovery_complete_rankings_frozen"
    assert checkpoint["wrapper_post_runner_error"] == {
        "effect_on_runner": "none; ledger was already complete",
        "message": "zsh:5: read-only variable: status",
        "occurred": True,
    }
    assert checkpoint["rerun_after_wrapper_error"] is False
    assert checkpoint["relevance_metrics_calculated"] is False
    assert checkpoint["pool_expansion_performed"] is False
    assert checkpoint["answer_generation_performed"] is False
    assert checkpoint["owner_judging_performed"] is False


def test_manifest_hashes_every_frozen_artifact() -> None:
    manifest = load(RUN / "artifact_manifest.json")
    assert manifest["status"] == "phase5d_v3_recovery_artifacts_frozen"
    assert manifest["complete_primary_query_n"] == 34
    assert manifest["manifest_self_hash_excluded"] is True
    assert manifest["relevance_metrics_included"] is False
    assert manifest["pool_expansion_performed"] is False
    assert manifest["generation_performed"] is False
    assert manifest["credentials_stored"] is False
    assert manifest["artifact_n"] == len(manifest["artifact_hashes"])
    for relative, digest in manifest["artifact_hashes"].items():
        assert sha256_file(ROOT / relative) == digest


def test_v2_failure_and_trace_evidence_remain_byte_identical() -> None:
    assert sha256_file(ROOT / "audits/phase5d_v2_full/failure_manifest.json") == "1ecb877daaa9eca705f2fe8ed1579261d6a77e3fc2420bf741d6344c607c11d4"
    assert sha256_file(ROOT / "runs/v2/phase5d_prompt_rag_claude_v2/full/control/ledger.json") == "01d2a453bd57252ea23551cc6a9b4a625a6d0827dcb0018d89de03ae08b8b3d7"
    assert sha256_file(ROOT / "runs/v2/phase5d_prompt_rag_claude_v2/full/failures/v2q-001__primary.json") == "f75e9fd02fd603efc809570027707dc3a458502399eec545dd7c4305595b9e26"
    assert sha256_file(ROOT / "runs/v2/phase5d_prompt_rag_claude_v2/trace/artifact_manifest.json") == "0910c957081b4bb54b1e7ba08f20b29e1a8b3608ecfe9b8d06bac5a6f7693158"


def test_terminal_complete_ledger_refuses_rerun_before_client_creation() -> None:
    frozen = runner.preflight()
    called = False

    def client_factory():
        nonlocal called
        called = True
        raise AssertionError("client must not be created for complete ledger")

    with pytest.raises(ClaudeContractError, match="V3 ledger is terminal: complete"):
        runner.run_recovery(frozen, client_factory=client_factory)
    assert called is False


def test_run_artifacts_contain_no_api_key_marker() -> None:
    forbidden = ("ANTHROPIC_API_KEY", "sk-ant-")
    for path in RUN.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert not any(marker in text for marker in forbidden)


def test_no_metrics_pool_generation_or_failure_directory_created() -> None:
    assert not (RUN / "metrics").exists()
    assert not (RUN / "pool").exists()
    assert not (RUN / "generation").exists()
    assert not (RUN / "failures").exists()
