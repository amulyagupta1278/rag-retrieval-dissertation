"""Offline tests for Phase 7 V2 remaining-160 full runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_phase7_v2_full_panel as runner
from src.generation.phase7_v2_freeze import MODEL


def response(index: int, request: dict | None = None) -> dict:
    context = json.loads(request["messages"][0]["content"]) if request else {"evidence": []}
    evidence_ids = [row["evidence_id"] for row in context["evidence"]]
    payload = (
        {
            "abstained": False,
            "abstention_reason": "",
            "answer": f"Supported answer [{evidence_ids[0]}].",
            "cited_evidence_ids": [evidence_ids[0]],
        }
        if evidence_ids
        else {
            "abstained": True,
            "abstention_reason": "No evidence supplied.",
            "answer": "",
            "cited_evidence_ids": [],
        }
    )
    return {
        "content": [{"text": json.dumps(payload), "type": "text"}],
        "id": f"msg_phase7_full_{index}",
        "model": MODEL,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def test_preflight_reuses_ten_and_leaves_exact_160() -> None:
    frozen = runner.preflight()
    assert len(frozen["trace_coverage"]) == 10
    assert len(frozen["remaining"]) == 160
    assert frozen["projected_initial_usd"] == pytest.approx(1.085833)
    trace_ids = {row["blinded_request_id"] for row in frozen["trace_coverage"]}
    remaining_ids = {row["blinded_request_id"] for row in frozen["remaining"]}
    assert trace_ids.isdisjoint(remaining_ids)


def test_mock_full_dispatches_only_160_and_covers_170(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = runner.preflight()
    monkeypatch.setattr(runner, "FULL_ROOT", tmp_path / "full_v2")
    calls: list[dict] = []

    def send(request: dict) -> dict:
        ledger = json.loads((runner.FULL_ROOT / "sealed/ledger.json").read_text())
        assert ledger["attempted_request_n"] == len(calls) + 1
        assert ledger["status"] == "attempt_counted_before_dispatch"
        calls.append(request)
        return response(len(calls), request)

    assert runner.run_full(frozen, sender=send) == 0
    assert len(calls) == 160
    coverage = [
        json.loads(line)
        for line in (runner.FULL_ROOT / "sealed/coverage_manifest.jsonl").read_text().splitlines()
    ]
    assert len(coverage) == len({row["blinded_request_id"] for row in coverage}) == 170
    assert sum(row["source"] == "trace_v2_reuse" for row in coverage) == 10
    assert sum(row["source"] == "full_v2_new" for row in coverage) == 160
    assert sum(row["dispatched_in_full_run"] is True for row in coverage) == 160


def test_terminal_failure_stops_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = runner.preflight()
    monkeypatch.setattr(runner, "FULL_ROOT", tmp_path / "full_v2")
    calls = 0

    def fail(_request: dict) -> dict:
        nonlocal calls
        calls += 1
        raise ConnectionError("must not be retained")

    assert runner.run_full(frozen, sender=fail) == 76
    ledger = json.loads((runner.FULL_ROOT / "sealed/ledger.json").read_text())
    assert calls == ledger["attempted_request_n"] == 1
    assert ledger["status"] == "failed"
    assert ledger["retry_n"] == 0
    failure = next((runner.FULL_ROOT / "sealed/failures").glob("*.json"))
    assert "must not be retained" not in failure.read_text()


def test_existing_ledger_refuses_rerun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = runner.preflight()
    monkeypatch.setattr(runner, "FULL_ROOT", tmp_path / "full_v2")
    runner.FULL_ROOT.joinpath("sealed").mkdir(parents=True)
    runner.FULL_ROOT.joinpath("sealed/ledger.json").write_text("{}\n")
    with pytest.raises(runner.FullPanelContractError, match="already exists"):
        runner.run_full(frozen, sender=lambda request: response(1))
