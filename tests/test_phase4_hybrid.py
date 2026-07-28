"""Phase 4 frozen BM25 + corrected Graph v3.2 RRF tests."""

from __future__ import annotations



import json
import hashlib
import inspect
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.evaluate_phase4_hybrid import (
    CATEGORIES,
    LATENCY_ADDITIONAL_WARMUP_QUERY_N,
    LATENCY_EXECUTION_ORDER,
    LATENCY_MEASURED_QUERY_N,
    LATENCY_MEASURED_SAMPLE_N,
    LATENCY_REPETITIONS_PER_QUERY,
    LATENCY_VALIDATION_QUERY_N,
    measure_latency,
)
from scripts.run_phase2a_bm25_faiss import METRICS
from scripts.run_phase4_hybrid import EXPECTED_HASHES, REJECTED_GRAPH_HASHES
from src.retrievers.hybrid_rrf_v1 import (
    EXPECTED_CONFIG,
    fuse_rankings,
    validate_component_names,
    validate_config,
    validate_query_rows,
    validate_ranking,
)
from src.utils.atomic_io import stable_json
from src.utils.hashing import sha256_text


ROOT = Path(__file__).parents[1]
KNOWN = {f"c{index:02d}" for index in range(1, 60)}


def row(chunk_id: str, rank: int, score: float = 0.0) -> dict:
    return {"chunk_id": chunk_id, "rank": rank, "score": score}


def fuse(bm25: list[dict], graph: list[dict]):
    return fuse_rankings(bm25, graph, config=EXPECTED_CONFIG, known_chunk_ids=KNOWN)


def test_frozen_config_file_matches_contract() -> None:
    config = json.loads((ROOT / "configs/hybrid_rrf_v1_frozen.json").read_text(encoding="utf-8"))
    assert config == EXPECTED_CONFIG
    validate_config(config)


def test_first_in_both_outranks_first_in_only_one() -> None:
    ranking, _ = fuse([row("c01", 1), row("c02", 2)], [row("c01", 1), row("c03", 2)])
    assert ranking[0]["chunk_id"] == "c01"


def test_exact_hand_computed_scores_and_one_based_ranking() -> None:
    ranking, trace = fuse([row("c01", 1), row("c02", 2)], [row("c03", 1), row("c01", 2)])
    assert ranking[0] == {"chunk_id": "c01", "rank": 1, "score": pytest.approx(1 / 61 + 1 / 62)}
    assert trace[0]["bm25_rrf_contribution"] == pytest.approx(1 / 61)
    assert trace[0]["graph_rrf_contribution"] == pytest.approx(1 / 62)
    assert [item["rank"] for item in ranking] == list(range(1, len(ranking) + 1))


def test_equal_weights_are_required() -> None:
    config = deepcopy(EXPECTED_CONFIG)
    config["weights"]["bm25"] = 2.0
    with pytest.raises(ValueError, match="frozen"):
        validate_config(config)


def test_missing_graph_ranking_preserves_bm25_contribution() -> None:
    ranking, trace = fuse([row("c01", 1)], [])
    assert ranking == [{"chunk_id": "c01", "rank": 1, "score": pytest.approx(1 / 61)}]
    assert trace[0]["graph_rank"] is None and trace[0]["graph_rrf_contribution"] == 0


def test_empty_graph_result_handled() -> None:
    assert fuse([row("c01", 1), row("c02", 2)], [])[0]


def test_empty_bm25_result_handled() -> None:
    ranking, trace = fuse([], [row("c01", 1)])
    assert ranking[0]["chunk_id"] == "c01"
    assert trace[0]["bm25_rank"] is None and trace[0]["bm25_rrf_contribution"] == 0


def test_duplicate_chunk_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate chunk"):
        fuse([row("c01", 1), row("c01", 2)], [])


def test_duplicate_query_rejected() -> None:
    rows = [{"query_id": "q1", "ranking": []}, {"query_id": "q1", "ranking": []}]
    with pytest.raises(ValueError, match="duplicate query"):
        validate_query_rows(rows, component="bm25", known_chunk_ids=KNOWN, expected_query_ids={"q1"})


