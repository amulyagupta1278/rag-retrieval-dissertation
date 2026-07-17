import json

import pytest

from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.metrics import compute_all_metrics
from src.evaluation.statistics import (
    bootstrap_mean_ci, paired_bootstrap, paired_randomization_test, query_level_metrics,
)


def _run(qid, ranked):
    return {
        "query_id": qid, "retriever": "test", "total_latency_ms": 1.0,
        "results": [{"chunk_id": value} for value in ranked],
    }


def test_zero_relevance_judgment_is_not_treated_as_gold():
    bundle = compute_all_metrics([_run("q1", ["negative", "positive"])], {"q1": {"negative": 0, "positive": 1}}, [5])
    assert bundle.mrr == pytest.approx(0.5)


def test_query_metrics_and_paired_tests_are_deterministic():
    qrels = {"q1": {"a": 1}, "q2": {"b": 1}}
    left = query_level_metrics([_run("q1", ["a"]), _run("q2", ["x", "b"])], qrels)
    right = query_level_metrics([_run("q1", ["x", "a"]), _run("q2", ["b"])], qrels)
    assert paired_bootstrap(left, right, "mrr_at_10", samples=200, seed=7) == paired_bootstrap(left, right, "mrr_at_10", samples=200, seed=7)
    assert paired_randomization_test(left, right, "mrr_at_10", samples=200, seed=7) == paired_randomization_test(left, right, "mrr_at_10", samples=200, seed=7)
    assert bootstrap_mean_ci(left, "mrr_at_10", samples=200, seed=7)["num_queries"] == 2


def test_evaluator_filters_frozen_split(tmp_path):
    qa = tmp_path / "qa.jsonl"
    qa.write_text(
        json.dumps({"question_id": "q1", "split": "dev"}) + "\n"
        + json.dumps({"question_id": "q2", "split": "test"}) + "\n",
        encoding="utf-8",
    )
    qrels = tmp_path / "qrels.tsv"
    qrels.write_text("q1\t0\ta\t1\nq2\t0\tb\t1\n", encoding="utf-8")
    run = tmp_path / "run.jsonl"
    run.write_text(json.dumps(_run("q1", ["a"])) + "\n" + json.dumps(_run("q2", ["b"])) + "\n", encoding="utf-8")
    evaluator = RetrievalEvaluator(qrels, qa_dataset_path=qa, split="dev")
    bundles = evaluator.evaluate_run_file(run)
    assert bundles[0].num_queries == 1
    assert set(evaluator.qrels) == {"q1"}


def test_split_filter_requires_qa_dataset(tmp_path):
    qrels = tmp_path / "qrels.tsv"
    qrels.write_text("q1\t0\ta\t1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="qa_dataset_path"):
        RetrievalEvaluator(qrels, split="dev")
