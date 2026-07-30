from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "audits/lifecycle_supersessions/expected_failures.json"
PHASE4_HEAD = "70de0fd17f825ca04527c7ff50f91a2e5959a084"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def phase4_checkpoint() -> tuple[int, str]:
    raw = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "-z", PHASE4_HEAD], cwd=ROOT
    )
    paths = sorted(part.decode("utf-8") for part in raw.split(b"\0") if part)
    manifest = hashlib.sha256()
    for relative in paths:
        manifest.update(relative.encode("utf-8"))
        manifest.update(b"\0")
        path = ROOT / relative
        digest = sha256(path) if path.is_file() else "MISSING"
        manifest.update(digest.encode("ascii"))
        manifest.update(b"\n")
    return len(paths), manifest.hexdigest()


def test_supersession_registry_evidence_hashes() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert len(registry["supersessions"]) == 17
    for entry in registry["supersessions"].values():
        assert entry["reason"]
        for relative, expected in entry["evidence"].items():
            assert sha256(ROOT / relative) == expected


def test_supersession_node_ids_reference_live_test_functions() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for nodeid in registry["supersessions"]:
        relative, function = nodeid.split("::", 1)
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert f"def {function}(" in source


def test_current_phase4_checkpoint_is_explicitly_recorded() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entry = registry["supersessions"][
        "tests/test_phase5a_prompt_rag.py::"
        "test_hypotheses_and_protected_phase4_checkpoint_are_unchanged"
    ]
    assert phase4_checkpoint() == (
        entry["current_checkpoint_file_n"],
        entry["current_checkpoint_sha256"],
    )


def test_phase5d_lifecycle_is_approved_and_complete() -> None:
    approvals = (
        "audits/phase5d_v2/trace_execution_approval.json",
        "audits/phase5d_v2_full/full_execution_approval.json",
        "audits/phase5d_v3_recovery/live_execution_approval.json",
    )
    assert all(
        json.loads((ROOT / path).read_text())["status"] == "owner_approved"
        for path in approvals
    )
    trace = json.loads(
        (ROOT / "runs/v2/phase5d_prompt_rag_claude_v2/trace/control/ledger.json").read_text()
    )
    recovery = json.loads(
        (
            ROOT
            / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/control/ledger.json"
        ).read_text()
    )
    assert trace["attempted_generation_request_n"] == 24
    assert trace["status"] == "complete"
    assert recovery["attempted_generation_request_n"] == 26
    assert recovery["status"] == "complete"
    assert recovery["cumulative_recorded_observed_cost_usd"] < recovery["cumulative_hard_cap_usd"]


def test_phase5d_environment_drift_remains_fail_closed_and_documented() -> None:
    record = json.loads(
        (ROOT / "audits/lifecycle_supersessions/phase5d_environment_drift.json").read_text()
    )
    manifest = json.loads((ROOT / "audits/phase5d_v2/freeze_manifest.json").read_text())
    assert record["historical_expected_pyproject_sha256"] == manifest["artifact_hashes"]["pyproject.toml"]
    assert record["current_pyproject_sha256"] == sha256(ROOT / "pyproject.toml")
    assert record["historical_expected_pyproject_sha256"] != record["current_pyproject_sha256"]
    assert record["hash_bypass_added"] is False
    assert record["historical_artifact_modified"] is False


def test_phase6_superseding_seed42_freeze_is_valid() -> None:
    freeze = json.loads(
        (ROOT / "audits/phase6_seed42/freeze/freeze_manifest.json").read_text()
    )
    integrity = json.loads(
        (ROOT / "audits/phase6_seed42/freeze/integrity_audit.json").read_text()
    )
    assert freeze["status"] == "frozen"
    assert freeze["historical_seed123_artifacts_modified"] is False
    assert integrity["status"] == "passed"
    assert integrity["final_grade_counts"] == {"0": 572, "1": 89, "2": 94}
