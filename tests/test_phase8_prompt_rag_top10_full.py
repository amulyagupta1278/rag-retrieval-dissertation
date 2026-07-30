"""Completed cost-adapted Phase 8 Prompt-RAG full-run contracts."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "runs/phase8_exploratory_five_system/prompt_rag_top10_full"
CHECKPOINT = ROOT / "audits/phase8_exploratory/cost_safe_prompt_rag_full_success.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_full_run_complete_under_cap_without_retries() -> None:
    summary = json.loads((FULL / "full_summary.json").read_text())
    assert summary["status"] == "full_complete"
    assert summary["coverage_n"] == summary["valid_n"] == 100
    assert summary["trace_reuse_n"] == 5
    assert summary["new_request_n"] == 95
    assert summary["failure_n"] == summary["retry_n"] == 0
    assert summary["cumulative_observed_cost_usd"] == 0.904148
    assert summary["cumulative_observed_cost_usd"] < summary["cumulative_hard_cap_usd"] == 2.25


def test_full_run_artifact_hashes_verify() -> None:
    summary = json.loads((FULL / "full_summary.json").read_text())
    for relative, expected in summary["artifacts"].items():
        assert sha256(ROOT / relative) == expected


def test_full_run_has_exact_query_coverage_and_rankings() -> None:
    rows = [json.loads(line) for line in (FULL / "retrieval/prompt_rag_top10_run.jsonl").read_text().splitlines()]
    assert len(rows) == 100
    assert len({row["query_id"] for row in rows}) == 100
    assert all(len(row["results"]) == 10 for row in rows)
    assert all([result["rank"] for result in row["results"]] == list(range(1, 11)) for row in rows)


def test_metrics_and_generation_stop_gate() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text())
    assert checkpoint["metrics"] == {
        "mrr@10": 0.5866,
        "recall@10": 0.775,
        "precision@10": 0.111,
        "ndcg@10": 0.6176,
    }
    assert checkpoint["generation_calls"] == 0
    assert checkpoint["generation_authorized"] is False
    assert sha256(FULL / "full_summary.json") == checkpoint["full_summary_sha256"]
    assert sha256(FULL / "retrieval/prompt_rag_top10_run.jsonl") == checkpoint["run_sha256"]
    assert sha256(FULL / "metrics/prompt_rag_top10_metrics.csv") == checkpoint["metrics_sha256"]
    assert sha256(FULL / "ledger.json") == checkpoint["ledger_sha256"]
