"""Offline tests for Phase 5C trace-only evaluation contract."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.evaluate_phase5c_trace as phase5c
from src.retrievers.prompt_rag_gemini_v1 import PromptRAGContractError


ROOT = Path(__file__).parents[1]
PLAN_PATH = ROOT / "audits/phase5c/trace_plan.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_phase5c_plan_freezes_exact_scope_and_prohibitions() -> None:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    assert plan["mode"] == "trace"
    assert plan["network_scope"] == {
        "logical_request_n": 24,
        "maximum_attempted_network_request_n": 24,
        "primary_request_n": 8,
        "replicate_request_n": 16,
        "retries_consume_cap": True,
        "trace_input_tokens_offline_planned": 604005,
        "trace_maximum_contract_output_tokens": 45186,
    }
    assert plan["selected_query_ids"] == [
        "v2q-017",
        "v2q-016",
        "v2q-003",
        "v2q-023",
        "v2q-013",
        "v2q-025",
        "v2q-004",
        "v2q-027",
    ]
    assert plan["permissions"] == {
        "answer_generation": False,
        "full_26_query_execution": False,
        "owner_judging": False,
        "pool_expansion": False,
        "relevance_metric_calculation": False,
        "repeatability_metric_calculation_after_complete_trace": True,
        "trace_operational_summary_after_complete_trace": True,
    }
    assert plan["gates"]["free_plan_confirmed"] is False
    assert plan["gates"]["paid_execution_authorized"] is False


def test_phase5c_frozen_hashes_match_phase5b_contract() -> None:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    frozen = plan["frozen_inputs"]
    for path_key, hash_key in (
        ("config_path", "config_sha256"),
        ("prompt_path", "prompt_sha256"),
        ("repeatability_protocol_path", "repeatability_protocol_sha256"),
        ("request_hash_source_path", "request_hash_source_sha256"),
        ("trace_selection_path", "trace_selection_sha256"),
    ):
        assert sha256(ROOT / frozen[path_key]) == frozen[hash_key]


def test_phase5c_freeze_manifest_is_complete_and_exact() -> None:
    manifest = json.loads(
        (ROOT / "audits/phase5c/freeze_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["completeness"] == {
        "artifact_count": 14,
        "manifest_self_hash_excluded": True,
    }
    assert len(manifest["artifact_hashes"]) == 14
    assert "audits/phase5c/freeze_manifest.json" not in manifest["artifact_hashes"]
    assert not set(manifest["mutable_runtime_controls_excluded"]) & set(
        manifest["artifact_hashes"]
    )
    for relative, expected in manifest["artifact_hashes"].items():
        assert sha256(ROOT / relative) == expected, relative
    assert phase5c._verify_freeze_manifest() == manifest


def test_phase5c_evaluator_has_no_benchmark_sensitive_inputs() -> None:
    source = (ROOT / "scripts/evaluate_phase5c_trace.py").read_text(encoding="utf-8").lower()
    for forbidden in (
        "qrels",
        "reference_answer",
        "owner_judgments",
        "sealed_provenance",
        "src.evaluation",
        "compute_mrr",
        "compute_ndcg",
        "bootstrap",
    ):
        assert forbidden not in source


def test_phase5c_cli_has_fixed_paths_and_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/evaluate_phase5c_trace.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "Validate Phase 5C trace records" in completed.stdout
    with pytest.raises(SystemExit):
        phase5c.parser().parse_args(["--raw-dir", "alternate"])


@pytest.mark.parametrize(
    ("logical_id", "filename"),
    [
        ("v2q-017:primary", "v2q-017__primary.json"),
        ("v2q-017:replicate-1", "v2q-017__replicate-1.json"),
        ("v2q-017:replicate-2", "v2q-017__replicate-2.json"),
    ],
)
def test_logical_filename_is_canonical(logical_id: str, filename: str) -> None:
    assert phase5c._logical_filename(logical_id) == filename
    with pytest.raises(PromptRAGContractError):
        phase5c._logical_filename("../v2q-017:primary")


def test_percentile_uses_frozen_linear_interpolation() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert phase5c._percentile(values, 0.5) == 2.5
    assert phase5c._percentile(values, 0.95) == pytest.approx(3.85)
    with pytest.raises(PromptRAGContractError):
        phase5c._percentile([], 0.5)


def test_provider_usage_is_strict_and_missing_optional_counts_become_zero() -> None:
    usage = phase5c._usage(
        {
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 25,
                "totalTokenCount": 125,
            }
        }
    )
    assert usage == {
        "cached_input_tokens": 0,
        "input_tokens": 100,
        "output_tokens": 25,
        "thinking_tokens": 0,
        "total_tokens": 125,
    }
    with pytest.raises(PromptRAGContractError, match="input_tokens"):
        phase5c._usage({"usageMetadata": {"candidatesTokenCount": 25, "totalTokenCount": 25}})


def test_idempotent_writer_rejects_changed_output(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    phase5c._write_exact(path, {"b": 2, "a": 1})
    original = path.read_bytes()
    phase5c._write_exact(path, {"a": 1, "b": 2})
    assert path.read_bytes() == original
    with pytest.raises(PromptRAGContractError, match="collision"):
        phase5c._write_exact(path, {"a": 9})


def _attempt(index: int) -> dict:
    return {
        "attempt": 1,
        "ended_at": f"2026-07-26T10:{index:02d}:01+00:00",
        "error_class": None,
        "finish_reason": "STOP",
        "http_status": 200,
        "model_version": "gemini-2.5-flash-001",
        "request_sha256": f"request-{index:02d}",
        "response_id_sha256": "d" * 64,
        "response_sha256": "e" * 64,
        "retry_decision": "validate",
        "schema_failure_classification": None,
        "started_at": f"2026-07-26T10:{index:02d}:00+00:00",
        "status": "valid",
    }


def _operational_records() -> list[dict]:
    query_ids = [
        "v2q-017",
        "v2q-016",
        "v2q-003",
        "v2q-023",
        "v2q-013",
        "v2q-025",
        "v2q-004",
        "v2q-027",
    ]
    rows = []
    index = 0
    for role in ("primary", "replicate-1", "replicate-2"):
        for query_id in query_ids:
            rows.append(
                {
                    "attempts": [_attempt(index)],
                    "logical_request_id": f"{query_id}:{role}",
                    "raw_response": {
                        "usageMetadata": {
                            "promptTokenCount": 100,
                            "candidatesTokenCount": 20,
                            "thoughtsTokenCount": 0,
                            "totalTokenCount": 120,
                        }
                    },
                }
            )
            index += 1
    return rows


def test_operational_summary_reports_trace_only_observations() -> None:
    ledger = SimpleNamespace(
        state={
            "attempted_network_request_n": 24,
            "returned_model_version": "gemini-2.5-flash-001",
        }
    )
    summary = phase5c._operational_summary(_operational_records(), ledger)
    assert summary["logical_request_n"] == 24
    assert summary["attempted_network_request_n"] == 24
    assert summary["primary_query_coverage"] == {
        "expected": 8,
        "rate": 1.0,
        "successful": 8,
    }
    assert summary["latency_ms"]["sample_n"] == 24
    assert summary["latency_ms"]["mean"] == 1000.0
    assert summary["provider_usage_totals"] == {
        "cached_input_tokens": 0,
        "input_tokens": 2400,
        "output_tokens": 480,
        "thinking_tokens": 0,
        "total_tokens": 2880,
    }
    assert summary["retry_n"] == summary["terminal_failure_n"] == 0
    assert summary["monetary_cost_usd"] == 0.0


def test_repeatability_summary_preserves_all_pairwise_gate() -> None:
    thresholds = {
        "candidate_score_agreement": 0.9,
        "kendall_tau_b": 0.9,
        "ranking_position_agreement": 0.8,
        "spearman_rho": 0.95,
        "top_10_overlap": 0.9,
    }
    comparisons = [
        {
            "metrics": {name: 1.0 for name in thresholds},
            "passed": True,
        }
        for _ in range(24)
    ]
    summary = phase5c._repeatability_summary(
        {
            "comparisons": comparisons,
            "model_version": "gemini-2.5-flash-001",
            "selected_query_ids": [f"q{index}" for index in range(8)],
            "status": "repeatability_gate_passed",
            "thresholds": thresholds,
            "trace_record_n": 24,
        }
    )
    assert summary["comparison_n"] == 24
    assert summary["decision_status"] == "repeatability_gate_passed"
    assert all(
        row == {
            "all_pairwise_passed": True,
            "maximum": 1.0,
            "mean": 1.0,
            "minimum": 1.0,
            "threshold": thresholds[name],
        }
        for name, row in summary["metric_aggregates"].items()
    )


def test_evaluator_refuses_before_trace_without_creating_outputs() -> None:
    assert not phase5c.RAW_ROOT.exists()
    completed = subprocess.run(
        [sys.executable, "scripts/evaluate_phase5c_trace.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 78
    assert "raw trace directory is missing" in completed.stderr
    assert not phase5c.DECISION_PATH.exists()
