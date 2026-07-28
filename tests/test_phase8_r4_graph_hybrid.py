"""Fresh-index contracts for Phase 8 R4 Graph and Hybrid runs."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/phase8_r4_improvements"
OUT = RUN / "retrieval/graph_hybrid_v4"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_graph_index_matches_r4_corpus() -> None:
    chunks = rows(RUN / "corpus/chunks_section_aware_450w.jsonl")
    config = load(OUT / "index/config.json")
    retrieval = load(OUT / "retrieval_config.json")
    assert len(chunks) == 954
    assert config["provenance"]["num_chunks"] == 954
    assert config["nodes"] == 3781
    assert config["edges"] == 26430
    assert retrieval == {
        "dual_entity_coverage": True,
        "entity_model": "en_core_web_sm",
        "hop_decay": 0.5,
        "hub_penalty": True,
        "lexical_fallback": True,
        "max_hop": 2,
        "max_seeds": 5,
        "min_entity_freq": 2,
        "relation_window": 2,
        "seed_filtering": True,
        "use_aliases": True,
    }


def test_graph_and_hybrid_runs_have_exact_matching_coverage() -> None:
    graph = rows(OUT / "graph_run.jsonl")
    equal = rows(OUT / "hybrid_equal_bm25_graph_run.jsonl")
    weighted = rows(OUT / "hybrid_weighted_run.jsonl")
    assert len(graph) == len(equal) == len(weighted) == 120
    ids = {row["query_id"] for row in graph}
    assert ids == {row["query_id"] for row in equal} == {row["query_id"] for row in weighted}
    known = {row["chunk_id"] for row in rows(RUN / "corpus/chunks_section_aware_450w.jsonl")}
    for run in (graph, equal, weighted):
        assert all(len(row["results"]) <= 50 for row in run)
        assert all({result["chunk_id"] for result in row["results"]} <= known for row in run)
        assert all([result["rank"] for result in row["results"]] == list(range(1, len(row["results"]) + 1)) for row in run)


def test_fresh_graph_improves_old_graph_but_bm25_remains_best() -> None:
    metrics = load(OUT / "metrics.json")
    baseline = load(RUN / "retrieval/offline_experiments.json")
    old_graph = baseline["baseline_test"]["graph"]
    graph = metrics["graph"]["test"]
    bm25 = baseline["section_aware_bm25"]["test"]
    weighted = metrics["hybrid_weighted_bm25_faiss_graph"]["test"]
    assert metrics["graph"]["empty_result_query_n"] == 0
    assert graph["mrr@10"] > old_graph["mrr@10"]
    assert graph["recall@10"] > old_graph["recall@10"]
    assert graph["ndcg@10"] > old_graph["ndcg@10"]
    assert graph == {"mrr@10": 0.457917, "recall@10": 0.6625, "ndcg@10": 0.46277}
    assert weighted == {"mrr@10": 0.59375, "recall@10": 0.85, "ndcg@10": 0.624515}
    assert weighted["recall@10"] == bm25["recall@10"]
    assert weighted["mrr@10"] < bm25["mrr@10"]
    assert weighted["ndcg@10"] < bm25["ndcg@10"]


def test_hybrid_selection_used_dev_only_and_preserved_warning() -> None:
    metrics = load(OUT / "metrics.json")
    selection = metrics["hybrid_weighted_bm25_faiss_graph"]["selection"]
    assert selection == {
        "dev": {"mrr@10": 0.622798, "recall@10": 0.858333, "ndcg@10": 0.655764},
        "faiss_weight": 0.25,
        "graph_only_factor": 0.0,
        "graph_weight": 0.1,
        "k": 10,
    }
    assert "60-query dev split only" in metrics["selection_policy"]
    assert "pending human validation" in metrics["warning"]
