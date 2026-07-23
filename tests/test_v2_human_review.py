from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path


def module():
    path = Path(__file__).parents[1] / "scripts/review_v2_benchmark.py"
    spec = importlib.util.spec_from_file_location("review_v2_benchmark", path)
    loaded = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(loaded)
    return loaded


def test_review_spec_resolves_all_original_ids_and_categories():
    review = module()
    assert len(review.REVIEWS) == 34
    assert [row[0] for row in review.REVIEWS] == [f"v2q-{i:03d}" for i in range(1, 35)]
    counts = {category: sum(row[1] == category for row in review.REVIEWS) for category in {
        "exact_lookup", "terminology", "paraphrase", "entity_relation", "multi_hop", "synthesis"}}
    assert counts == {"exact_lookup": 6, "terminology": 6, "paraphrase": 6,
                      "entity_relation": 6, "multi_hop": 6, "synthesis": 4}


def test_review_spec_structural_evidence_requirements():
    review = module()
    for _, category, question, answer, evidence, bridge in review.REVIEWS:
        assert question.endswith("?") and answer.endswith(".")
        assert len(evidence) >= (3 if category == "synthesis" else 2 if category == "multi_hop" else 1)
        assert bool(bridge) == (category == "multi_hop")


def test_frozen_review_artifacts_resolve_and_match_hashes():
    root = Path(__file__).parents[1]
    review = module()
    qa_path = root / "data/v2/pilot/qa" / f"{review.VERSION}.jsonl"
    qrels_path = root / "data/v2/pilot/qrels" / f"{review.VERSION}.jsonl"
    chunks = {x["chunk_id"]: x for x in map(json.loads, (root / "data/v2/pilot/chunks/chunks.jsonl").read_text().splitlines())}
    qa = [json.loads(x) for x in qa_path.read_text().splitlines()]
    qrels = [json.loads(x) for x in qrels_path.read_text().splitlines()]
    assert len(qa) == 34 and all(x["benchmark_version"] == review.VERSION and x["review_status"] == "reviewed" for x in qa)
    assert {(x["question_id"], cid) for x in qa for cid in x["gold_evidence_ids"]} == {
        (x["query_id"], x["chunk_id"]) for x in qrels}
    assert len(qrels) == 48 and {x["relevance"] for x in qrels} == {2}
    for item in qa:
        for chunk_id, quote in zip(item["gold_evidence_ids"], item["supporting_evidence_quotes"], strict=True):
            assert chunks[chunk_id]["text"] == quote
    freeze = json.loads((root / "audits/phase1/human_review/freeze_manifest.json").read_text())
    assert hashlib.sha256(qa_path.read_bytes()).hexdigest() == freeze["qa_sha256"]
    assert hashlib.sha256(qrels_path.read_bytes()).hexdigest() == freeze["qrels_sha256"]