def test_mismatched_query_sets_rejected() -> None:
    with pytest.raises(ValueError, match="query-ID set"):
        validate_query_rows([{"query_id": "q1", "ranking": []}], component="bm25", known_chunk_ids=KNOWN, expected_query_ids={"q1", "q2"})


def test_unknown_chunk_rejected() -> None:
    with pytest.raises(ValueError, match="unknown chunk"):
        fuse([row("unknown", 1)], [])


def test_input_depth_50_enforced() -> None:
    ranking = [row(f"c{index:02d}", index) for index in range(1, 52)]
    with pytest.raises(ValueError, match="exceeds input depth"):
        validate_ranking(ranking, component="bm25", known_chunk_ids=KNOWN, input_depth=50)


def test_output_depth_50_enforced() -> None:
    config = deepcopy(EXPECTED_CONFIG)
    config["output_depth"] = 51
    with pytest.raises(ValueError, match="frozen"):
        validate_config(config)


def test_deterministic_chunk_id_tie_break() -> None:
    ranking, trace = fuse([row("c02", 1)], [row("c01", 1)])
    assert [item["chunk_id"] for item in ranking] == ["c01", "c02"]
    assert all(item["tie_break"] == "chunk_id_ascending" for item in trace)


def test_raw_component_scores_do_not_influence_rrf() -> None:
    first = fuse([row("c01", 1, -999)], [row("c02", 1, 999)])[0]
    second = fuse([row("c01", 1, 999)], [row("c02", 1, -999)])[0]
    assert first == second


@pytest.mark.parametrize("components", [
    ["bm25", "entity_graph_v3_1"],
    ["bm25", "phase3_graph_invalid_v1"],
])
def test_invalid_graph_v1_or_v31_component_rejected(components: list[str]) -> None:
    with pytest.raises(ValueError, match="exactly"):
        validate_component_names(components)


def test_faiss_input_rejected() -> None:
    with pytest.raises(ValueError, match="exactly"):
        validate_component_names(["bm25", "faiss_windowed_max"])


def test_three_system_input_rejected() -> None:
    with pytest.raises(ValueError, match="exactly"):
        validate_component_names(["bm25", "entity_graph_v3_2", "faiss_windowed_max"])


def test_serialization_reload_equality() -> None:
    result = fuse([row("c01", 1)], [row("c02", 1)])
    assert json.loads(stable_json(result)) == json.loads(stable_json(json.loads(stable_json(result))))


def test_deterministic_output_hash() -> None:
    first = stable_json(fuse([row("c02", 1), row("c01", 2)], [row("c03", 1)]))
    second = stable_json(fuse([row("c02", 1), row("c01", 2)], [row("c03", 1)]))
    assert sha256_text(first) == sha256_text(second)


def test_invalid_graph_hashes_are_explicitly_rejected_by_run_contract() -> None:
    assert REJECTED_GRAPH_HASHES == {
        "invalid_v1": "77a5d83bf2989602bc506175bb9ee569addf49bc1aa57af138cc283d8d5985df",
        "invalid_v3_1": "7b2e339a0865cd9ab7682ba8d309407ae97bb27bd862b5ad7fddf08f8f839d84",
    }
    assert EXPECTED_HASHES["graph"] not in REJECTED_GRAPH_HASHES.values()


