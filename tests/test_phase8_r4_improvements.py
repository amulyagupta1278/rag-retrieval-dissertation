"""Integrity and result contracts for offline Phase 8 R4 improvements."""

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/phase8_r4_improvements"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_corpus_audit_and_balanced_rechunk() -> None:
    audit = load(RUN / "corpus/corpus_quality_audit.json")
    chunks = rows(RUN / "corpus/chunks_section_aware_450w.jsonl")
    assert audit["document_n"] == 130
    assert audit["chunk_n"] == 856
    assert audit["exact_duplicate_document_n"] == 0
    assert audit["near_duplicate_pair_n"] == 1
    assert audit["noise_candidate_n"] == 10
    assert len(chunks) == 954
    assert len({row["chunk_id"] for row in chunks}) == 954
    assert max(row["word_count"] for row in chunks) == 450
    assert sum(row["word_count"] < 100 for row in chunks) == 13
    assert all(row["section_title"] and "—" in row["text"] for row in chunks)


def test_crosswalk_and_synthesis_candidates_are_complete_but_not_human_validated() -> None:
    crosswalk = rows(RUN / "corpus/gold_chunk_crosswalk.jsonl")
    synthesis = rows(RUN / "benchmark/synthesis_candidates_20.jsonl")
    assert len(crosswalk) == 140
    assert min(row["reference_answer_coverage"] for row in crosswalk) >= 0.5
    assert all(row["status"] == "automatic_pending_human_validation" for row in crosswalk)
    assert len(synthesis) == 20
    assert all(row["category"] == "synthesis" for row in synthesis)
    assert all(len(row["source_doc_ids"]) >= 2 and len(row["gold_evidence_ids"]) >= 2 for row in synthesis)
    assert all(row["review_status"] == "automated_candidate_pending_human_validation" for row in synthesis)


def test_split_is_category_stratified_and_locked() -> None:
    qa = rows(RUN / "benchmark/qa_dev_test.jsonl")
    assert Counter(row["split"] for row in qa) == {"dev": 60, "test": 40}
    for category in {row["category"] for row in qa}:
        subset = [row for row in qa if row["category"] == category]
        assert Counter(row["split"] for row in subset) == {"dev": 12, "test": 8}


def test_r4_bm25_improves_locked_test_baseline() -> None:
    metrics = load(RUN / "retrieval/offline_experiments.json")
    baseline = metrics["baseline_test"]["bm25"]
    improved = metrics["section_aware_bm25"]["test"]
    assert metrics["section_aware_bm25"]["selection"]["k1"] == 1.2
    assert metrics["section_aware_bm25"]["selection"]["b"] == 0.75
    assert improved["mrr@10"] > baseline["mrr@10"]
    assert improved["recall@10"] > baseline["recall@10"]
    assert improved["ndcg@10"] > baseline["ndcg@10"]
    assert improved == {"mrr@10": 0.607083, "recall@10": 0.85, "ndcg@10": 0.641178}


def test_fusion_candidate_pool_and_faiss_results() -> None:
    metrics = load(RUN / "retrieval/offline_experiments.json")
    assert metrics["weighted_bm25_faiss"]["test"]["recall@10"] == 0.8125
    assert metrics["graph_guarded"]["selected"]["graph_only_factor"] == 0.0
    assert metrics["prompt_rag_candidate_pool"]["bm25_faiss_union_top25_candidate_recall"] == 0.88
    faiss = load(RUN / "retrieval/faiss_cosine/metrics.json")
    assert faiss["normalize_embeddings"] is True
    assert faiss["similarity"] == "cosine"
    assert faiss["test"] == {"mrr@10": 0.411349, "recall@10": 0.6625, "ndcg@10": 0.441349}


def test_manifest_verifies_and_preserves_gates() -> None:
    manifest = load(RUN / "manifest.json")
    assert manifest["baseline_preserved"] is True
    assert manifest["counts"] == {"documents": 130, "old_chunks": 856, "new_section_aware_chunks": 954, "queries": 100, "synthesis_candidates": 20, "mapped_qrels": 140}
    assert manifest["gates"] == {"human_validation_complete": False, "new_faiss_index_run": True, "new_graph_index_run": False, "prompt_rag_api_calls": 0, "final_test_claim_authorized": False}
    for section in ("inputs", "outputs", "code"):
        for relative, expected in manifest[section].items():
            assert sha(ROOT / relative) == expected
