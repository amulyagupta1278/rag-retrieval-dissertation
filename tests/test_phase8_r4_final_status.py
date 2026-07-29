import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_r4_final_status_is_honest_and_cost_safe():
    status = json.load(open(ROOT / "audits/phase8_r4/canonical_status.json"))
    assert status["status"] == "automated_r4_complete_pending_human_validation"
    assert status["human_validation_complete"] is False
    assert status["ai_assigned_generation_labels"] == 100
    assert status["human_owner_r4_generation_labels"] == 0
    assert status["generation_valid"] == status["prompt_rag_retrieval_valid"] == 100
    assert status["cumulative_r4_api_cost_usd"] <= status["absolute_hard_cap_usd"]


def test_final_manifest_and_synthesis_separation():
    manifest = json.load(open(ROOT / "audits/phase8_r4/final_manifest.json"))
    for rel, expected in manifest["artifacts"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == expected
    synthesis = [json.loads(x) for x in open(ROOT / "runs/phase8_r4_improvements/benchmark/synthesis_candidates_20.jsonl")]
    assert len(synthesis) == 20
    assert all(row["review_status"] == "automated_candidate_pending_human_validation" for row in synthesis)


def test_r4_ai_agreement_is_not_fabricated():
    agreement = json.load(open(ROOT / "runs/phase8_r4_improvements/evaluation_ai_h5/ai_owner_agreement.json"))
    assert agreement["r4_owner_label_overlap_n"] == 0
    assert agreement["r4_ai_owner_agreement"] is None
    h5 = json.load(open(ROOT / "runs/phase8_r4_improvements/evaluation_ai_h5/h5_results.json"))
    assert h5["decision"] == "exploratory_descriptive_only"
    assert h5["label_sources"] == {"offline_ai_knn_transfer": 100, "human_owner_r4": 0}
