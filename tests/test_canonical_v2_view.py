"""Integrity contracts for consolidated canonical V2 pilot view."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "runs/canonical_v2_pilot"
EXPECTED_SYSTEMS = {
    "bm25",
    "faiss_windowed_max",
    "graph_v3_2",
    "hybrid_rrf",
    "prompt_rag_claude",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_consolidated_view_is_byte_identical_to_frozen_sources() -> None:
    manifest = json.loads((VIEW / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["status"] == "canonical_v2_pilot_consolidated_view"
    assert manifest["system_count"] == 5
    assert manifest["historical_sources_modified"] is False
    assert manifest["artifact_count"] == len(manifest["copies"]) == 24

    for record in manifest["copies"]:
        source = ROOT / record["source_path"]
        destination = ROOT / record["destination_path"]
        assert source.is_file(), record["source_path"]
        assert destination.is_file(), record["destination_path"]
        assert source.read_bytes() == destination.read_bytes(), record["destination_path"]
        assert _sha256(source) == _sha256(destination) == record["sha256"]


def test_consolidated_view_exposes_five_rankings_and_complete_metrics() -> None:
    ranking_names = {path.stem.removesuffix("_top50") for path in (VIEW / "retrieval").glob("*.jsonl")}
    assert ranking_names == EXPECTED_SYSTEMS

    metrics = json.loads((VIEW / "metrics/balanced_metrics.json").read_text(encoding="utf-8"))
    assert set(metrics) == EXPECTED_SYSTEMS
    assert (VIEW / "metrics/final_pooled_per_query.jsonl").is_file()
    assert (VIEW / "metrics/efficiency_snapshot.json").is_file()
    assert (VIEW / "statistics/preregistered_h1_h4_results.json").is_file()


def test_retriever_code_registry_resolves_every_declared_path() -> None:
    registry = json.loads((ROOT / "src/retrievers/SYSTEMS.json").read_text(encoding="utf-8"))
    assert registry["status"] == "canonical_v2_pilot_retriever_code_registry"
    assert set(registry["systems"]) == EXPECTED_SYSTEMS

    for system, record in registry["systems"].items():
        assert (ROOT / record["canonical_runner"]).is_file(), system
        assert (ROOT / record["configuration_evidence"]).is_file(), system
        assert record["core_modules"], system
        assert all((ROOT / path).is_file() for path in record["core_modules"]), system
