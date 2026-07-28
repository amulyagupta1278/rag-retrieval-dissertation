"""Integrity tests for successful Phase 7 V2 trace checkpoint."""

from __future__ import annotations

import json
from pathlib import Path

from src.generation.phase7_v2_freeze import MODEL, validate_provider_response
from src.utils.atomic_io import stable_json
from src.utils.hashing import sha256_file, sha256_text


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/v2/phase7_generation_claude_top3_v2"
TRACE = RUN / "trace_v2"
AUDIT = ROOT / "audits/phase7_generation/v2/trace_v2_success_checkpoint.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_checkpoint_hashes_counts_and_scope() -> None:
    audit = load(AUDIT)
    paths = {
        "ledger": TRACE / "sealed/ledger.json",
        "operational_summary": TRACE / "operational_summary.json",
        "reuse_manifest": TRACE / "sealed/reuse_manifest.jsonl",
        "trace_manifest": TRACE / "trace_manifest.json",
    }
    assert {name: sha256_file(path) for name, path in paths.items()} == audit["hashes"]
    ledger = load(paths["ledger"])
    summary = load(paths["operational_summary"])
    assert ledger["status"] == "complete"
    assert ledger["attempted_request_n"] == 10
    assert len(ledger["completed_blinded_request_ids"]) == 10
    assert ledger["retry_n"] == 0
    assert summary["successful_request_n"] == 10
    assert summary["full_panel_executed"] is False
    assert audit["full_panel_executed"] is False


def test_all_raw_responses_validate_against_exact_frozen_context() -> None:
    payloads = {
        row["blinded_request_id"]: row
        for row in jsonl(RUN / "blinded/request_payloads.jsonl")
    }
    raw_paths = sorted((TRACE / "blinded/raw_responses").glob("*.json"))
    answer_paths = sorted((TRACE / "blinded/validated_answers").glob("*.json"))
    assert len(raw_paths) == len(answer_paths) == 10
    response_ids: set[str] = set()
    for raw_path in raw_paths:
        blinded_id = raw_path.stem
        request = payloads[blinded_id]["request"]
        context = json.loads(request["messages"][0]["content"])
        available_ids = [item["evidence_id"] for item in context["evidence"]]
        raw = load(raw_path)
        validated = validate_provider_response(
            raw,
            available_evidence_ids=available_ids,
        )
        assert validated["model"] == MODEL
        assert raw["stop_reason"] == "end_turn"
        assert validated["usage"]["output_tokens"] <= 512
        assert validated["response_id"] not in response_ids
        response_ids.add(validated["response_id"])
        answer = load(TRACE / f"blinded/validated_answers/{blinded_id}.json")
        assert answer["answer"] == validated["answer"]
        assert answer["response_sha256"] == sha256_text(stable_json(raw))


def test_reuse_manifest_requires_exact_frozen_request_hashes() -> None:
    payloads = {
        row["blinded_request_id"]: row
        for row in jsonl(RUN / "blinded/request_payloads.jsonl")
    }
    reuse = jsonl(TRACE / "sealed/reuse_manifest.jsonl")
    assert len(reuse) == 10
    for row in reuse:
        assert row["reusable_in_v2_panel"] is True
        assert row["frozen_panel_request_sha256"] == payloads[
            row["blinded_request_id"]
        ]["request_sha256"]
    assert not (TRACE / "sealed/failures").exists()


def test_trace_manifest_maps_every_execution_artifact() -> None:
    manifest = load(TRACE / "trace_manifest.json")
    actual = {
        str(path.relative_to(TRACE)): sha256_file(path)
        for path in TRACE.rglob("*")
        if path.is_file() and path.name != "trace_manifest.json"
    }
    assert manifest["artifacts"] == actual
    assert len(actual) == 23
