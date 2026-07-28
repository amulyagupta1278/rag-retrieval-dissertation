"""Integrity tests for completed Phase 7 V2 170-record generation panel."""

from __future__ import annotations

import json
from pathlib import Path

from src.generation.phase7_v2_freeze import MODEL, validate_provider_response
from src.utils.atomic_io import stable_json
from src.utils.hashing import sha256_file, sha256_text


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/v2/phase7_generation_claude_top3_v2"
FULL = RUN / "full_v2"
AUDIT = ROOT / "audits/phase7_generation/v2/full_v2_success_checkpoint.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_checkpoint_hashes_costs_and_terminal_scope() -> None:
    audit = load(AUDIT)
    paths = {
        "coverage_manifest": FULL / "sealed/coverage_manifest.jsonl",
        "full_manifest": FULL / "full_manifest.json",
        "ledger": FULL / "sealed/ledger.json",
        "operational_summary": FULL / "operational_summary.json",
    }
    assert {name: sha256_file(path) for name, path in paths.items()} == audit["hashes"]
    ledger = load(paths["ledger"])
    summary = load(paths["operational_summary"])
    assert ledger["status"] == "complete"
    assert ledger["attempted_request_n"] == len(ledger["completed_blinded_request_ids"]) == 160
    assert ledger["retry_n"] == ledger["trace_dispatch_n"] == 0
    assert summary["full_panel_coverage_n"] == 170
    assert summary["cumulative_observed_phase7_cost_usd"] == 0.52532
    assert summary["v2_full_observed_cost_usd"] == 0.486916
    assert audit["failure_n"] == 0
    assert audit["manifest_finalization_correction"]["api_calls_n"] == 0
    assert audit["manifest_finalization_correction"]["existing_execution_artifacts_overwritten"] is False


def test_coverage_is_exact_170_with_ten_reused_and_160_new() -> None:
    coverage = jsonl(FULL / "sealed/coverage_manifest.jsonl")
    payloads = {
        row["blinded_request_id"]: row
        for row in jsonl(RUN / "blinded/request_payloads.jsonl")
    }
    assert len(coverage) == len({row["blinded_request_id"] for row in coverage}) == 170
    assert len({row["logical_request_id"] for row in coverage}) == 170
    assert sum(row["source"] == "trace_v2_reuse" for row in coverage) == 10
    assert sum(row["source"] == "full_v2_new" for row in coverage) == 160
    assert sum(row["dispatched_in_full_run"] is False for row in coverage) == 10
    for row in coverage:
        assert row["request_sha256"] == payloads[row["blinded_request_id"]][
            "request_sha256"
        ]


def test_all_170_responses_revalidate_against_frozen_requests() -> None:
    coverage = jsonl(FULL / "sealed/coverage_manifest.jsonl")
    payloads = {
        row["blinded_request_id"]: row
        for row in jsonl(RUN / "blinded/request_payloads.jsonl")
    }
    response_ids: set[str] = set()
    for row in coverage:
        request = payloads[row["blinded_request_id"]]["request"]
        context = json.loads(request["messages"][0]["content"])
        available_ids = [item["evidence_id"] for item in context["evidence"]]
        raw = load(ROOT / row["raw_response_path"])
        validated = validate_provider_response(
            raw,
            available_evidence_ids=available_ids,
        )
        assert raw["model"] == MODEL
        assert raw["stop_reason"] == "end_turn"
        assert validated["usage"]["output_tokens"] <= 512
        assert validated["response_id"] not in response_ids
        response_ids.add(validated["response_id"])
        assert row["response_sha256"] == sha256_text(stable_json(raw))
        answer = load(ROOT / row["validated_answer_path"])
        assert answer["answer"] == validated["answer"]
        assert answer["response_sha256"] == row["response_sha256"]
    assert len(response_ids) == 170


def test_full_manifest_maps_all_completed_artifacts() -> None:
    manifest = load(FULL / "full_manifest.json")
    actual = {
        str(path.relative_to(FULL)): sha256_file(path)
        for path in FULL.rglob("*")
        if path.is_file() and path.name != "full_manifest.json"
    }
    assert manifest["artifacts"] == actual
    assert len(actual) == 323
    assert not (FULL / "sealed/failures").exists()
