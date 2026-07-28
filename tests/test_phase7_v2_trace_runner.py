"""Offline tests for owner-approved Phase 7 V2 trace runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_phase7_v2_generation_trace as runner
from src.generation.phase7_v2_freeze import MODEL


def response(index: int) -> dict:
    payload = {
        "abstained": False,
        "abstention_reason": "",
        "answer": "Supported answer [E01].",
        "cited_evidence_ids": ["E01"],
    }
    return {
        "content": [{"text": json.dumps(payload), "type": "text"}],
        "id": f"msg_phase7_v2_{index}",
        "model": MODEL,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def test_preflight_is_exact_and_offline() -> None:
    frozen = runner.preflight()
    assert len(frozen["rows"]) == 10
    assert all(row["request"]["max_tokens"] == 512 for row in frozen["rows"])
    assert frozen["cost"]["current_hard_cap_usd"] == 3.0


def test_mock_trace_counts_once_and_marks_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = runner.preflight()
    monkeypatch.setattr(runner, "TRACE_ROOT", tmp_path / "trace_v2")
    calls: list[dict] = []

    def send(request: dict) -> dict:
        ledger = json.loads((runner.TRACE_ROOT / "sealed/ledger.json").read_text())
        assert ledger["attempted_request_n"] == len(calls) + 1
        assert ledger["status"] == "attempt_counted_before_dispatch"
        calls.append(request)
        return response(len(calls))

    assert runner.run_trace(frozen, sender=send) == 0
    ledger = json.loads((runner.TRACE_ROOT / "sealed/ledger.json").read_text())
    assert len(calls) == ledger["attempted_request_n"] == 10
    assert ledger["status"] == "complete"
    assert ledger["retry_n"] == 0
    reuse = [
        json.loads(line)
        for line in (runner.TRACE_ROOT / "sealed/reuse_manifest.jsonl").read_text().splitlines()
    ]
    assert len(reuse) == 10
    assert all(row["reusable_in_v2_panel"] is True for row in reuse)
    summary = json.loads((runner.TRACE_ROOT / "operational_summary.json").read_text())
    assert summary["full_panel_executed"] is False


def test_terminal_failure_stops_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = runner.preflight()
    monkeypatch.setattr(runner, "TRACE_ROOT", tmp_path / "trace_v2")
    calls = 0

    def fail(_request: dict) -> dict:
        nonlocal calls
        calls += 1
        raise ConnectionError("must not be retained")

    assert runner.run_trace(frozen, sender=fail) == 76
    ledger = json.loads((runner.TRACE_ROOT / "sealed/ledger.json").read_text())
    assert calls == ledger["attempted_request_n"] == 1
    assert ledger["status"] == "failed"
    failure = next((runner.TRACE_ROOT / "sealed/failures").glob("*.json"))
    assert "must not be retained" not in failure.read_text()


def test_existing_ledger_refuses_rerun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = runner.preflight()
    monkeypatch.setattr(runner, "TRACE_ROOT", tmp_path / "trace_v2")
    runner.TRACE_ROOT.joinpath("sealed").mkdir(parents=True)
    runner.TRACE_ROOT.joinpath("sealed/ledger.json").write_text("{}\n")
    with pytest.raises(runner.TraceV2ContractError, match="already exists"):
        runner.run_trace(frozen, sender=lambda request: response(1))
