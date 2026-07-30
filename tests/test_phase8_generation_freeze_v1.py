"""Phase 8 five-system answer-generation freeze contracts."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import scripts.run_phase8_generation_trace as runner
from src.generation.phase7_v2_freeze import request_sha256


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "runs/phase8_exploratory_five_system/generation_freeze_v1"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_panel_is_deterministic_balanced_and_complete() -> None:
    config = load(FREEZE / "execution_config.json")
    sealed = rows(FREEZE / "sealed/request_plan.jsonl")
    assert config["base_commit"] == "811c9a0b507f6ac154bb08542dd9ca37988c8e3f"
    assert config["query_n"] == 20
    assert config["system_n"] == 5
    assert config["request_n"] == len(sealed) == 100
    assert config["category_counts"] == {
        "entity_relation": 4,
        "exact_match": 4,
        "multi_hop": 4,
        "paraphrase": 4,
        "terminology_heavy": 4,
    }
    assert "no synthesis" in config["category_limitation"]
    assert Counter(row["system_id"] for row in sealed) == Counter({system: 20 for system in config["system_ids"]})
    assert len({row["blinded_request_id"] for row in sealed}) == 100


def test_every_context_is_first_three_of_frozen_top_ten() -> None:
    for row in rows(FREEZE / "sealed/request_plan.jsonl"):
        assert len(row["top10_chunk_ids"]) == 10
        assert len(set(row["top10_chunk_ids"])) == 10
        assert row["context_chunk_ids"] == row["top10_chunk_ids"][:3]
        assert list(row["evidence_id_to_chunk_id"]) == ["E01", "E02", "E03"]


def test_requests_are_exact_and_blinded() -> None:
    payloads = rows(FREEZE / "blinded/request_payloads.jsonl")
    forbidden = ("system_id", "retrieval_system", "reference_answer", "gold_evidence", "qrel", "question_category", "retrieval_score")
    assert len(payloads) == 100
    for row in payloads:
        assert request_sha256(row["request"]) == row["request_sha256"]
        text = json.dumps(row["request"], sort_keys=True).lower()
        assert not any(term in text for term in forbidden)
        assert row["request"]["model"] == "claude-haiku-4-5-20251001"
        assert row["request"]["temperature"] == 0
        assert row["request"]["max_tokens"] == 512
        assert row["request"]["tools"] == []


def test_trace_covers_all_systems_and_available_categories() -> None:
    trace = load(FREEZE / "sealed/trace_plan.json")["selected"]
    assert len(trace) == 5
    assert len({row["system_id"] for row in trace}) == 5
    assert len({row["category"] for row in trace}) == 5


def test_cost_gates_and_stop_state() -> None:
    config = load(FREEZE / "execution_config.json")
    cost = load(FREEZE / "cost_plan.json")
    assert cost["trace_worst_case_including_reserve_usd"] <= cost["trace_hard_cap_usd"] == 0.10
    assert cost["full_worst_case_usd"] + cost["ambiguous_dispatch_reserve_usd"] <= cost["full_hard_cap_usd"] == 1.25
    assert config["retry_n"] == 0
    assert config["execution_authorized"] is False
    assert config["full_execution_authorized"] is False
    frozen = runner.preflight(require_approval=False)
    assert len(frozen["rows"]) == 5


def test_manifest_hashes_verify_and_no_calls_recorded() -> None:
    manifest = load(FREEZE / "freeze_manifest.json")
    assert manifest["live_api_calls_n"] == 0
    for section in ("inputs", "artifacts", "code"):
        for relative, expected in manifest[section].items():
            assert sha(ROOT / relative) == expected
