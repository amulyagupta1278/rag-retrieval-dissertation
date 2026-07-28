"""Synthetic-only tests for provider-neutral Phase 7 generation scaffold."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.generation.phase7_context import Phase7ContextError, serialize_context
from src.generation.phase7_contract import (
    FAILURE_CLASSES,
    AttemptLedger,
    Phase7ContractError,
    Phase7ProviderFailure,
    validate_response,
    write_record_once,
)
from src.generation.phase7_mock_provider import MockPhase7Provider
from src.generation.phase7_panel import SYSTEM_IDS, Phase7PanelError, build_panel


def _panel_inputs() -> tuple[list[dict[str, str]], dict[str, dict[str, list[str]]]]:
    questions = [
        {"query_id": f"q{index:02d}", "question": f"Synthetic question {index}?"}
        for index in range(1, 35)
    ]
    rankings = {
        system: {row["query_id"]: [f"chunk-{row['query_id']}-1"] for row in questions}
        for system in SYSTEM_IDS
    }
    return questions, rankings


def test_panel_has_170_unique_logical_request_ids() -> None:
    questions, rankings = _panel_inputs()
    panel = build_panel(questions, rankings)
    assert len(panel) == 170
    assert len({row["logical_request_id"] for row in panel}) == 170


def test_panel_rejects_missing_system() -> None:
    questions, rankings = _panel_inputs()
    rankings.pop("graph_v3_2")
    with pytest.raises(Phase7PanelError, match="retrieval system"):
        build_panel(questions, rankings)


def test_context_is_deterministic_and_blind() -> None:
    chunk_text = {"c1": "Evidence one.", "c2": "Evidence two.", "c3": "Evidence three."}
    first, mapping = serialize_context("Question?", ["c2", "c1", "c3"], chunk_text, 3)
    second, _ = serialize_context("Question?", ["c2", "c1", "c3"], chunk_text, 3)
    assert first == second
    assert mapping == {"E01": "c2", "E02": "c1", "E03": "c3"}
    payload = json.loads(first)
    assert set(payload) == {"question", "evidence"}
    serialized_keys = {key for item in payload["evidence"] for key in item}
    assert serialized_keys == {"evidence_id", "text"}


def test_context_rejects_duplicate_chunks() -> None:
    with pytest.raises(Phase7ContextError, match="duplicate"):
        serialize_context("Question?", ["c1", "c1"], {"c1": "x"}, 3)


def test_response_contract_rejects_invalid_citation() -> None:
    payload = {
        "answer": "Synthetic.",
        "cited_evidence_ids": ["E99"],
        "abstained": False,
        "abstention_reason": "",
    }
    with pytest.raises(Phase7ProviderFailure, match="invalid_citation_ids"):
        validate_response(payload, {"E01"}, "mock-v1", "mock-v1", {"input_tokens": 1, "output_tokens": 1})


def test_response_contract_rejects_model_drift_and_missing_usage() -> None:
    payload = {
        "answer": "Synthetic.",
        "cited_evidence_ids": ["E01"],
        "abstained": False,
        "abstention_reason": "",
    }
    with pytest.raises(Phase7ProviderFailure, match="model_drift"):
        validate_response(payload, {"E01"}, "mock-v1", "mock-v2", {"input_tokens": 1, "output_tokens": 1})
    with pytest.raises(Phase7ProviderFailure, match="missing_usage"):
        validate_response(payload, {"E01"}, "mock-v1", "mock-v1", None)


def test_mock_provider_supports_success_and_every_failure() -> None:
    success = MockPhase7Provider().generate({"question": "Q", "evidence": [{"evidence_id": "E01", "text": "x"}]})
    assert success["model_version"] == "mock-model-v1"
    for failure_class in sorted(FAILURE_CLASSES):
        with pytest.raises(Phase7ProviderFailure) as exc:
            MockPhase7Provider(failure_class=failure_class).generate({})
        assert exc.value.failure_class == failure_class


def test_ledger_and_output_are_idempotent(tmp_path: Path) -> None:
    ledger = AttemptLedger.empty()
    ledger.register("phase7:q01:bm25", "abc")
    with pytest.raises(Phase7ProviderFailure, match="duplicate_response"):
        ledger.register("phase7:q01:bm25", "def")
    output = tmp_path / "record.json"
    write_record_once(output, {"status": "synthetic"})
    with pytest.raises(FileExistsError):
        write_record_once(output, {"status": "replacement"})
    assert json.loads(output.read_text()) == {"status": "synthetic"}

