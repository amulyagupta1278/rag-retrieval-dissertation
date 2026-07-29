"""Validate machine-readable discovery of all canonical pilot retrieval systems."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runs/CANONICAL_EVIDENCE.json"
EXPECTED_SYSTEMS = {
    "bm25",
    "faiss_windowed_max",
    "graph_v3_2",
    "hybrid_rrf",
    "prompt_rag_claude",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_registry_exposes_five_hash_verified_rankings() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    assert registry["status"] == "canonical_five_system_pilot_evidence_registry"
    assert registry["canonical_system_count"] == 5
    assert set(registry["systems"]) == EXPECTED_SYSTEMS
    assert registry["pending_systems"]["rule_router"]["status"] == (
        "pending_no_canonical_run_or_score"
    )

    for system, record in registry["systems"].items():
        ranking_path = ROOT / record["ranking_path"]
        assert ranking_path.is_file(), system
        assert _sha256(ranking_path) == record["ranking_sha256"], system

        rows = [
            json.loads(line)
            for line in ranking_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 34, system
        assert len({row["query_id"] for row in rows}) == 34, system
        observed_depths = [len(row["ranking"]) for row in rows]
        assert record["requested_ranking_depth"] == 50, system
        assert min(observed_depths) == record["observed_min_depth"], system
        assert max(observed_depths) == record["observed_max_depth"], system
        assert all(depth <= record["requested_ranking_depth"] for depth in observed_depths), system


def test_registry_metrics_cover_same_five_systems() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    metrics_record = registry["canonical_metrics"]
    metrics_path = ROOT / metrics_record["path"]

    assert _sha256(metrics_path) == metrics_record["sha256"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert set(metrics) == EXPECTED_SYSTEMS
    assert {record["metric_key"] for record in registry["systems"].values()} == set(metrics)


def test_unversioned_root_directories_are_explicitly_noncanonical() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    legacy = registry["legacy_unversioned_directories"]

    assert set(legacy) == {"runs/metrics", "runs/retrieval"}
    assert all("not canonical V2 pilot" in description for description in legacy.values())
