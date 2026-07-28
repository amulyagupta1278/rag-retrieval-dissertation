import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluation_v1"
AUDIT = ROOT / "audits/phase7_generation/v2/evaluation_v1"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_owner_audit_complete_and_protected_fields_match():
    frozen = load(EVAL / "owner_audit_package.json")["rows"]
    completed = load(EVAL / "phase7_owner_audit_26_COMPLETED.json")["rows"]
    assert len(completed) == 26
    assert len({row["blinded_request_id"] for row in completed}) == 26
    protected = ("blinded_request_id", "question", "reference_answer", "evidence", "generated_answer", "abstained", "abstention_reason", "cited_evidence_ids")
    dimensions = ("correctness", "faithfulness", "completeness", "citation_accuracy", "unsupported_claim_severity", "abstention_quality")
    for expected, actual in zip(frozen, completed, strict=True):
        assert all(actual[field] == expected[field] for field in protected)
        assert all(type(actual[field]) is int and actual[field] in {0, 1, 2} for field in dimensions)


def test_summary_and_h5_gate_are_truthful():
    summary = load(EVAL / "owner_audit_summary.json")
    gate = load(AUDIT / "h5_gate_after_owner_audit.json")
    assert summary["owner_labeled_n"] == 26
    assert summary["score_n"] == 156
    assert summary["blank_or_invalid_score_n"] == 0
    assert gate["unlabeled_generation_n"] == 144
    assert gate["h5_executed"] is False
    assert gate["h5_gate"] == "BLOCKED_PENDING_FINALIZED_FULL_PANEL_QUALITY_LABELS"


def test_freeze_manifest_hashes():
    manifest = load(AUDIT / "owner_audit_freeze_manifest.json")
    assert manifest["ai_assigned_quality_labels_n"] == 0
    assert manifest["api_calls_n"] == 0
    for relative, expected in manifest["artifacts"].items():
        assert digest(ROOT / relative) == expected
