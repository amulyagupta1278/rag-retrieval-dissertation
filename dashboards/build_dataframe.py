#!/usr/bin/env python3
"""Build and reconcile authoritative seed-42 pilot per-query dashboard data."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboards/data"
PRIMARY = ROOT / "runs/v2/phase6_seed42_final/metrics/final_pooled_per_query.jsonl"
KNOWN_GOLD = ROOT / "runs/v2/phase6_seed42_final/metrics/known_gold_per_query.jsonl"
COMPARISON = ROOT / "runs/v2/phase6_seed42_final/metrics/system_comparison_table.json"
BALANCED = ROOT / "runs/v2/phase6_seed42_final/metrics/balanced_metrics.json"
QA = ROOT / "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl"
QRELS = ROOT / "data/v2/pilot/qrels/pilot-qa-v2-final-pooled-phase6-seed42-owner-adjudicated.tsv"
STATISTICS = ROOT / "runs/v2/phase6_seed42_final/statistics/preregistered_h1_h4_results.json"
UNCERTAINTY = ROOT / "runs/v2/phase6_seed42_final/metrics/paired_uncertainty_vs_bm25.json"
H5 = ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/h5_results.json"
CHUNKS = ROOT / "data/v2/pilot/chunks/chunks.jsonl"
DOCUMENTS = ROOT / "data/v2/pilot/extracted/documents.jsonl"

BLACKLISTED = {
    (ROOT / "runs/v2/phase6_metrics/statistical_tests.json").resolve(),
    (ROOT / "runs/v2/phase6_metrics/per_query_metrics.csv").resolve(),
    (ROOT / "data/v2/pilot/qrels/INVALID-seed123-ai-graded-phase6.tsv").resolve(),
}

SYSTEMS = (
    "bm25",
    "faiss_windowed_max",
    "graph_v3_2",
    "hybrid_rrf",
    "prompt_rag_claude",
)
RANKINGS = {
    "bm25": ROOT / "runs/v2/phase2a_r5_windowed/rankings/bm25_top50.jsonl",
    "faiss_windowed_max": ROOT
    / "runs/v2/phase2a_r5_windowed/rankings/faiss_windowed_max_top50.jsonl",
    "graph_v3_2": ROOT / "runs/v2/phase3_graph_v3_2/rankings/graph_v3_2_top50.jsonl",
    "hybrid_rrf": ROOT / "runs/v2/phase4_hybrid/rankings/hybrid_top50.jsonl",
    "prompt_rag_claude": ROOT
    / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/complete_primary_rankings.jsonl",
}
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


class ValidityError(RuntimeError):
    """Raised when dashboard input violates frozen evidence contract."""


class SourceReader:
    """Read only allowlisted evidence while recording exact SHA-256 provenance."""

    def __init__(self) -> None:
        self.reads: dict[str, str] = {}

    def bytes(self, path: Path) -> bytes:
        resolved = path.resolve()
        if resolved in BLACKLISTED:
            raise ValidityError(f"blacklisted source read attempted: {path.relative_to(ROOT)}")
        if not path.is_file():
            raise FileNotFoundError(f"required source missing: {path.relative_to(ROOT)}")
        payload = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        self.reads[relative] = hashlib.sha256(payload).hexdigest()
        return payload

    def json(self, path: Path) -> dict[str, Any]:
        value = json.loads(self.bytes(path).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValidityError(f"expected JSON object: {path.relative_to(ROOT)}")
        self._validate_status_fields(value, path)
        return value

    def jsonl(self, path: Path) -> list[dict[str, Any]]:
        rows = [json.loads(line) for line in self.bytes(path).decode("utf-8").splitlines() if line]
        if not all(isinstance(row, dict) for row in rows):
            raise ValidityError(f"expected JSON objects: {path.relative_to(ROOT)}")
        for row in rows:
            self._validate_status_fields(row, path)
        return rows

    @staticmethod
    def _validate_status_fields(value: dict[str, Any], path: Path) -> None:
        status = value.get("VALIDITY_STATUS")
        notice = value.get("INVALIDATION_NOTICE")
        if status is not None and str(status).upper().startswith("INVALID"):
            raise ValidityError(f"invalid source status: {path.relative_to(ROOT)}")
        if notice not in (None, "", False):
            raise ValidityError(f"source carries invalidation notice: {path.relative_to(ROOT)}")


def _load_qrels(
    reader: SourceReader,
) -> tuple[dict[str, set[str]], dict[tuple[str, str], int]]:
    positives: dict[str, set[str]] = defaultdict(set)
    grades: dict[tuple[str, str], int] = {}
    text = reader.bytes(QRELS).decode("utf-8")
    for line_number, row in enumerate(csv.reader(text.splitlines(), delimiter="\t"), start=1):
        if len(row) != 4:
            raise ValidityError(f"qrels row {line_number} must have four columns")
        query_id, iteration, chunk_id, relevance_text = row
        if iteration != "0":
            raise ValidityError(f"qrels row {line_number} has unsupported iteration")
        try:
            relevance = int(relevance_text)
        except ValueError as exc:
            raise ValidityError(f"qrels row {line_number} has malformed relevance") from exc
        if relevance not in {0, 1, 2}:
            raise ValidityError(f"qrels row {line_number} has out-of-range relevance")
        pair = (query_id, chunk_id)
        if pair in grades:
            raise ValidityError(f"duplicate qrels pair at row {line_number}")
        grades[pair] = relevance
        if relevance > 0:
            positives[query_id].add(chunk_id)
    return positives, grades


def _write_evidence_browser(
    reader: SourceReader,
    qa_rows: list[dict[str, Any]],
    qrel_grades: dict[tuple[str, str], int],
    rankings: dict[str, dict[str, list[dict[str, Any]]]],
) -> None:
    """Write reference-answer and pooled-positive passage drilldown data."""

    document_rows = reader.jsonl(DOCUMENTS)
    documents = {row.get("document_id"): row for row in document_rows}
    if len(documents) != 22 or None in documents:
        raise ValidityError("document metadata must contain 22 unique documents")
    chunk_rows = reader.jsonl(CHUNKS)
    chunks = {row.get("chunk_id"): row for row in chunk_rows}
    if len(chunks) != 140 or None in chunks:
        raise ValidityError("chunk metadata must contain 140 unique chunks")
    unknown_qrel_chunks = {chunk_id for _, chunk_id in qrel_grades if chunk_id not in chunks}
    if unknown_qrel_chunks:
        raise ValidityError(f"qrels contain unknown chunks: {sorted(unknown_qrel_chunks)[:3]}")

    output: list[dict[str, Any]] = []
    for qa in sorted(qa_rows, key=lambda row: row["question_id"]):
        query_id = qa["question_id"]
        evidence: list[dict[str, Any]] = []
        positives = sorted(
            (
                (chunk_id, grade)
                for (candidate_query, chunk_id), grade in qrel_grades.items()
                if candidate_query == query_id and grade > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )
        for chunk_id, grade in positives:
            chunk = chunks[chunk_id]
            document_id = chunk.get("document_id")
            if document_id not in documents:
                raise ValidityError(f"chunk has unknown document: {chunk_id}")
            ranks = {}
            for system in SYSTEMS:
                rank = next(
                    (
                        int(item["rank"])
                        for item in rankings[system][query_id]
                        if item["chunk_id"] == chunk_id
                    ),
                    None,
                )
                ranks[system] = rank
            evidence.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "document_title": documents[document_id]["title"],
                    "grade": grade,
                    "ranks": ranks,
                    "text": chunk["text"],
                }
            )
        output.append(
            {
                "category": qa["category"],
                "evidence": evidence,
                "query_id": query_id,
                "question": qa["question"],
                "reference_answer": qa["reference_answer"],
            }
        )
    if len(output) != 34 or any(not row["evidence"] for row in output):
        raise ValidityError("evidence browser requires 34 queries with positive evidence")
    (OUT / "evidence_browser.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ranking_map(reader: SourceReader, path: Path) -> dict[str, list[dict[str, Any]]]:
    rows = reader.jsonl(path)
    mapped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        query_id = row.get("query_id")
        ranking = row.get("ranking")
        if not isinstance(query_id, str) or not isinstance(ranking, list):
            raise ValidityError(f"malformed ranking row: {path.relative_to(ROOT)}")
        if query_id in mapped:
            raise ValidityError(f"duplicate ranking query: {query_id}")
        chunk_ids = [item.get("chunk_id") for item in ranking]
        if any(not isinstance(chunk_id, str) for chunk_id in chunk_ids):
            raise ValidityError(f"malformed ranked chunk ID: {query_id}")
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValidityError(f"duplicate ranked chunk ID: {query_id}")
        expected_ranks = list(range(1, len(ranking) + 1))
        if [item.get("rank") for item in ranking] != expected_ranks:
            raise ValidityError(f"non-contiguous ranking: {query_id}")
        mapped[query_id] = ranking
    return mapped


def _gold_rank(ranking: list[dict[str, Any]], relevant_ids: set[str]) -> int:
    ranks = [int(item["rank"]) for item in ranking if item["chunk_id"] in relevant_ids]
    return min(ranks) if ranks else 999


def _failure_type(gold_rank: int) -> str:
    if gold_rank <= 5:
        return "hit"
    if gold_rank <= 10:
        return "near_miss"
    if gold_rank <= 50:
        return "ranking_failure"
    return "missing_evidence"


def _validate_statistics(reader: SourceReader) -> dict[str, Any]:
    statistics = reader.json(STATISTICS)
    if statistics.get("conclusions_are_exploratory_pilot_evidence") is not True:
        raise ValidityError("statistics missing exploratory-pilot disclosure")
    if statistics.get("invalid_historical_statistics_reused") is not False:
        raise ValidityError("statistics reused invalid historical lineage")
    summaries = statistics.get("summaries")
    if not isinstance(summaries, dict) or set(summaries) != {"H1", "H2", "H3", "H4", "H5"}:
        raise ValidityError("statistics hypothesis summaries malformed")
    reader.json(UNCERTAINTY)
    return statistics


def _aggregate_reconciliation(
    frame: pd.DataFrame, comparison: dict[str, Any], basis: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    reverse_metrics = {dashboard: source for source, dashboard in METRIC_MAP.items()}
    for system in SYSTEMS:
        subset = frame.loc[frame["system"] == system]
        if len(subset) != 34:
            raise ValidityError(f"{basis} has wrong query count for {system}: {len(subset)}")
        expected_panel = comparison[system][basis]
        if expected_panel["query_n"] != 34:
            raise ValidityError(f"comparison table has wrong query count for {system}")
        for dashboard_name, source_name in reverse_metrics.items():
            observed = float(subset[dashboard_name].mean())
            expected = float(expected_panel["metrics"][source_name])
            delta = observed - expected
            if abs(delta) > 1e-12:
                raise ValidityError(
                    f"aggregate mismatch {basis}/{system}/{dashboard_name}: {observed} != {expected}"
                )
            records.append(
                {
                    "basis": basis,
                    "delta": delta,
                    "expected": expected,
                    "metric": dashboard_name,
                    "observed": observed,
                    "system": system,
                }
            )
    return records


def _base_frame(rows: list[dict[str, Any]], qa_by_id: dict[str, dict[str, Any]]) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    for row in rows:
        query_id = row.get("query_id")
        system = row.get("system")
        metrics = row.get("metrics")
        if query_id not in qa_by_id or system not in SYSTEMS or not isinstance(metrics, dict):
            raise ValidityError(f"malformed per-query row: {row!r}")
        if row.get("category") != qa_by_id[query_id]["category"]:
            raise ValidityError(f"category mismatch: {query_id}")
        record: dict[str, Any] = {
            "query_id": query_id,
            "query_text": qa_by_id[query_id]["question"],
            "category": row["category"],
            "system": system,
        }
        for source_name, dashboard_name in METRIC_MAP.items():
            value = metrics.get(source_name)
            if not isinstance(value, (int, float)):
                raise ValidityError(f"missing metric {source_name}: {system}/{query_id}")
            record[dashboard_name] = float(value)
        output.append(record)
    frame = pd.DataFrame(output)
    if len(frame) != 170 or frame[["query_id", "system"]].duplicated().any():
        raise ValidityError("per-query panel must contain 170 unique query/system rows")
    if set(frame["system"]) != set(SYSTEMS):
        raise ValidityError("per-query panel has incompatible systems")
    return frame


def build() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build primary dataframe and return Gate 1 audit."""

    reader = SourceReader()
    qa_rows = reader.jsonl(QA)
    if len(qa_rows) != 34:
        raise ValidityError(f"expected 34 QA rows, found {len(qa_rows)}")
    qa_by_id = {row["question_id"]: row for row in qa_rows}
    if len(qa_by_id) != 34:
        raise ValidityError("duplicate QA question IDs")
    if Counter(row["category"] for row in qa_rows) != Counter(CATEGORY_COUNTS):
        raise ValidityError("QA category counts differ from frozen contract")

    comparison = reader.json(COMPARISON)
    balanced = reader.json(BALANCED)
    if set(comparison) != set(SYSTEMS) or set(balanced) != set(SYSTEMS):
        raise ValidityError("aggregate files do not contain exact five-system panel")
    statistics = _validate_statistics(reader)
    positives, qrel_grades = _load_qrels(reader)
    if set(positives) != set(qa_by_id) or any(not chunks for chunks in positives.values()):
        raise ValidityError("every query must have positive final-pooled qrels")

    primary = _base_frame(reader.jsonl(PRIMARY), qa_by_id)
    known_gold = _base_frame(reader.jsonl(KNOWN_GOLD), qa_by_id)
    primary["qrel_base"] = "final_pooled"
    known_gold["qrel_base"] = "known_gold"

    rankings = {system: _ranking_map(reader, path) for system, path in RANKINGS.items()}
    expected_queries = set(qa_by_id)
    if any(set(panel) != expected_queries for panel in rankings.values()):
        raise ValidityError("ranking query sets differ from QA")

    gold_ranks: list[int] = []
    failures: list[str] = []
    for row in primary.itertuples(index=False):
        rank = _gold_rank(rankings[row.system][row.query_id], positives[row.query_id])
        gold_ranks.append(rank)
        failures.append(_failure_type(rank))
        if int(row.hit_at_5) != int(rank <= 5) or int(row.hit_at_10) != int(rank <= 10):
            raise ValidityError(f"gold-rank/hit mismatch: {row.system}/{row.query_id}")
    primary["gold_rank"] = gold_ranks
    primary["failure_type"] = failures

    hits_per_query = primary.groupby("query_id", sort=True)["hit_at_5"].sum().astype(int)
    primary["n_systems_hit_at_5"] = primary["query_id"].map(hits_per_query)
    primary["difficulty"] = 1.0 - primary["n_systems_hit_at_5"] / 5.0

    ordered_columns = [
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
    primary = primary[ordered_columns].sort_values(["query_id", "system"], kind="stable")
    known_reconciliation = _aggregate_reconciliation(known_gold, comparison, "known_gold")
    primary_reconciliation = _aggregate_reconciliation(primary, comparison, "final_pooled")

    null_counts = {column: int(value) for column, value in primary.isna().sum().items()}
    if any(null_counts.values()):
        raise ValidityError(f"null audit failed: {null_counts}")
    if set(primary["qrel_base"]) != {"final_pooled"}:
        raise ValidityError("primary dataframe silently mixed qrel bases")

    OUT.mkdir(parents=True, exist_ok=True)
    primary.to_csv(OUT / "per_query_pilot.csv", index=False, lineterminator="\n")
    primary.to_parquet(OUT / "per_query_pilot.parquet", index=False)
    _write_evidence_browser(reader, qa_rows, qrel_grades, rankings)

    audit = {
        "blacklisted_paths": sorted(path.relative_to(ROOT).as_posix() for path in BLACKLISTED),
        "blacklisted_sources_read": [],
        "category_counts": dict(sorted(CATEGORY_COUNTS.items())),
        "column_count": len(primary.columns),
        "h5_source_available": H5.is_file(),
        "known_gold_reconciliation": known_reconciliation,
        "null_counts": null_counts,
        "primary_qrel_base": "final_pooled",
        "primary_reconciliation": primary_reconciliation,
        "query_count": int(primary["query_id"].nunique()),
        "row_count": len(primary),
        "source_hashes": dict(sorted(reader.reads.items())),
        "statistics_summaries": statistics["summaries"],
        "status": "gate1_passed",
        "system_count": int(primary["system"].nunique()),
        "validity_guard": "passed_seed42_only",
    }
    (OUT / "gate1_reconciliation.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return primary, audit


def main() -> None:
    frame, audit = build()
    print(frame.head(10).to_string(index=False))
    print(
        json.dumps(
            {
                "blacklisted_sources_read": audit["blacklisted_sources_read"],
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
