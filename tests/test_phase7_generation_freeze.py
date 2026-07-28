"""Offline validity tests for frozen Phase 7 Claude top-3 design."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from src.generation.phase7_contract import write_record_once
from src.generation.phase7_freeze import (
    FAILURE_CLASSES,
    HARD_COST_CAP_USD,
    MODEL,
    Phase7ExecutionFailure,
    build_request,
    enforce_cost_cap,
    request_sha256,
    response_schema,
    select_trace,
    validate_answer_payload,
    validate_provider_response,
)


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/v2/phase7_generation_claude_top3"
AUDIT = ROOT / "audits/phase7_generation"
EXPECTED_RANKINGS = {
    "bm25": "93b42dc121927561bf880cbe44ccf264c60bac1196adac08ce3d6d5e80d2db6a",
    "faiss_windowed_max": "7e419626d2e7d00efaedfa9f1ce0dda01760dbce5c901b214e992e32df597115",
    "graph_v3_2": "68ad05ff4b600fa549f957b4bd44579af7e9d6addc2ddebff3f71a4584adc59a",
    "hybrid_rrf": "6570030a1c12edb38ff5c4e33b5dedb5d2fa83a05aa9a01ecd768bcf4edce249",
    "prompt_rag_claude": "e665aa4dc80b468a0fc2af06173ab0e6963786a578653c9a9083e6ffa6b1e04f",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(item) for item in value))
    return set()


def provider_response(payload: dict, *, model: str = MODEL, stop_reason: str = "end_turn") -> dict:
    return {
        "content": [{"text": json.dumps(payload), "type": "text"}],
        "id": "msg_phase7_test",
        "model": model,
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def test_dependency_gate_and_hashes_are_exact() -> None:
    dependency = json.loads((RUN / "dependency_manifest.json").read_text())
    assert dependency["approved_phase6_commit"] == (
        "c9af2cfbd0cc49fa0935611a71a7b64cf261a68d"
    )
    assert dependency["status"] == "verified"
    assert dependency["dependency_gate"]["status"] == "OPEN"
    assert dependency["final_label_sha256"] == (
        "ee5f4c6731117001ff92be01489e859b43ab14a6bda6bcfc8b0bce16ca94f77c"
    )
    assert dependency["final_qrels_sha256"] == (
        "c167689e5f0a1e7412d17baab56c6789e1612bb08121255fc0c153fecd1e077f"
    )
    assert {key: item["sha256"] for key, item in dependency["rankings"].items()} == (
        EXPECTED_RANKINGS
    )
    for item in [
        dependency["dependency_gate"],
        dependency["final_labels"],
        dependency["final_qrels"],
        dependency["questions"],
        dependency["chunks"],
        *dependency["rankings"].values(),
    ]:
        assert sha256(ROOT / item["path"]) == item["sha256"]


def test_panel_has_exact_170_unique_pairs() -> None:
    rows = jsonl(RUN / "sealed/request_plan.jsonl")
    assert len(rows) == len({row["logical_request_id"] for row in rows}) == 170
    assert len({(row["query_id"], row["system_id"]) for row in rows}) == 170
    assert len({row["query_id"] for row in rows}) == 34
    assert Counter(row["system_id"] for row in rows) == Counter(
        {system_id: 34 for system_id in EXPECTED_RANKINGS}
    )
    assert all(row["execution_status"] == "frozen_not_executed" for row in rows)
    assert all(row["response_hash"] is None for row in rows)


def test_blinded_contexts_and_requests_exclude_hidden_metadata() -> None:
    contexts = jsonl(RUN / "blinded/serialized_contexts.jsonl")
    payloads = jsonl(RUN / "blinded/request_payloads.jsonl")
    assert len(contexts) == len(payloads) == 170
    assert {row["blinded_request_id"] for row in contexts} == {
        row["blinded_request_id"] for row in payloads
    }
    forbidden = {
        "category",
        "gold_chunk_ids",
        "metrics",
        "owner_grade",
        "qrels",
        "rank",
        "reference_answer",
        "retrieval_score",
        "retrieval_system",
        "score",
        "system_id",
    }
    for context_row, payload_row in zip(contexts, payloads):
        context = json.loads(context_row["serialized_context"])
        assert set(context) == {"evidence", "question"}
        assert nested_keys(context).isdisjoint(forbidden)
        assert nested_keys(payload_row).isdisjoint(forbidden)
        assert payload_row["request"]["messages"][0]["content"] == (
            context_row["serialized_context"]
        )
        assert hashlib.sha256(context_row["serialized_context"].encode()).hexdigest() == (
            context_row["context_sha256"]
        )


def test_context_evidence_is_exact_frozen_top3_in_order() -> None:
    chunks = {
        row["chunk_id"]: row["text"]
        for row in jsonl(ROOT / "data/v2/pilot/chunks/chunks.jsonl")
    }
    ranking_paths = {
        "bm25": ROOT / "runs/v2/phase2a_r5_windowed/rankings/bm25_top50.jsonl",
        "faiss_windowed_max": ROOT
        / "runs/v2/phase2a_r5_windowed/rankings/faiss_windowed_max_top50.jsonl",
        "graph_v3_2": ROOT
        / "runs/v2/phase3_graph_v3_2/rankings/graph_v3_2_top50.jsonl",
        "hybrid_rrf": ROOT / "runs/v2/phase4_hybrid/rankings/hybrid_top50.jsonl",
        "prompt_rag_claude": ROOT
        / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/complete_primary_rankings.jsonl",
    }
    rankings = {
        system: {
            row["query_id"]: [item["chunk_id"] for item in row["ranking"]]
            for row in jsonl(path)
        }
        for system, path in ranking_paths.items()
    }
    contexts = {
        row["blinded_request_id"]: json.loads(row["serialized_context"])
        for row in jsonl(RUN / "blinded/serialized_contexts.jsonl")
    }
    for row in jsonl(RUN / "sealed/request_plan.jsonl"):
        expected_ids = rankings[row["system_id"]][row["query_id"]][:3]
        assert list(row["evidence_id_to_chunk_id"].values()) == expected_ids
        context = contexts[row["blinded_request_id"]]
        assert [item["text"] for item in context["evidence"]] == [
            chunks[chunk_id] for chunk_id in expected_ids
        ]


def test_context_and_request_serialization_is_deterministic() -> None:
    contexts = {
        row["blinded_request_id"]: row
        for row in jsonl(RUN / "blinded/serialized_contexts.jsonl")
    }
    prompt = (RUN / "prompt.txt").read_text()
    schema = json.loads((RUN / "response_schema.json").read_text())
    for row in jsonl(RUN / "blinded/request_payloads.jsonl"):
        rebuilt = build_request(
            prompt=prompt,
            serialized_context=contexts[row["blinded_request_id"]][
                "serialized_context"
            ],
            schema=schema,
        )
        assert rebuilt == row["request"]
        assert request_sha256(rebuilt) == row["request_sha256"]


def test_prompt_and_schema_hashes_are_frozen() -> None:
    config = json.loads((RUN / "execution_config.json").read_text())
    assert sha256(RUN / "prompt.txt") == config["prompt"]["sha256"] == (
        "90ef2de64eb650ccd3cc7e2c9273743d63c36c3d166971e36206ae427ee4a2db"
    )
    assert sha256(RUN / "response_schema.json") == config["response_schema"][
        "sha256"
    ]
    schema = json.loads((RUN / "response_schema.json").read_text())
    assert schema == response_schema()
    assert schema["additionalProperties"] is False
    unsupported = {"maxLength", "minItems", "minLength", "uniqueItems"}
    assert nested_keys(schema).isdisjoint(unsupported)


def test_answer_schema_and_citation_validation_fail_closed() -> None:
    valid = {
        "abstained": False,
        "abstention_reason": "",
        "answer": "Supported fact [E01].",
        "cited_evidence_ids": ["E01"],
    }
    assert validate_answer_payload(valid, available_evidence_ids={"E01", "E02"}) == valid
    with pytest.raises(Phase7ExecutionFailure) as invalid:
        validate_answer_payload(
            {**valid, "cited_evidence_ids": ["E99"]},
            available_evidence_ids={"E01"},
        )
    assert invalid.value.failure_class == "invalid_citation"
    with pytest.raises(Phase7ExecutionFailure, match="duplicate"):
        validate_answer_payload(
            {**valid, "cited_evidence_ids": ["E01", "E01"]},
            available_evidence_ids={"E01"},
        )
    with pytest.raises(Phase7ExecutionFailure):
        validate_answer_payload(
            {**valid, "answer": "Uncited fact."}, available_evidence_ids={"E01"}
        )


def test_abstention_and_optional_claim_mapping_contract() -> None:
    abstention = {
        "abstained": True,
        "abstention_reason": "Evidence is insufficient.",
        "answer": "",
        "cited_evidence_ids": [],
    }
    assert validate_answer_payload(abstention, available_evidence_ids=set()) == abstention
    mapped = {
        "abstained": False,
        "abstention_reason": "",
        "answer": "Supported fact [E01].",
        "cited_evidence_ids": ["E01"],
        "claim_to_evidence": [{"claim": "Supported fact", "evidence_ids": ["E01"]}],
    }
    assert validate_answer_payload(mapped, available_evidence_ids={"E01"}) == mapped


def test_provider_model_drift_truncation_and_missing_usage_stop() -> None:
    valid = {
        "abstained": False,
        "abstention_reason": "",
        "answer": "Supported fact [E01].",
        "cited_evidence_ids": ["E01"],
    }
    assert validate_provider_response(
        provider_response(valid), available_evidence_ids={"E01"}
    )["model"] == MODEL
    cases = [
        (provider_response(valid, model="claude-haiku-alias"), "model_drift"),
        (provider_response(valid, stop_reason="max_tokens"), "truncation"),
        ({**provider_response(valid), "usage": None}, "missing_usage"),
        ({**provider_response(valid), "id": None}, "missing_response"),
    ]
    for response, expected in cases:
        with pytest.raises(Phase7ExecutionFailure) as failure:
            validate_provider_response(response, available_evidence_ids={"E01"})
        assert failure.value.failure_class == expected


def test_trace_is_exact_sha_selection_with_required_coverage() -> None:
    rows = jsonl(RUN / "sealed/request_plan.jsonl")
    expected = select_trace(rows)
    trace = json.loads((RUN / "sealed/trace_plan.json").read_text())
    assert [row["logical_request_id"] for row in trace["selected"]] == [
        row["logical_request_id"] for row in expected
    ]
    assert trace["request_n"] == 10
    assert trace["system_n"] == 5
    assert trace["category_n"] == 5
    assert trace["context_length_distinct_n"] == 9


def test_zero_retry_failure_and_model_policies_are_frozen() -> None:
    config = json.loads((RUN / "execution_config.json").read_text())
    failure = json.loads((RUN / "failure_contract.json").read_text())
    assert config["retry_n"] == failure["automatic_retries"] == 0
    assert config["model"] == MODEL
    assert config["returned_model_policy"] == "exact_match_only"
    assert config["generation"]["tools"] == []
    assert config["execution_enabled"] is False
    assert set(failure["failure_classes"]) == set(FAILURE_CLASSES)
    assert failure["fallback_model"] is None
    assert failure["failed_output_replacement_allowed"] is False


def test_evaluator_and_h5_are_frozen_before_outputs() -> None:
    evaluator = json.loads((RUN / "evaluator_protocol.json").read_text())
    h5 = json.loads((RUN / "h5_protocol.json").read_text())
    audit_ids = evaluator["owner_audit"]["blinded_request_ids"]
    assert len(audit_ids) == len(set(audit_ids)) == 26
    assert evaluator["owner_audit"]["seed"] == 42
    assert evaluator["ai_judge_calls_authorized"] is False
    assert h5["bootstrap"] == {
        "paired_whole_query": True,
        "samples": 10000,
        "seed": 42,
    }
    assert h5["holm_correction"] is True
    assert h5["causal_claim_allowed"] is False
    assert h5["universal_winner_claim_allowed"] is False


def test_cost_cap_is_conservative_and_fails_closed() -> None:
    cost = json.loads((RUN / "cost_plan.json").read_text())
    assert cost["trace"]["request_n"] == 10
    assert cost["remaining_after_trace"]["request_n"] == 160
    assert cost["full_panel"]["request_n"] == 170
    assert cost["hard_cap_usd"] == HARD_COST_CAP_USD
    assert cost["cumulative_worst_case_usd"] <= HARD_COST_CAP_USD
    assert cost["hard_cap_pass"] is True
    assert cost["cache_discount_assumed"] is False
    assert cost["token_counting"]["network_token_count_endpoint_used"] is False
    enforce_cost_cap(HARD_COST_CAP_USD)
    with pytest.raises(Phase7ExecutionFailure) as failure:
        enforce_cost_cap(HARD_COST_CAP_USD + 0.000001)
    assert failure.value.failure_class == "cost_cap_breach"


def test_completed_output_cannot_be_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "response.json"
    write_record_once(path, {"status": "complete"})
    with pytest.raises(FileExistsError):
        write_record_once(path, {"status": "replacement"})


def test_freeze_manifest_verifies_all_references() -> None:
    manifest = json.loads((RUN / "freeze_manifest.json").read_text())
    for group in ("artifacts", "code", "dependency_hashes"):
        for relative, expected in manifest[group].items():
            assert sha256(ROOT / relative) == expected
    assert manifest["live_api_calls_n"] == 0
    assert manifest["execution_authorized"] is False


def test_freeze_readiness_records_no_execution_or_credentials() -> None:
    readiness = json.loads((AUDIT / "freeze_readiness.json").read_text())
    assert readiness["status"] == "ready_for_owner_trace_approval"
    assert readiness["api_calls_n"] == 0
    assert readiness["credential_access_n"] == 0
    assert readiness["generation_outputs_n"] == 0
    assert readiness["execution_authorized"] is False
