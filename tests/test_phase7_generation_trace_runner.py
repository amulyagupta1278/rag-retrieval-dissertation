"""Offline tests for owner-approved Phase 7 trace runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_phase7_generation_trace as runner
from src.generation.phase7_freeze import MODEL


def response(index: int) -> dict:
    payload = {
        "abstained": False,
        "abstention_reason": "",
        "answer": "Supported answer [E01].",
        "cited_evidence_ids": ["E01"],
    }
    return {
        "content": [{"text": json.dumps(payload), "type": "text"}],
        "id": f"msg_phase7_{index}",
        "model": MODEL,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def test_preflight_is_exact_and_offline() -> None:
    frozen = runner.preflight()
    assert len(frozen["rows"]) == 10
    assert sum(row["planned_input_token_envelope"] for row in frozen["rows"]) == 40561
    assert all(row["request"]["model"] == MODEL for row in frozen["rows"])


def test_mock_trace_counts_once_and_completes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "TRACE_ROOT", tmp_path / "trace")
    calls: list[dict] = []

    def send(request: dict) -> dict:
        ledger = json.loads((runner.TRACE_ROOT / "sealed/ledger.json").read_text())
        assert ledger["attempted_request_n"] == len(calls) + 1
        assert ledger["status"] == "attempt_counted_before_dispatch"
        calls.append(request)
        return response(len(calls))

    assert runner.run_trace(runner.preflight(), sender=send) == 0
    ledger = json.loads((runner.TRACE_ROOT / "sealed/ledger.json").read_text())
    assert len(calls) == ledger["attempted_request_n"] == 10
    assert ledger["status"] == "complete"
    assert ledger["retry_n"] == 0
    assert json.loads((runner.TRACE_ROOT / "operational_summary.json").read_text())[
        "full_panel_executed"
    ] is False


def test_terminal_failure_stops_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "TRACE_ROOT", tmp_path / "trace")
    calls = 0

    def fail(_request: dict) -> dict:
        nonlocal calls
        calls += 1
        raise ConnectionError("must not be retained")

    assert runner.run_trace(runner.preflight(), sender=fail) == 76
    ledger = json.loads((runner.TRACE_ROOT / "sealed/ledger.json").read_text())
    assert calls == ledger["attempted_request_n"] == 1
    assert ledger["status"] == "failed"
    assert ledger["billing_ambiguity"] is True
    failure = next((runner.TRACE_ROOT / "sealed/failures").glob("*.json"))
    assert "must not be retained" not in failure.read_text()


def test_existing_ledger_refuses_rerun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "TRACE_ROOT", tmp_path / "trace")
    runner.TRACE_ROOT.joinpath("sealed").mkdir(parents=True)
    runner.TRACE_ROOT.joinpath("sealed/ledger.json").write_text("{}\n")
    with pytest.raises(runner.TraceContractError, match="already exists"):
        runner.run_trace(runner.preflight(), sender=lambda request: response(1))
