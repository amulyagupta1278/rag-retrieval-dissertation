#!/usr/bin/env python3
"""Build one verified seed-42 data contract for both dashboard screens.

All evidence bytes are read from one immutable Git commit. Renderers consume only
the generated CSV/Parquet and ``dashboard_payload.json``; they never read study
artifacts directly.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboards/data"
EVIDENCE_COMMIT = "7bc5bda9c6fc01964bab0247145699fe14e35175"
EVIDENCE_DATE = "2026-07-29"
SEED = 42
BOOTSTRAP_SAMPLES = 10_000

PRIMARY = "runs/v2/phase6_seed42_final/metrics/final_pooled_per_query.jsonl"
KNOWN_GOLD = "runs/v2/phase6_seed42_final/metrics/known_gold_per_query.jsonl"
COMPARISON = "runs/v2/phase6_seed42_final/metrics/system_comparison_table.json"
BALANCED = "runs/v2/phase6_seed42_final/metrics/balanced_metrics.json"
QA = "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl"
QRELS = "data/v2/pilot/qrels/pilot-qa-v2-final-pooled-phase6-seed42-owner-adjudicated.tsv"
STATISTICS = "runs/v2/phase6_seed42_final/statistics/preregistered_h1_h4_results.json"
UNCERTAINTY = "runs/v2/phase6_seed42_final/metrics/paired_uncertainty_vs_bm25.json"
H5 = "runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/h5_results.json"

BLACKLISTED = {
    "runs/v2/phase6_metrics/statistical_tests.json",
    "runs/v2/phase6_metrics/per_query_metrics.csv",
    "data/v2/pilot/qrels/INVALID-seed123-ai-graded-phase6.tsv",
}
SYSTEMS = (
    "bm25",
    "faiss_windowed_max",
    "graph_v3_2",
    "hybrid_rrf",
    "prompt_rag_claude",
)
SYSTEM_LABELS = {
    "bm25": "BM25",
    "faiss_windowed_max": "FAISS (dense baseline)",
    "graph_v3_2": "Entity-Co-occurrence Graph",
    "hybrid_rrf": "Hybrid (BM25+Graph, RRF)",
    "prompt_rag_claude": "Prompt-RAG (BM25 top-50 reranker)",
}
RANKINGS = {
    "bm25": "runs/v2/phase2a_r5_windowed/rankings/bm25_top50.jsonl",
    "faiss_windowed_max": "runs/v2/phase2a_r5_windowed/rankings/faiss_windowed_max_top50.jsonl",
    "graph_v3_2": "runs/v2/phase3_graph_v3_2/rankings/graph_v3_2_top50.jsonl",
    "hybrid_rrf": "runs/v2/phase4_hybrid/rankings/hybrid_top50.jsonl",
    "prompt_rag_claude": (
        "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/complete_primary_rankings.jsonl"
    ),
}
CATEGORIES = (
    "exact_lookup",
    "terminology",
    "paraphrase",
    "entity_relation",
    "multi_hop",
    "synthesis",
)
CATEGORY_COUNTS = {
    "exact_lookup": 6,
    "terminology": 6,
    "paraphrase": 6,
    "entity_relation": 6,
    "multi_hop": 6,
    "synthesis": 4,
}
METRIC_MAP = {
    "hit_rate_at_5": "hit_at_5",
    "hit_rate_at_10": "hit_at_10",
    "mrr_at_5": "mrr_at_5",
    "mrr_at_10": "mrr_at_10",
    "recall_at_5": "recall_at_5",
    "recall_at_10": "recall_at_10",
    "graded_ndcg_at_10": "ndcg_graded_at_10",
    "complete_evidence_recall_at_10": "ce_recall_at_10",
}
FAILURE_ORDER = ("hit", "near_miss", "ranking_failure", "missing_evidence")


class ValidityError(RuntimeError):
    """Raised when frozen evidence violates dashboard contract."""


class SourceReader:
    """Read allowlisted evidence from one immutable Git tree and record hashes."""

    def __init__(self, commit: str = EVIDENCE_COMMIT) -> None:
        resolved = subprocess.run(
            ["git", "rev-parse", f"{commit}^{{commit}}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if resolved != EVIDENCE_COMMIT:
            raise ValidityError(f"evidence commit drift: {resolved}")
        self.commit = resolved
        self.reads: dict[str, str] = {}

    def bytes(self, relative: str) -> bytes:
        """Return exact bytes for a path at frozen commit."""

        if relative in BLACKLISTED:
            raise ValidityError(f"blacklisted source read attempted: {relative}")
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ValidityError(f"unsafe source path: {relative}")
        completed = subprocess.run(
            ["git", "show", f"{self.commit}:{relative}"],
            cwd=ROOT,
            capture_output=True,
        )
        if completed.returncode:
            raise FileNotFoundError(f"required source missing at {self.commit}: {relative}")
        payload = completed.stdout
        self.reads[relative] = hashlib.sha256(payload).hexdigest()
        return payload

    def json(self, relative: str) -> dict[str, Any]:
        value = json.loads(self.bytes(relative).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValidityError(f"expected JSON object: {relative}")
        self._validate_status(value, relative)
        return value

    def jsonl(self, relative: str) -> list[dict[str, Any]]:
        rows = [
            json.loads(line)
            for line in self.bytes(relative).decode("utf-8").splitlines()
            if line.strip()
        ]
        if not all(isinstance(row, dict) for row in rows):
            raise ValidityError(f"expected JSON objects: {relative}")
        for row in rows:
            self._validate_status(row, relative)
        return rows

    @staticmethod
    def _validate_status(value: dict[str, Any], relative: str) -> None:
        status = value.get("VALIDITY_STATUS")
        notice = value.get("INVALIDATION_NOTICE")
        if status is not None and str(status).upper().startswith("INVALID"):
            raise ValidityError(f"invalid source status: {relative}")
        if notice not in (None, "", False):
            raise ValidityError(f"source carries invalidation notice: {relative}")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _load_qrels(reader: SourceReader) -> dict[str, set[str]]:
    positives: dict[str, set[str]] = defaultdict(set)
    seen: set[tuple[str, str]] = set()
    for line_number, row in enumerate(
        csv.reader(reader.bytes(QRELS).decode("utf-8").splitlines(), delimiter="\t"), start=1
    ):
        if len(row) != 4:
            raise ValidityError(f"qrels row {line_number} must have four columns")
        query_id, iteration, chunk_id, relevance_text = row
        pair = (query_id, chunk_id)
        if iteration != "0" or pair in seen:
            raise ValidityError(f"invalid/duplicate qrels row {line_number}")
        seen.add(pair)
        try:
            relevance = int(relevance_text)
        except ValueError as exc:
            raise ValidityError(f"malformed qrels relevance at row {line_number}") from exc
        if relevance not in {0, 1, 2}:
            raise ValidityError(f"out-of-range qrels relevance at row {line_number}")
        if relevance > 0:
            positives[query_id].add(chunk_id)
    return positives


def _ranking_map(reader: SourceReader, relative: str) -> dict[str, list[dict[str, Any]]]:
    mapped: dict[str, list[dict[str, Any]]] = {}
    for row in reader.jsonl(relative):
        query_id, ranking = row.get("query_id"), row.get("ranking")
        if not isinstance(query_id, str) or not isinstance(ranking, list):
            raise ValidityError(f"malformed ranking row: {relative}")
        if query_id in mapped or not 0 <= len(ranking) <= 50:
            raise ValidityError(f"duplicate query or invalid ranking depth: {relative}/{query_id}")
        ids = [item.get("chunk_id") for item in ranking]
        if len(set(ids)) != len(ranking) or any(not isinstance(value, str) for value in ids):
            raise ValidityError(f"invalid ranked chunk IDs: {relative}/{query_id}")
        if [item.get("rank") for item in ranking] != list(range(1, len(ranking) + 1)):
            raise ValidityError(f"non-contiguous ranking: {relative}/{query_id}")
        mapped[query_id] = ranking
    return mapped


def _base_frame(rows: list[dict[str, Any]], qa_by_id: dict[str, dict[str, Any]]) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    for row in rows:
        query_id, system, metrics = row.get("query_id"), row.get("system"), row.get("metrics")
        if query_id not in qa_by_id or system not in SYSTEMS or not isinstance(metrics, dict):
            raise ValidityError("malformed per-query metric row")
        qa = qa_by_id[query_id]
        if row.get("category") != qa["category"]:
            raise ValidityError(f"category mismatch: {query_id}")
        record: dict[str, Any] = {
            "query_id": query_id,
            "query_text": qa["question"],
            "category": row["category"],
            "system": system,
        }
        for source_name, output_name in METRIC_MAP.items():
            value = metrics.get(source_name)
            if not isinstance(value, (int, float)):
                raise ValidityError(f"missing metric {source_name}: {system}/{query_id}")
            record[output_name] = float(value)
        output.append(record)
    frame = pd.DataFrame(output)
    if len(frame) != 170 or frame[["query_id", "system"]].duplicated().any():
        raise ValidityError("per-query panel must contain 170 unique query/system rows")
    if set(frame["system"]) != set(SYSTEMS):
        raise ValidityError("per-query panel has incompatible systems")
    return frame


def _reconcile(
    frame: pd.DataFrame, comparison: dict[str, Any], basis: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for system in SYSTEMS:
        subset = frame.loc[frame["system"] == system]
        expected_panel = comparison[system][basis]
        if len(subset) != 34 or expected_panel["query_n"] != 34:
            raise ValidityError(f"wrong query count: {basis}/{system}")
        for source_name, output_name in METRIC_MAP.items():
            observed = float(subset[output_name].mean())
            expected = float(expected_panel["metrics"][source_name])
            delta = observed - expected
            if abs(delta) > 1e-12:
                raise ValidityError(
                    f"aggregate mismatch {basis}/{system}/{source_name}: {observed} != {expected}"
                )
            records.append(
                {
                    "basis": basis,
                    "system": system,
                    "metric": output_name,
                    "observed": observed,
                    "expected": expected,
                    "delta": delta,
                }
            )
    return records


def _bootstrap_mean(values: np.ndarray, generator: np.random.Generator) -> tuple[float, float]:
    indices = generator.integers(0, len(values), size=(BOOTSTRAP_SAMPLES, len(values)))
    means = values[indices].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _forest_rows(statistics: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        "faiss_windowed_max_minus_bm25": "FAISS − BM25",
        "graph_v3_2_minus_bm25": "Graph − BM25",
        "graph_v3_2_minus_faiss_windowed_max": "Graph − FAISS",
        "hybrid_rrf_minus_bm25": "Hybrid − BM25",
        "hybrid_rrf_minus_faiss_windowed_max": "Hybrid − FAISS",
        "hybrid_rrf_minus_graph_v3_2": "Hybrid − Graph",
        "hybrid_rrf_minus_prompt_rag_claude": "Hybrid − Prompt-RAG",
    }
    h1 = statistics["h1_equivalence"]
    primary = h1["primary_result"]
    rows = [
        {
            "hypothesis": "H1",
            "comparison": "BM25 − FAISS · exact+terminology",
            "effect": primary["effect_left_minus_right"],
            "ci_low": primary["ci95"][0],
            "ci_high": primary["ci95"][1],
            "verdict": h1["verdict"],
            "adjusted_p": None,
        }
    ]
    for record in statistics["holm_directional_tests"]:
        if record["metric"] != "mrr_at_10":
            continue
        bootstrap = record["bootstrap"]
        rows.append(
            {
                "hypothesis": record["hypothesis"],
                "comparison": f"{labels[record['comparison']]} · {record['slice']}",
                "effect": bootstrap["effect_left_minus_right"],
                "ci_low": bootstrap["ci95"][0],
                "ci_high": bootstrap["ci95"][1],
                "verdict": "supported" if record["holm_reject_at_0_05"] else "not supported",
                "adjusted_p": record["holm_adjusted_p_value"],
            }
        )
    if len(rows) != 10:
        raise ValidityError(f"expected 10 H1-H4 MRR rows, found {len(rows)}")
    return rows


def _shared_payload(
    frame: pd.DataFrame, statistics: dict[str, Any], h5: dict[str, Any]
) -> dict[str, Any]:
    generator = np.random.default_rng(SEED)
    aggregate_metrics = ("mrr_at_10", "recall_at_10", "ndcg_graded_at_10", "ce_recall_at_10", "hit_at_5")
    aggregates: list[dict[str, Any]] = []
    for system in SYSTEMS:
        subset = frame.loc[frame["system"] == system].sort_values("query_id")
        record: dict[str, Any] = {"system": system, "label": SYSTEM_LABELS[system], "query_n": 34}
        for metric in aggregate_metrics:
            values = subset[metric].to_numpy(dtype=float)
            low, high = _bootstrap_mean(values, generator)
            record[metric] = {"mean": float(values.mean()), "ci95": [low, high]}
        aggregates.append(record)

    category_mrr: list[dict[str, Any]] = []
    for category in CATEGORIES:
        for system in SYSTEMS:
            values = frame.loc[
                (frame["category"] == category) & (frame["system"] == system), "mrr_at_10"
            ].to_numpy(dtype=float)
            low, high = _bootstrap_mean(values, generator)
            category_mrr.append(
                {
                    "category": category,
                    "system": system,
                    "query_n": len(values),
                    "mean": float(values.mean()),
                    "ci95": [low, high],
                }
            )

    failures: list[dict[str, Any]] = []
    for system in SYSTEMS:
        subset = frame.loc[frame["system"] == system].sort_values("query_id")
        for failure in FAILURE_ORDER:
            values = (subset["failure_type"] == failure).to_numpy(dtype=float)
            low, high = _bootstrap_mean(values, generator)
            failures.append(
                {
                    "system": system,
                    "failure_type": failure,
                    "count": int(values.sum()),
                    "proportion": float(values.mean()),
                    "ci95": [low, high],
                }
            )

    correlations = {
        (row["x"], row["y"]): row for row in h5.get("correlations", [])
    }
    wanted = [
        ("mrr_at_10", "faithfulness"),
        ("complete_evidence_recall_at_10", "completeness"),
    ]
    if any(pair not in correlations for pair in wanted):
        raise ValidityError("H5 required correlations missing")
    if h5.get("label_sources") != {"human_owner": 26, "offline_ai_knn": 144}:
        raise ValidityError("H5 label-source mix differs from frozen evidence")

    queries: list[dict[str, Any]] = []
    for query_id, group in frame.groupby("query_id", sort=True):
        first = group.iloc[0]
        systems = []
        for system in SYSTEMS:
            row = group.loc[group["system"] == system].iloc[0]
            systems.append(
                {
                    "system": system,
                    "gold_rank": int(row["gold_rank"]),
                    "hit_at_5": int(row["hit_at_5"]),
                    "mrr_at_10": float(row["mrr_at_10"]),
                    "recall_at_10": float(row["recall_at_10"]),
                    "ndcg_graded_at_10": float(row["ndcg_graded_at_10"]),
                    "ce_recall_at_10": float(row["ce_recall_at_10"]),
                    "failure_type": row["failure_type"],
                }
            )
        queries.append(
            {
                "query_id": query_id,
                "query_text": first["query_text"],
                "category": first["category"],
                "difficulty": float(first["difficulty"]),
                "n_systems_hit_at_5": int(first["n_systems_hit_at_5"]),
                "systems": systems,
            }
        )

    return {
        "schema_version": 2,
        "evidence_commit": EVIDENCE_COMMIT,
        "evidence_date": EVIDENCE_DATE,
        "qrels_base": "final_pooled",
        "seed": SEED,
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "pilot": {
            "documents": 22,
            "chunks": 140,
            "questions": 34,
            "systems": 5,
            "concentration_risk": "Two documents supply 65/140 chunks.",
        },
        "systems": [{"key": system, "label": SYSTEM_LABELS[system]} for system in SYSTEMS],
        "categories": [
            {"key": category, "query_n": CATEGORY_COUNTS[category]} for category in CATEGORIES
        ],
        "aggregates": aggregates,
        "category_mrr": category_mrr,
        "failures": failures,
        "forest": _forest_rows(statistics),
        "hypothesis_summaries": statistics["summaries"],
        "h5": {
            "status": h5["status"],
            "decision": h5["decision"],
            "label_sources": h5["label_sources"],
            "correlations": [correlations[pair] for pair in wanted],
            "interpretation_limits": h5["interpretation_limits"],
        },
        "queries": queries,
    }


def build() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build primary dataframe, shared render payload, and Gate 1 audit."""

    reader = SourceReader()
    qa_rows = reader.jsonl(QA)
    qa_by_id = {row["question_id"]: row for row in qa_rows}
    if len(qa_rows) != 34 or len(qa_by_id) != 34:
        raise ValidityError("QA must contain 34 unique questions")
    if Counter(row["category"] for row in qa_rows) != Counter(CATEGORY_COUNTS):
        raise ValidityError("QA category counts differ from frozen contract")

    comparison = reader.json(COMPARISON)
    balanced = reader.json(BALANCED)
    if set(comparison) != set(SYSTEMS) or set(balanced) != set(SYSTEMS):
        raise ValidityError("aggregate files do not contain exact five-system panel")
    statistics = reader.json(STATISTICS)
    reader.json(UNCERTAINTY)
    if statistics.get("conclusions_are_exploratory_pilot_evidence") is not True:
        raise ValidityError("statistics missing exploratory-pilot disclosure")
    if statistics.get("invalid_historical_statistics_reused") is not False:
        raise ValidityError("statistics reused invalid historical lineage")
    h5 = reader.json(H5)
    if h5.get("status") != "complete_exploratory_ai_evaluated":
        raise ValidityError("H5 source is not frozen exploratory evaluation")

    positives = _load_qrels(reader)
    if set(positives) != set(qa_by_id) or any(not values for values in positives.values()):
        raise ValidityError("every query must have positive final-pooled qrels")
    primary = _base_frame(reader.jsonl(PRIMARY), qa_by_id)
    known_gold = _base_frame(reader.jsonl(KNOWN_GOLD), qa_by_id)
    primary["qrel_base"] = "final_pooled"
    known_gold["qrel_base"] = "known_gold"

    rankings = {system: _ranking_map(reader, path) for system, path in RANKINGS.items()}
    if any(set(panel) != set(qa_by_id) for panel in rankings.values()):
        raise ValidityError("ranking query sets differ from QA")
    gold_ranks: list[int] = []
    failure_types: list[str] = []
    for row in primary.itertuples(index=False):
        ranks = [
            int(item["rank"])
            for item in rankings[row.system][row.query_id]
            if item["chunk_id"] in positives[row.query_id]
        ]
        rank = min(ranks) if ranks else 999
        failure = (
            "hit"
            if rank <= 5
            else "near_miss"
            if rank <= 10
            else "ranking_failure"
            if rank <= 50
            else "missing_evidence"
        )
        if int(row.hit_at_5) != int(rank <= 5) or int(row.hit_at_10) != int(rank <= 10):
            raise ValidityError(f"gold-rank/hit mismatch: {row.system}/{row.query_id}")
        gold_ranks.append(rank)
        failure_types.append(failure)
    primary["gold_rank"] = gold_ranks
    primary["failure_type"] = failure_types
    hits = primary.groupby("query_id", sort=True)["hit_at_5"].sum().astype(int)
    primary["n_systems_hit_at_5"] = primary["query_id"].map(hits)
    primary["difficulty"] = 1.0 - primary["n_systems_hit_at_5"] / 5.0

    columns = [
        "query_id",
        "query_text",
        "category",
        "system",
        "gold_rank",
        "hit_at_5",
        "hit_at_10",
        "mrr_at_5",
        "mrr_at_10",
        "recall_at_5",
        "recall_at_10",
        "ndcg_graded_at_10",
        "ce_recall_at_10",
        "qrel_base",
        "failure_type",
        "n_systems_hit_at_5",
        "difficulty",
    ]
    primary = primary[columns].sort_values(["query_id", "system"], kind="stable")
    if primary.isna().any().any():
        raise ValidityError("primary dataframe contains null values")

    primary_reconciliation = _reconcile(primary, comparison, "final_pooled")
    known_reconciliation = _reconcile(known_gold, comparison, "known_gold")
    payload = _shared_payload(primary, statistics, h5)

    OUT.mkdir(parents=True, exist_ok=True)
    _atomic_text(OUT / "per_query_pilot.csv", primary.to_csv(index=False, lineterminator="\n"))
    parquet_tmp = OUT / "per_query_pilot.parquet.tmp"
    primary.to_parquet(parquet_tmp, index=False)
    parquet_tmp.replace(OUT / "per_query_pilot.parquet")
    _atomic_text(
        OUT / "dashboard_payload.json",
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    audit = {
        "status": "gate1_passed",
        "validity_guard": "passed_seed42_only",
        "evidence_commit": EVIDENCE_COMMIT,
        "evidence_date": EVIDENCE_DATE,
        "row_count": len(primary),
        "column_count": len(primary.columns),
        "query_count": int(primary["query_id"].nunique()),
        "system_count": int(primary["system"].nunique()),
        "category_counts": dict(sorted(CATEGORY_COUNTS.items())),
        "null_counts": {column: int(value) for column, value in primary.isna().sum().items()},
        "primary_qrel_base": "final_pooled",
        "blacklisted_paths": sorted(BLACKLISTED),
        "blacklisted_sources_read": [],
        "source_hashes": dict(sorted(reader.reads.items())),
        "primary_reconciliation": primary_reconciliation,
        "known_gold_reconciliation": known_reconciliation,
        "h5_source_available": True,
        "h5_source": H5,
    }
    _atomic_text(
        OUT / "gate1_reconciliation.json",
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
    )
    return primary, audit


def main() -> None:
    frame, audit = build()
    print(frame.head(10).to_string(index=False))
    print(
        json.dumps(
            {
                "blacklisted_sources_read": audit["blacklisted_sources_read"],
                "evidence_commit": audit["evidence_commit"],
                "null_total": sum(audit["null_counts"].values()),
                "qrel_base": audit["primary_qrel_base"],
                "row_count": audit["row_count"],
                "status": audit["status"],
                "system_count": audit["system_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
