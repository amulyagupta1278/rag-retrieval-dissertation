from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from src.generation.phase7_gate import assert_phase7_ready

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/v2/phase6_seed42_final"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_canonical_human_inputs_are_byte_preserved() -> None:
    assert sha256(RUN / "human_regrade/regrade_package_seed42_COMPLETED.csv") == (
        "e12c4c427ddf7b5ea58063c19e3063ddfcf223b2762ee2089e8434b26dc9bc00"
    )
    assert sha256(RUN / "owner_adjudication/phase6_owner_adjudication_14_FINAL.csv") == (
        "9fd10b3267fbcd339c3ce65b2c5796a99b17672f69c32d4a39cbdc9055fa4aa7"
    )


def test_completed_regrade_and_agreement() -> None:
    rows = csv_rows(RUN / "human_regrade/regrade_package_seed42_COMPLETED.csv")
    assert len(rows) == len({row["display_id"] for row in rows}) == 114
    assert len({(row["query_id"], row["chunk_id"]) for row in rows}) == 114
    assert Counter(row["second_relevance_grade"] for row in rows) == Counter(
        {"0": 79, "1": 24, "2": 11}
    )
    agreement = json.loads((RUN / "human_regrade/agreement_report.json").read_text())
    assert agreement["exact_agreement_n"] == 100
    assert agreement["disagreement_n"] == 14
    assert agreement["exact_agreement"] == 100 / 114
    assert agreement["cohen_kappa_unweighted"] == 0.7420814479638009
    assert agreement["cohen_kappa_quadratic_weighted"] == 0.8841126924194017


def test_owner_adjudication_exactly_resolves_disagreements() -> None:
    regrade = csv_rows(RUN / "human_regrade/regrade_package_seed42_COMPLETED.csv")
    first_pass = csv_rows(
        ROOT / "runs/v2/phase6_blind_judging_package/owner_judging_package.csv"
    )
    owner = csv_rows(
        RUN / "owner_adjudication/phase6_owner_adjudication_14_FINAL.csv"
    )
    first_by_id = {row["display_id"]: row for row in first_pass}
    disagreement_ids = {
        row["display_id"]
        for row in regrade
        if first_by_id[row["display_id"]]["relevance_grade"]
        != row["second_relevance_grade"]
    }
    assert len(owner) == len({row["display_id"] for row in owner}) == 14
    assert {row["display_id"] for row in owner} == disagreement_ids
    assert Counter(row["final_grade"] for row in owner) == Counter({"1": 3, "2": 11})
    assert all(row["owner_rationale"].strip() for row in owner)

    multipart_grade_two_ids = {
        "v2q-025-candidate-13",
        "v2q-031-candidate-13",
        "v2q-033-candidate-01",
        "v2q-033-candidate-13",
        "v2q-033-candidate-16",
        "v2q-034-candidate-09",
        "v2q-034-candidate-12",
        "v2q-034-candidate-14",
        "v2q-034-candidate-17",
    }
    owner_grades = {row["display_id"]: row["final_grade"] for row in owner}
    assert {display_id for display_id, grade in owner_grades.items() if grade == "2"}.issuperset(
        multipart_grade_two_ids
    )


def test_final_labels_have_exact_precedence_counts() -> None:
    rows = csv_rows(RUN / "final_labels/phase6_final_labels.csv")
    assert len(rows) == len({row["display_id"] for row in rows}) == 755
    assert len({(row["query_id"], row["chunk_id"]) for row in rows}) == 755
    assert Counter(row["final_relevance_grade"] for row in rows) == Counter(
        {"0": 572, "1": 89, "2": 94}
    )
    assert Counter(row["label_source"] for row in rows) == Counter(
        {
            "first_pass_unsampled": 641,
            "seed42_regrade_agreement": 100,
            "owner_adjudication": 14,
        }
    )
    assert all(row["adjudication_rationale"] for row in rows if row["label_source"] == "owner_adjudication")


def test_final_qrels_exactly_map_final_labels() -> None:
    labels = csv_rows(RUN / "final_labels/phase6_final_labels.csv")
    expected = sorted(
        (row["query_id"], "0", row["chunk_id"], row["final_relevance_grade"])
        for row in labels
    )
    actual = [tuple(line.split("\t")) for line in (RUN / "qrels/phase6_final_pooled_qrels.tsv").read_text().splitlines()]
    assert actual == expected
    report = json.loads((RUN / "qrels/change_report.json").read_text())
    assert report["changed_qrel_n"] == len(report["changes"]) == 11


def test_metrics_cover_all_systems_categories_and_metrics() -> None:
    metrics = json.loads((RUN / "metrics/balanced_metrics.json").read_text())
    assert set(metrics) == {
        "bm25",
        "faiss_windowed_max",
        "graph_v3_2",
        "hybrid_rrf",
        "prompt_rag_claude",
    }
    for system in metrics.values():
        assert system["aggregate"]["query_n"] == 34
        assert set(system["aggregate"]["metrics"]) == {
            "mrr_at_5",
            "mrr_at_10",
            "recall_at_5",
            "recall_at_10",
            "hit_rate_at_5",
            "hit_rate_at_10",
            "precision_at_5",
            "precision_at_10",
            "binary_ndcg_at_10",
            "graded_ndcg_at_10",
            "complete_evidence_recall_at_5",
            "complete_evidence_recall_at_10",
        }
        assert {category: row["query_n"] for category, row in system["per_category"].items()} == {
            "entity_relation": 6,
            "exact_lookup": 6,
            "multi_hop": 6,
            "paraphrase": 6,
            "synthesis": 4,
            "terminology": 6,
        }


def test_statistics_match_preregistered_hypotheses() -> None:
    result = json.loads((RUN / "statistics/preregistered_h1_h4_results.json").read_text())
    h1 = result["h1_equivalence"]
    assert h1["comparison"] == "bm25_minus_faiss_windowed_max"
    assert h1["query_categories"] == ["exact_lookup", "terminology"]
    assert h1["query_n"] == 12
    assert h1["primary_margin"] == [-0.05, 0.05]
    assert h1["sensitivity_margin"] == [-0.03, 0.03]
    assert h1["verdict"] == "inconclusive"
    tests = result["holm_directional_tests"]
    assert len(tests) == 32
    assert sum(test["hypothesis"] == "H2" for test in tests) == 12
    assert sum(test["hypothesis"] == "H3" for test in tests) == 16
    assert sum(test["hypothesis"] == "H4" for test in tests) == 4
    assert all(test["randomization"]["method"].startswith("exact paired") for test in tests)
    assert all("holm_adjusted_p_value" in test for test in tests)


def test_all_new_manifests_verify() -> None:
    manifests = (
        RUN / "freeze_manifest.json",
        RUN / "metrics/supplement_manifest.json",
        RUN / "statistics/manifest.json",
    )
    for path in manifests:
        manifest = json.loads(path.read_text())
        for group in ("code_hashes", "inputs", "outputs"):
            for relative, expected in manifest.get(group, {}).items():
                assert sha256(ROOT / relative) == expected


def test_phase7_dependency_gate_is_open_but_execution_unauthorized() -> None:
    gate = ROOT / "audits/phase7/dependency_gate_seed42_final.json"
    result = assert_phase7_ready(gate, ROOT)
    assert result["ready"] is True
    manifest = json.loads(gate.read_text())
    assert manifest["execution_authorized"] is False
    recorded = json.loads((ROOT / "audits/phase7/gate_result_seed42_final.json").read_text())
    assert recorded["dependency_gate"] == "OPEN"
    assert recorded["execution_authorized"] is False
