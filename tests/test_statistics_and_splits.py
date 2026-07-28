import json

import pytest

from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.metrics import compute_all_metrics
from src.evaluation.statistics import (
    bootstrap_mean_ci, holm_bonferroni, paired_bootstrap, paired_noninferiority,
    paired_randomization_test, query_level_metrics,
)


def _run(qid, ranked):
    return {
        "query_id": qid, "retriever": "test", "total_latency_ms": 1.0,
        "top_k": max(len(ranked), 1), "query_text": f"Question {qid}",
        "config_snapshot": {"fixture": True},
        "results": [{"chunk_id": value, "rank": rank} for rank, value in enumerate(ranked, 1)],
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


def test_noninferiority_and_holm_are_deterministic():
    left = {f"q{i}": {"ndcg_at_10": 0.80} for i in range(10)}
    right = {f"q{i}": {"ndcg_at_10": 0.81} for i in range(10)}
    result = paired_noninferiority(left, right, "ndcg_at_10", margin=0.03, samples=200, seed=7)
    assert result["noninferior"] is True
    adjusted = holm_bonferroni({"H2": 0.01, "H3": 0.04})
    assert adjusted["H2"]["adjusted_p_value"] == pytest.approx(0.02)
    assert adjusted["H3"]["adjusted_p_value"] == pytest.approx(0.04)


def test_evaluator_filters_frozen_split(tmp_path):
    qa = tmp_path / "qa.jsonl"
    qa.write_text(
        json.dumps({"question_id": "q1", "question": "Question q1", "split": "dev"}) + "\n"
        + json.dumps({"question_id": "q2", "question": "Question q2", "split": "test"}) + "\n",
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
