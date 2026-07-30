import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai"
AUDIT = ROOT / "audits/phase7_generation/v2/evaluation_v2_ai"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_label_sources_and_scores_are_explicit():
    rows = jsonl(OUT / "final_quality_labels_170.jsonl")
    assert len(rows) == 170
    assert len({row["blinded_request_id"] for row in rows}) == 170
    assert Counter(row["label_source"] for row in rows) == {"offline_ai_knn": 144, "human_owner": 26}
    dims = ("correctness", "faithfulness", "completeness", "citation_accuracy", "unsupported_claim_severity", "abstention_quality")
    assert all(type(row[dim]) is int and row[dim] in {0, 1, 2} for row in rows for dim in dims)


def test_owner_labels_override_ai_predictions():
    owner = {row["blinded_request_id"]: row for row in load(ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluation_v1/phase7_owner_audit_26_COMPLETED.json")["rows"]}
    final = {row["blinded_request_id"]: row for row in jsonl(OUT / "final_quality_labels_170.jsonl")}
    dims = ("correctness", "faithfulness", "completeness", "citation_accuracy", "unsupported_claim_severity", "abstention_quality")
    assert all(final[row_id][dim] == row[dim] for row_id, row in owner.items() for dim in dims)
    assert all(final[row_id]["label_source"] == "human_owner" for row_id in owner)


def test_h5_contract_and_manifest():
    h5 = load(OUT / "h5_results.json")
    assert h5["status"] == "complete_exploratory_ai_evaluated"
    assert h5["label_sources"] == {"human_owner": 26, "offline_ai_knn": 144}
    assert h5["bootstrap"] == {"samples": 10000, "seed": 42, "unit": "whole query preserving five-system panel"}
    assert len(h5["correlations"]) == 4
    assert all(item["query_n"] == 34 and item["record_n"] == 170 for item in h5["correlations"])
    manifest = load(AUDIT / "freeze_manifest.json")
    assert manifest["api_call_n"] == 0
    assert manifest["ai_assigned_label_n"] == 144
    for relative, expected in manifest["artifacts"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
