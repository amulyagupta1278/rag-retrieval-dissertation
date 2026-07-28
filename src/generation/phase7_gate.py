"""Fail-closed dependency gate for Phase 7 generation execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class Phase7GateError(RuntimeError):
    """Raised when any Phase 7 prerequisite is absent or inconsistent."""


REQUIRED_RANKING_IDS = {
    "bm25",
    "faiss_windowed_max",
    "graph_v3_2",
    "hybrid_rrf",
    "prompt_rag_claude",
}


def sha256_file(path: Path) -> str:
    """Return SHA-256 for *path* without changing it."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Phase7GateError(message)


def _verified_artifact(root: Path, item: dict[str, Any], label: str) -> str:
    rel = item.get("path")
    expected = item.get("sha256")
    _require(isinstance(rel, str) and rel, f"{label}: missing path")
    _require(isinstance(expected, str) and len(expected) == 64, f"{label}: invalid SHA-256")
    path = root / rel
    _require(path.is_file(), f"{label}: missing artifact {rel}")
    actual = sha256_file(path)
    _require(actual == expected, f"{label}: hash mismatch for {rel}")
    return actual


def assert_phase7_ready(manifest_path: Path, repository_root: Path) -> dict[str, Any]:
    """Validate every human-review, qrels, metrics, and ranking prerequisite.

    This function never opens benchmark answers, owner judgments, or qrels content.
    It checks explicit completion facts and cryptographic hashes only.
    """

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(manifest.get("status") == "ready_for_phase7_execution", "gate status is not ready")
    phase6 = manifest.get("phase6", {})
    _require(phase6.get("first_pass_structural_validation") is True, "first-pass validation missing")
    _require(phase6.get("human_regrade_complete") is True, "114-row human regrade missing")
    _require(phase6.get("human_regrade_row_n") == 114, "human regrade must contain 114 rows")
    _require(phase6.get("agreement_report_exists") is True, "agreement report missing")
    _require(phase6.get("unresolved_disagreement_n") == 0, "unresolved disagreements remain")
    _require(phase6.get("unresolved_u_n") == 0, "unresolved U judgments remain")

    qrels_hash = _verified_artifact(repository_root, manifest.get("final_qrels", {}), "final qrels")
    _verified_artifact(
        repository_root,
        manifest.get("phase6_retrieval_metrics", {}),
        "frozen Phase 6 retrieval metrics",
    )
    freeze_item = manifest.get("phase7_freeze_manifest", {})
    _verified_artifact(repository_root, freeze_item, "Phase 7 freeze manifest")
    freeze = json.loads((repository_root / freeze_item["path"]).read_text(encoding="utf-8"))
    _require(freeze.get("final_qrels_sha256") == qrels_hash, "final qrels hash absent from Phase 7 freeze")

    rankings = manifest.get("rankings", {})
    _require(set(rankings) == REQUIRED_RANKING_IDS, "ranking system set is incomplete or unexpected")
    for system_id in sorted(REQUIRED_RANKING_IDS):
        _verified_artifact(repository_root, rankings[system_id], f"ranking {system_id}")
    return {
        "ready": True,
        "final_qrels_sha256": qrels_hash,
        "verified_ranking_n": len(rankings),
    }

