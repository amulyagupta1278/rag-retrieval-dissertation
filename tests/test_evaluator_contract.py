import json

import pytest

from src.evaluation.evaluator import RetrievalEvaluator


def _files(tmp_path):
    qa = tmp_path / "qa.jsonl"
    qa.write_text(json.dumps({"question_id": "q1", "question": "question", "split": "dev"}) + "\n", encoding="utf-8")
    qrels = tmp_path / "qrels.tsv"
    qrels.write_text("q1\t0\tc1\t1\n", encoding="utf-8")
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text(json.dumps({"chunk_id": "c1", "doc_id": "d1", "text": "evidence"}) + "\n", encoding="utf-8")
    return qa, qrels, chunks


def _run(results):
    return {
        "query_id": "q1", "query_text": "question", "retriever": "test", "top_k": 10,
        "total_latency_ms": 1.0, "results": results, "config_snapshot": {"fixture": True},
    }


def test_evaluator_rejects_duplicate_chunks_and_bad_ranks(tmp_path):
    qa, qrels, chunks = _files(tmp_path)
    run = tmp_path / "run.jsonl"
    run.write_text(json.dumps(_run([
        {"chunk_id": "c1", "rank": 1}, {"chunk_id": "c1", "rank": 2},
    ])) + "\n", encoding="utf-8")
    evaluator = RetrievalEvaluator(qrels, qa_dataset_path=qa, split="dev", chunks_path=chunks)
    with pytest.raises(ValueError, match="Duplicate retrieved chunks"):
        evaluator.evaluate_run_file(run)


def test_evaluator_rejects_unknown_chunk(tmp_path):
    qa, qrels, chunks = _files(tmp_path)
    run = tmp_path / "run.jsonl"
    run.write_text(json.dumps(_run([{"chunk_id": "unknown", "rank": 1}])) + "\n", encoding="utf-8")
    evaluator = RetrievalEvaluator(qrels, qa_dataset_path=qa, split="dev", chunks_path=chunks)
    with pytest.raises(ValueError, match="unknown chunks"):
        evaluator.evaluate_run_file(run)


def test_evaluator_rejects_missing_configuration_snapshot(tmp_path):
    qa, qrels, chunks = _files(tmp_path)
    payload = _run([{"chunk_id": "c1", "rank": 1}])
    payload.pop("config_snapshot")
    run = tmp_path / "run.jsonl"
    run.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    evaluator = RetrievalEvaluator(qrels, qa_dataset_path=qa, split="dev", chunks_path=chunks)
    with pytest.raises(ValueError, match="Missing configuration snapshot"):
        evaluator.evaluate_run_file(run)


def test_evaluator_rejects_graded_qrels(tmp_path):
    qa, qrels, chunks = _files(tmp_path)
    qrels.write_text("q1\t0\tc1\t2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Non-binary qrels"):
        RetrievalEvaluator(qrels, qa_dataset_path=qa, split="dev", chunks_path=chunks)
