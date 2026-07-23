from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from src.benchmark.graph_path_validator import validate_graph_path_item


def test_r2_candidate_structure_and_provenance():
    root = Path(__file__).parents[1]
    r2 = [json.loads(x) for x in (root / "data/v2/pilot/qa/pilot-qa-v2-reviewed-20260724-r2.jsonl").read_text().splitlines()]
    qrels = [json.loads(x) for x in (root / "data/v2/pilot/qrels/pilot-qa-v2-reviewed-20260724-r2.jsonl").read_text().splitlines()]
    assert len(r2) == 34
    assert Counter(x["category"] for x in r2) == {"exact_lookup": 6, "terminology": 6, "paraphrase": 6,
                                                   "entity_relation": 6, "multi_hop": 6, "synthesis": 4}
    assert all(x["authoring_method"] == "ai_assisted_full_chunk_review" and x["review_status"] == "ai_reviewed_owner_pending" for x in r2)
    assert len(qrels) == 48 and {x["relevance"] for x in qrels} == {2}
    assert all(x["judgment_source"] == "ai_assisted_direct_support_review" for x in qrels)


def test_all_r2_multi_hop_paths_validate():
    root = Path(__file__).parents[1]
    r2 = [json.loads(x) for x in (root / "data/v2/pilot/qa/pilot-qa-v2-reviewed-20260724-r2.jsonl").read_text().splitlines()]
    chunks = {x["chunk_id"]: x for x in map(json.loads, (root / "data/v2/pilot/chunks/chunks.jsonl").read_text().splitlines())}
    docs = [json.loads(x) for x in (root / "data/v2/pilot/extracted/documents.jsonl").read_text().splitlines()]
    entities = {v for d in docs for v in (d["title"], d["ministry"], d["department"]) if v}
    for item in (x for x in r2 if x["category"] == "multi_hop"):
        validate_graph_path_item(item, chunks, entities)


def test_r1_hashes_remain_frozen():
    root = Path(__file__).parents[1]
    freeze = json.loads((root / "audits/phase1/human_review/freeze_manifest.json").read_text())
    import hashlib
    assert hashlib.sha256((root / freeze["qa_path"]).read_bytes()).hexdigest() == freeze["qa_sha256"]
    assert hashlib.sha256((root / freeze["qrels_path"]).read_bytes()).hexdigest() == freeze["qrels_sha256"]