def test_fusion_manifest_proves_pre_evaluation_boundary() -> None:
    manifest = json.loads((ROOT / "runs/v2/phase4_hybrid/fusion_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "fusion_only_pending_trace_gate"
    assert manifest["raw_component_scores_used"] is False
    assert manifest["component_indexes_rebuilt"] is False
    assert all(manifest[key] is False for key in (
        "relevance_inputs_read", "reference_answers_read", "query_categories_read",
        "prior_metrics_read", "owner_judgments_read", "blind_pool_relevance_read",
        "invalid_graph_artifacts_read",
    ))


def test_trace_gate_passes_before_qrels_and_freezes_rankings() -> None:
    decision = json.loads((ROOT / "audits/phase4_hybrid/trace_validity_decision.json").read_text(encoding="utf-8"))
    freeze = json.loads((ROOT / "runs/v2/phase4_hybrid/fusion_freeze_manifest.json").read_text(encoding="utf-8"))
    assert decision["status"] == "passed_fusion_trace_gate"
    assert decision["valid_trace_count"] == decision["inspected_trace_count"] == 8
    assert decision["metrics_calculated_at_gate_time"] is False
    assert freeze["status"] == "hybrid_rankings_frozen_after_trace_gate_before_qrels"
    assert freeze["qrels_read_before_freeze"] is False


def test_balanced_metrics_and_bootstrap_cover_all_required_scopes() -> None:
    notice = "Metrics use non-exhaustive direct-support qrels. Unjudged relevant chunks may exist. Pilot results are exploratory and not final dissertation evidence."
    metrics = json.loads((ROOT / "runs/v2/phase4_hybrid/metrics/balanced_known_gold_metrics.json").read_text(encoding="utf-8"))
    assert metrics["notice"] == notice
    assert set(metrics["systems"]) == {"bm25", "entity_graph_v3_2", "hybrid_bm25_graph_rrf"}
    for system in metrics["systems"].values():
        assert system["aggregate"]["notice"] == notice and system["aggregate"]["query_n"] == 34
        assert set(system["aggregate"]["metrics"]) == set(METRICS)
        assert set(system["per_category"]) == set(CATEGORIES)
        assert all(row["notice"] == notice for row in system["per_category"].values())
    comparisons = json.loads((ROOT / "runs/v2/phase4_hybrid/statistics/paired_bootstrap_hybrid_vs_constituents.json").read_text(encoding="utf-8"))
    assert comparisons["samples"] == 10_000 and comparisons["seed"] == 42
    assert comparisons["strongest_constituent_by_aggregate_mrr_at_10"] == "bm25"
    for comparison in comparisons["comparisons"].values():
        assert set(comparison["aggregate"]) == set(METRICS)
        assert set(comparison["per_category"]) == set(CATEGORIES)
    assert comparisons["equal_weight_fusion_vs_strongest"] == "point_estimate_higher_but_inconclusive"
    strongest = comparisons["comparisons"]["hybrid_vs_bm25"]["aggregate"]["mrr_at_10"]
    assert strongest["ci95"] == [-0.024509803921568624, 0.10294117647058823]
    assert strongest["uncertainty_includes_zero"] is True
    assert "improves" not in json.dumps(comparisons)


def test_live_latency_and_combined_pool_contracts() -> None:
    latency = json.loads((ROOT / "runs/v2/phase4_hybrid/latency/live_summary.json").read_text(encoding="utf-8"))
    protocol = latency["protocol"]
    assert protocol["execution_order"] == LATENCY_EXECUTION_ORDER
    assert protocol["validation_warmup_query_n"] == LATENCY_VALIDATION_QUERY_N == 34
    assert protocol["additional_warmup_query_n"] == LATENCY_ADDITIONAL_WARMUP_QUERY_N == 5
    assert protocol["measured_query_n"] == LATENCY_MEASURED_QUERY_N == 34
    assert protocol["repetitions_per_query"] == LATENCY_REPETITIONS_PER_QUERY == 20
    assert protocol["measured_sample_n"] == LATENCY_MEASURED_SAMPLE_N == 680
    assert protocol["cache_condition"] == "warm persisted-index/cache operational conditions"
    assert protocol["cache_flushing_performed"] is False
    assert protocol["cold_start_latency"] is False
    assert protocol["component_indexes_rebuilt"] is False
    assert protocol["validation_invocations"] == {
        "combined_bm25_retrieval_call_n": 34,
        "combined_graph_retrieval_call_n": 34,
        "combined_rrf_fusion_call_n": 34,
        "combined_run_query_call_n": 34,
        "separate_bm25_validation_call_n": 34,
        "separate_graph_validation_call_n": 34,
        "total_bm25_calls_before_additional_warmup": 68,
        "total_graph_calls_before_additional_warmup": 68,
        "total_rrf_fusion_calls_before_additional_warmup": 34,
    }
    assert "warmup_queries" not in protocol and "query_n" not in protocol and "sample_n" not in protocol
    assert latency["latency_interpretation"] == "Reported values are warm-cache operational latency and must not be presented as cold-start latency."
    assert set(latency["timings"]) == {
        "bm25_retrieval_ms", "graph_retrieval_ms", "rrf_fusion_overhead_ms",
        "sequential_end_to_end_ms", "parallel_critical_path_estimate_ms",
    }
    blind = [json.loads(line) for line in (ROOT / "runs/v2/phase4_hybrid/pool/provisional_blind_top10_bm25_faiss_graph_hybrid.jsonl").read_text(encoding="utf-8").splitlines()]
    sealed = [json.loads(line) for line in (ROOT / "runs/v2/phase4_hybrid/pool/sealed_provenance_bm25_faiss_graph_hybrid.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(blind) == len(sealed) == 620
    assert all(not row["relevance_judgment"] and not row["reviewer_notes"] for row in blind)
    assert len({(row["query_id"], row["chunk_id"]) for row in sealed}) == 620


def test_latency_disclosure_correction_preserves_values_and_non_latency_artifacts() -> None:
    current = ROOT / "runs/v2/phase4_hybrid"
    preserved = ROOT / "runs/v2/phase4_hybrid_pre_latency_disclosure_correction"
    current_summary = json.loads((current / "latency/live_summary.json").read_text(encoding="utf-8"))
    preserved_summary = json.loads((preserved / "latency/live_summary.json").read_text(encoding="utf-8"))
    assert current_summary["timings"] == preserved_summary["timings"]
    assert sha256_text((current / "latency/live_raw_samples.jsonl").read_text(encoding="utf-8")) == sha256_text((preserved / "latency/live_raw_samples.jsonl").read_text(encoding="utf-8"))
    latency_dependent = {
        "latency/live_summary.json",
        "evaluation_manifest.json",
        "evaluation_hashes.json",
        "statistics/paired_bootstrap_hybrid_vs_constituents.json",
    }
    preserved_hashes = {
        str(path.relative_to(preserved)): sha256_text(path.read_text(encoding="utf-8"))
        for path in preserved.rglob("*") if path.is_file() and str(path.relative_to(preserved)) not in latency_dependent
    }
    current_hashes = {
        str(path.relative_to(current)): sha256_text(path.read_text(encoding="utf-8"))
        for path in current.rglob("*") if path.is_file() and str(path.relative_to(current)) not in latency_dependent
    }
    assert current_hashes == preserved_hashes


def test_latency_execution_code_orders_validation_then_warmup_then_measurement() -> None:
    source = inspect.getsource(measure_latency)
    validation = source.index("for query_id in query_ids:")
    additional_warmup = source.index("for query_id in query_ids[:LATENCY_ADDITIONAL_WARMUP_QUERY_N]:")
    measured = source.index("for repetition in range(1, LATENCY_REPETITIONS_PER_QUERY + 1):")
    assert validation < additional_warmup < measured


def test_preserved_pre_correction_run_tree_hash() -> None:
    preserved = ROOT / "runs/v2/phase4_hybrid_pre_latency_disclosure_correction"
    inventory = {
        str(path.relative_to(preserved)): sha256_text(path.read_text(encoding="utf-8"))
        for path in preserved.rglob("*") if path.is_file()
    }
    payload = "".join(f"{relative}\0{digest}\n" for relative, digest in sorted(inventory.items())).encode()
    assert len(inventory) == 22
    assert hashlib.sha256(payload).hexdigest() == "418e658ecae2a2fdf73d3795c27f55085eab7733e3d80da7e8d9bf619fb31a24"
