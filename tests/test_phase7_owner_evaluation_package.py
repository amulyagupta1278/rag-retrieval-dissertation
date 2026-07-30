import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluation_v1"
AUDIT = ROOT / "audits/phase7_generation/v2/evaluation_v1/freeze_manifest.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_mechanical_summary_covers_full_panel():
    summary = load(RUN / "mechanical_summary.json")
    assert summary["record_n"] == 170
    assert summary["schema_valid_n"] == 170
    assert summary["citation_ids_valid_n"] == 170
    assert summary["generation_failure_n"] == 0


def test_owner_package_matches_frozen_26_ids_and_has_blank_scores():
    frozen = load(ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluator_protocol.json")
    package = load(RUN / "owner_audit_package.json")
    rows = package["rows"]
    assert [row["blinded_request_id"] for row in rows] == frozen["owner_audit"]["blinded_request_ids"]
    assert len(rows) == 26
    for row in rows:
        assert "system_id" not in row
        assert "logical_request_id" not in row
        assert row["correctness"] is None
        assert row["faithfulness"] is None
        assert row["completeness"] is None
        assert row["citation_accuracy"] is None


def test_freeze_records_no_ai_labels_or_api_calls():
    manifest = load(AUDIT)
    assert manifest["api_calls_n"] == 0
    assert manifest["ai_assigned_quality_labels_n"] == 0
    assert manifest["status"] == "frozen_pending_owner_quality_audit"
