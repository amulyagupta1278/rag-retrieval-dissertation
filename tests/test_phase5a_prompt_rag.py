"""Offline validity tests for the non-executable Phase 5A candidate design."""

from __future__ import annotations



import hashlib
import inspect
import json
import subprocess
from pathlib import Path

import pytest

from src.retrievers.prompt_rag_contract import (
    FORBIDDEN_INPUT_FIELDS,
    parse_and_rank_response,
    validate_model_inputs,
)


ROOT = Path(__file__).parents[1]
PHASE4_HEAD = "70de0fd17f825ca04527c7ff50f91a2e5959a084"
PHASE5A_HEAD = "d9689aeae520ed24a5f0c409a18134f5f9042e0f"
CONFIG_PATH = ROOT / "configs/prompt_rag_v1_candidate.json"
BLIND_POOL_PATH = ROOT / "runs/v2/phase4_hybrid/pool/provisional_blind_top10_bm25_faiss_graph_hybrid.jsonl"
HYPOTHESIS_PATH = ROOT / "docs/EXPERIMENT_PROTOCOL_V2.md"


def sha256(path: Path) -> str:
    """Return the lowercase SHA-256 of one file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config() -> dict:
    """Load the Phase 5A candidate configuration."""

    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def checkpoint_manifest_sha256() -> tuple[int, str]:
    """Hash every tracked file at the protected Phase 4 HEAD without parsing it."""

    raw = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "-z", PHASE4_HEAD], cwd=ROOT
    )
    paths = sorted(part.decode("utf-8") for part in raw.split(b"\0") if part)
    manifest = hashlib.sha256()
    for relative_path in paths:
        digest = sha256(ROOT / relative_path)
        manifest.update(relative_path.encode("utf-8"))
        manifest.update(b"\0")
        manifest.update(digest.encode("ascii"))
        manifest.update(b"\n")
    return len(paths), manifest.hexdigest()


def test_candidate_is_explicitly_blocked_and_non_executable() -> None:
    config = load_config()
    assert config["architecture_status"] == "blocked_owner_architecture_choice_required"
    assert config["execution_authorized"] is False
    assert config["historical_evidence_conclusion"]["unique_architecture_defined"] is False
    assert config["owner_decision_required"]["recommendation"] == "A"
    assert config["owner_decision_required"]["alternatives"][0]["status"] == "recommended_not_selected"


def test_all_execution_specific_parameters_remain_unresolved() -> None:
    unresolved = load_config()["unresolved_execution_parameters"]
    for field in (
        "api_endpoint",
        "batch_size",
        "candidate_depth",
        "candidate_generator",
        "context_window_tokens",
        "max_output_tokens",
        "model",
        "model_version",
        "provider",
        "retry_count",
        "sdk_name",
        "sdk_version",
        "seed",
        "temperature",
        "timeout_seconds",
        "top_p",
    ):
        assert unresolved[field] is None


def test_committed_phase5a_prompt_hash_matches_candidate_config() -> None:
    config = load_config()
    prompt_bytes = subprocess.check_output(
        ["git", "show", f"{PHASE5A_HEAD}:prompts/prompt_rag_retrieval_v1.txt"],
        cwd=ROOT,
    )
    prompt = prompt_bytes.decode("utf-8")
    assert hashlib.sha256(prompt_bytes).hexdigest() == config["prompt"]["sha256"]
    assert config["prompt"]["status"] == "unfrozen_non_executable_placeholder"
    assert prompt.startswith("UNFROZEN PLACEHOLDER — DO NOT SEND TO ANY MODEL OR API.")
    assert "Execution is prohibited" in prompt


def test_proposed_output_schema_is_strict_and_minimal() -> None:
    schema = load_config()["proposed_common_contract"]["output_json_schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["candidate_scores"]
    item = schema["properties"]["candidate_scores"]["items"]
    assert item["additionalProperties"] is False
    assert item["required"] == ["chunk_id", "score"]
    assert set(item["properties"]) == {"chunk_id", "score"}


def test_allowed_model_input_contract() -> None:
    validate_model_inputs(
        {"query_id": "q01", "question": "What is the rule?"},
        [{"chunk_id": "c01", "text": "Rule text", "source_title": "Scheme"}],
    )


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_INPUT_FIELDS))
def test_every_forbidden_query_input_is_rejected(forbidden: str) -> None:
    query = {"query_id": "q01", "question": "Question", forbidden: "hidden"}
    with pytest.raises(ValueError, match="forbidden fields"):
        validate_model_inputs(
            query,
            [{"chunk_id": "c01", "text": "Text", "source_title": "Title"}],
        )


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_INPUT_FIELDS))
def test_every_forbidden_candidate_input_is_rejected(forbidden: str) -> None:
    candidate = {
        "chunk_id": "c01",
        "text": "Text",
        "source_title": "Title",
        forbidden: "hidden",
    }
    with pytest.raises(ValueError, match="forbidden fields"):
        validate_model_inputs({"query_id": "q01", "question": "Question"}, [candidate])


def test_non_allowlisted_input_and_duplicate_candidates_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-allowlisted"):
        validate_model_inputs(
            {"query_id": "q01", "question": "Question", "extra": "no"},
            [{"chunk_id": "c01", "text": "Text", "source_title": "Title"}],
        )
    with pytest.raises(ValueError, match="duplicate candidate"):
        validate_model_inputs(
            {"query_id": "q01", "question": "Question"},
            [
                {"chunk_id": "c01", "text": "Text", "source_title": "Title"},
                {"chunk_id": "c01", "text": "Other", "source_title": "Title"},
            ],
        )


def test_parser_is_deterministic_and_ties_use_chunk_id_ascending() -> None:
    raw = json.dumps(
        {
            "candidate_scores": [
                {"chunk_id": "c03", "score": 0.2},
                {"chunk_id": "c02", "score": 0.9},
                {"chunk_id": "c01", "score": 0.9},
            ]
        }
    )
    first = parse_and_rank_response(raw, ["c01", "c02", "c03"])
    second = parse_and_rank_response(raw, ["c03", "c02", "c01"])
    assert first == second
    assert [row["chunk_id"] for row in first] == ["c01", "c02", "c03"]
    assert [row["rank"] for row in first] == [1, 2, 3]


@pytest.mark.parametrize(
    ("raw", "expected_ids", "message"),
    [
        ("not json", ["c01"], "invalid JSON"),
        ('{"candidate_scores": []}', ["c01"], "non-empty"),
        ('{"candidate_scores":[{"chunk_id":"c01","score":true}]}', ["c01"], "numeric"),
        ('{"candidate_scores":[{"chunk_id":"c01","score":NaN}]}', ["c01"], "finite"),
        (
            '{"candidate_scores":[{"chunk_id":"c01","score":1},{"chunk_id":"c01","score":0}]}',
            ["c01"],
            "duplicate response",
        ),
        ('{"candidate_scores":[{"chunk_id":"c01","score":1}]}', ["c01", "c02"], "mismatch"),
        ('{"candidate_scores":[{"chunk_id":"c99","score":1}]}', ["c01"], "mismatch"),
        ('{"candidate_scores":[{"chunk_id":"c01","score":1,"rank":1}]}', ["c01"], "only"),
    ],
)
def test_invalid_responses_fail_closed(raw: str, expected_ids: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_and_rank_response(raw, expected_ids)


def test_parser_has_no_retriever_fallback_path() -> None:
    source = inspect.getsource(parse_and_rank_response).lower()
    for forbidden_fallback in ("bm25", "faiss", "graph", "hybrid", "backfill"):
        assert forbidden_fallback not in source
    assert "except valueerror" not in source
    assert "return []" not in source


def test_blind_pool_has_620_unique_blank_judgments() -> None:
    rows = [json.loads(line) for line in BLIND_POOL_PATH.read_text(encoding="utf-8").splitlines()]
    pairs = {(row["query_id"], row["chunk_id"]) for row in rows}
    assert len(rows) == len(pairs) == 620
    assert all(row.get("relevance_judgment") in (None, "") for row in rows)
    assert all(row.get("reviewer_notes") in (None, "") for row in rows)
    assert all(not ({"system", "rank", "score", "gold_status"} & set(row)) for row in rows)
    assert sha256(BLIND_POOL_PATH) == "5c424b6a0bbca1343499621c5fd705a904eaf11c1109824c3ec6094c0dc643e2"


def test_hypotheses_and_protected_phase4_checkpoint_are_unchanged() -> None:
    assert sha256(HYPOTHESIS_PATH) == "78547d0fc4a81ae64303103b22f577366a0d7895d8e5dbe94b0e417e366115b7"
    count, manifest_hash = checkpoint_manifest_sha256()
    assert count == 532
    # Updated for authorized repairs plus Phase 5D Gemini dependency archival.
    assert manifest_hash == "727c2fe2553c2686f9130fbd995bee9fa43c9ccca992ec542c8fae50cd3ec7f5"


def test_history_audit_uses_only_permitted_classifications() -> None:
    audit = json.loads(
        (ROOT / "audits/phase5a/history_and_claims_audit.json").read_text(encoding="utf-8")
    )
    allowed = {
        "verified_implementation",
        "documentation_only_claim",
        "unsupported_claim",
        "obsolete_or_invalid_artifact",
    }
    assert audit["architecture_determination"]["unique_architecture_defined"] is False
    assert {finding["classification"] for finding in audit["findings"]} <= allowed
    assert audit["conclusion"]["decision"] == "stop_for_owner_architecture_choice"


def test_freeze_readiness_contains_all_20_items_and_stops_execution() -> None:
    readiness = json.loads(
        (ROOT / "audits/phase5a/freeze_readiness.json").read_text(encoding="utf-8")
    )
    assert readiness["decision"] == "not_ready_stop_for_owner_approval"
    assert readiness["execution_authorized"] is False
    assert readiness["unresolved_choices_prevent_execution"] is True
    assert len(readiness["freeze_checklist"]) == 20
    assert readiness["gates"]["metrics_before_trace_approval_prohibited"] is True


def test_planning_call_and_token_arithmetic() -> None:
    policy = json.loads(
        (ROOT / "audits/phase5a/cost_and_failure_policy.json").read_text(encoding="utf-8")
    )
    depth_50 = policy["planning_estimates"]["alternative_A_or_B_depth_50"]
    assert depth_50["candidate_judgment_n"] == 34 * 50
    assert depth_50["calls_by_batch_size"] == {"10": 170, "25": 68, "50": 34}
    assert depth_50["candidate_payload_input_token_range"] == [34 * 50 * 300, 34 * 50 * 600]
    assert policy["failure_policy"]["fallback"] == "none"
    assert policy["exact_cost_status"]["dollar_cost_available"] is False
