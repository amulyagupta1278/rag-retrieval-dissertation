#!/usr/bin/env python3
"""Fail-closed recomputation of historical retrieval metrics.

This script reads explicit corpus, query, qrels, and run paths. It never
selects historical inputs implicitly and never modifies those inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


OUTPUT_FILES = (
    "command.txt",
    "environment.json",
    "input_manifest.json",
    "per_query.jsonl",
    "recomputed_metrics.json",
    "hashes.txt",
    "findings.md",
)


class ValidationError(ValueError):
    """Raised when an input violates the forensic evaluation contract."""


@dataclass(frozen=True)
class QueryMetrics:
    """Binary-relevance metrics for one query and retrieval system."""

    mrr_at_5: float
    mrr_at_10: float
    recall_at_5: float
    recall_at_10: float
    ndcg_at_10: float
    graded_ndcg_at_10: float

    def to_dict(self) -> dict[str, float]:
        """Return stable field representation."""
        return {
            "mrr_at_5": self.mrr_at_5,
            "mrr_at_10": self.mrr_at_10,
            "ndcg_at_10": self.ndcg_at_10,
            "graded_ndcg_at_10": self.graded_ndcg_at_10,
            "recall_at_5": self.recall_at_5,
            "recall_at_10": self.recall_at_10,
        }


def sha256_file(path: Path) -> str:
    """Return streaming SHA-256 for a regular file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_file(path: Path, label: str) -> Path:
    path = path.resolve()
    if not path.is_file():
        raise ValidationError(f"{label} file does not exist: {path}")
    return path


def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    """Load non-empty JSONL and report actionable line errors."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValidationError(
                    f"{label} contains invalid JSON at {path}:{line_number}: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise ValidationError(
                    f"{label} record must be an object at {path}:{line_number}"
                )
            records.append(value)
    if not records:
        raise ValidationError(f"{label} is empty: {path}")
    return records


def _unique_identifier_map(
    records: Iterable[dict[str, Any]], key: str, label: str
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records, 1):
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{label} record {index} has missing or invalid {key}")
        if value in output:
            raise ValidationError(f"{label} contains duplicate {key}: {value}")
        output[value] = record
    return output


def load_qrels(path: Path) -> dict[str, dict[str, float]]:
    """Load four-column qrels, retaining finite relevance values."""
    qrels: dict[str, dict[str, float]] = {}
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            fields = raw.rstrip("\n").split("\t")
            if line_number == 1 and fields[0].strip().lower() in {"query_id", "qid"}:
                continue
            if len(fields) != 4:
                raise ValidationError(
                    f"qrels row must have four tab-separated fields at {path}:{line_number}"
                )
            query_id, _, chunk_id, raw_relevance = (field.strip() for field in fields)
            if not query_id or not chunk_id:
                raise ValidationError(f"qrels has empty query/chunk ID at {path}:{line_number}")
            try:
                relevance = float(raw_relevance)
            except ValueError as exc:
                raise ValidationError(
                    f"qrels relevance is not numeric at {path}:{line_number}: {raw_relevance!r}"
                ) from exc
            if not math.isfinite(relevance):
                raise ValidationError(
                    f"qrels relevance must be finite at {path}:{line_number}: {raw_relevance!r}"
                )
            pair = (query_id, chunk_id)
            if pair in seen:
                raise ValidationError(f"qrels contains duplicate judgment: {query_id}/{chunk_id}")
            seen.add(pair)
            qrels.setdefault(query_id, {})[chunk_id] = relevance
    if not qrels:
        raise ValidationError(f"qrels is empty: {path}")
    return qrels


def load_reported_summary(path: Path) -> dict[str, dict[str, float]]:
    """Load historical aggregate CSV fields needed for forensic comparison."""
    required = {
        "MRR@5": "mrr_at_5",
        "MRR@10": "mrr_at_10",
        "Recall@5": "recall_at_5",
        "Recall@10": "recall_at_10",
        "nDCG@10": "ndcg_at_10",
    }
    output: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "Retriever" not in reader.fieldnames:
            raise ValidationError(f"reported summary lacks Retriever column: {path}")
        missing_columns = sorted(set(required) - set(reader.fieldnames))
        if missing_columns:
            raise ValidationError(
                f"reported summary lacks required columns: {missing_columns}"
            )
        for line_number, row in enumerate(reader, 2):
            system = (row.get("Retriever") or "").strip().lower()
            if not system:
                raise ValidationError(f"reported summary has empty system at {path}:{line_number}")
            if system in output:
                raise ValidationError(f"reported summary contains duplicate system: {system}")
            values: dict[str, float] = {}
            for column, metric_name in required.items():
                try:
                    value = float(row[column])
                except (TypeError, ValueError) as exc:
                    raise ValidationError(
                        f"reported summary has invalid {column} at {path}:{line_number}"
                    ) from exc
                if not math.isfinite(value):
                    raise ValidationError(
                        f"reported summary has non-finite {column} at {path}:{line_number}"
                    )
                values[metric_name] = value
            output[system] = values
    if not output:
        raise ValidationError(f"reported summary is empty: {path}")
    return output


def mrr_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Return reciprocal rank of first relevant item within cutoff."""
    if not relevant_ids:
        raise ValidationError("cannot compute MRR with empty gold set")
    for rank, chunk_id in enumerate(ranked_ids[:k], 1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Return fraction of relevant chunks retrieved within cutoff."""
    if not relevant_ids:
        raise ValidationError("cannot compute recall with empty gold set")
    return len(set(ranked_ids[:k]) & relevant_ids) / len(relevant_ids)


def binary_ndcg_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Return binary nDCG, treating every qrel with relevance > 0 equally."""
    if not relevant_ids:
        raise ValidationError("cannot compute nDCG with empty gold set")
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked_ids[:k], 1)
        if chunk_id in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg


def graded_ndcg_at_k(ranked_ids: list[str], gains: dict[str, float], k: int) -> float:
    """Return nDCG using positive qrel values as graded gains."""
    positive_gains = {chunk_id: gain for chunk_id, gain in gains.items() if gain > 0}
    if not positive_gains:
        raise ValidationError("cannot compute graded nDCG with empty gold set")
    dcg = sum(
        positive_gains.get(chunk_id, 0.0) / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked_ids[:k], 1)
    )
    ideal = sorted(positive_gains.values(), reverse=True)[:k]
    idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal, 1))
    return dcg / idcg


def compute_query_metrics(
    ranked_ids: list[str],
    relevant_ids: set[str],
    gains: dict[str, float] | None = None,
) -> QueryMetrics:
    """Validate ranking and calculate approved Phase 0 metrics."""
    if len(ranked_ids) != len(set(ranked_ids)):
        duplicates = sorted({item for item in ranked_ids if ranked_ids.count(item) > 1})
        raise ValidationError(f"ranked results contain duplicate chunk IDs: {duplicates}")
    return QueryMetrics(
        mrr_at_5=mrr_at_k(ranked_ids, relevant_ids, 5),
        mrr_at_10=mrr_at_k(ranked_ids, relevant_ids, 10),
        recall_at_5=recall_at_k(ranked_ids, relevant_ids, 5),
        recall_at_10=recall_at_k(ranked_ids, relevant_ids, 10),
        ndcg_at_10=binary_ndcg_at_k(ranked_ids, relevant_ids, 10),
        graded_ndcg_at_10=graded_ndcg_at_k(
            ranked_ids, gains or {chunk_id: 1.0 for chunk_id in relevant_ids}, 10
        ),
    )


def _validate_run(
    records: list[dict[str, Any]],
    system: str,
    known_chunks: set[str],
) -> dict[str, list[str]]:
    by_query = _unique_identifier_map(records, "query_id", f"run {system}")
    rankings: dict[str, list[str]] = {}
    for query_id, run in by_query.items():
        results = run.get("results")
        if not isinstance(results, list):
            raise ValidationError(f"run {system}/{query_id} has invalid results list")
        if not results:
            raise ValidationError(f"run {system}/{query_id} has empty results list")
        ranked: list[str] = []
        for position, result in enumerate(results, 1):
            if not isinstance(result, dict):
                raise ValidationError(
                    f"run {system}/{query_id} result {position} is not an object"
                )
            chunk_id = result.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id:
                raise ValidationError(
                    f"run {system}/{query_id} result {position} has invalid chunk_id"
                )
            if chunk_id not in known_chunks:
                raise ValidationError(
                    f"run {system}/{query_id} references unknown chunk ID: {chunk_id}"
                )
            rank = result.get("rank")
            if rank is not None and (isinstance(rank, bool) or not isinstance(rank, int) or rank != position):
                raise ValidationError(
                    f"run {system}/{query_id} result {position} has invalid rank: {rank!r}"
                )
            ranked.append(chunk_id)
        if len(ranked) != len(set(ranked)):
            duplicates = sorted({item for item in ranked if ranked.count(item) > 1})
            raise ValidationError(
                f"run {system}/{query_id} contains duplicate ranked chunk IDs: {duplicates}"
            )
        rankings[query_id] = ranked
    return rankings


def evaluate(
    chunks: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    qrels: dict[str, dict[str, float]],
    runs: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate compatible query sets and compute deterministic results."""
    chunk_map = _unique_identifier_map(chunks, "chunk_id", "chunks")
    query_map = _unique_identifier_map(queries, "question_id", "queries")
    expected_queries = set(query_map)
    qrels_queries = set(qrels)
    if qrels_queries != expected_queries:
        missing = sorted(expected_queries - qrels_queries)
        extra = sorted(qrels_queries - expected_queries)
        raise ValidationError(f"qrels query set mismatch: missing={missing}, extra={extra}")

    relevant: dict[str, set[str]] = {}
    for query_id in sorted(expected_queries):
        unknown_judgments = sorted(set(qrels[query_id]) - set(chunk_map))
        if unknown_judgments:
            raise ValidationError(
                f"qrels for {query_id} references unknown chunks: {unknown_judgments}"
            )
        gold = {chunk_id for chunk_id, value in qrels[query_id].items() if value > 0}
        if not gold:
            raise ValidationError(f"query has empty positive gold set: {query_id}")
        relevant[query_id] = gold

    rankings_by_system: dict[str, dict[str, list[str]]] = {}
    for system in sorted(runs):
        rankings = _validate_run(runs[system], system, set(chunk_map))
        run_queries = set(rankings)
        if run_queries != expected_queries:
            missing = sorted(expected_queries - run_queries)
            extra = sorted(run_queries - expected_queries)
            raise ValidationError(
                f"run {system} query set mismatch: missing={missing}, extra={extra}"
            )
        rankings_by_system[system] = rankings

    if not rankings_by_system:
        raise ValidationError("at least one run is required")
    query_sets = {tuple(sorted(values)) for values in rankings_by_system.values()}
    if len(query_sets) != 1:
        raise ValidationError("run files have incompatible query sets")

    per_query: list[dict[str, Any]] = []
    aggregates: dict[str, Any] = {}
    for system in sorted(rankings_by_system):
        system_rows: list[QueryMetrics] = []
        for query_id in sorted(expected_queries):
            ranked = rankings_by_system[system][query_id]
            metrics = compute_query_metrics(ranked, relevant[query_id], qrels[query_id])
            system_rows.append(metrics)
            per_query.append(
                {
                    "metrics": metrics.to_dict(),
                    "query_id": query_id,
                    "ranked_chunk_ids_top_10": ranked[:10],
                    "relevant_chunk_ids": sorted(relevant[query_id]),
                    "system": system,
                }
            )
        keys = tuple(system_rows[0].to_dict())
        aggregates[system] = {
            "macro_metrics": {
                key: sum(row.to_dict()[key] for row in system_rows) / len(system_rows)
                for key in keys
            },
            "query_count": len(system_rows),
        }
    return per_query, {"metric_definition": "binary_relevance_gt_zero", "systems": aggregates}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--run must use NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("--run must use non-empty NAME=PATH")
    return name.strip(), Path(raw_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--reported-summary", type=Path, required=True)
    parser.add_argument("--run", type=_parse_run, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    chunks_path = _require_file(args.chunks, "chunks")
    queries_path = _require_file(args.queries, "queries")
    qrels_path = _require_file(args.qrels, "qrels")
    reported_summary_path = _require_file(args.reported_summary, "reported summary")
    run_paths: dict[str, Path] = {}
    for name, path in args.run:
        if name in run_paths:
            raise ValidationError(f"duplicate --run system name: {name}")
        run_paths[name] = _require_file(path, f"run {name}")

    output_dir = args.output_dir.resolve()
    collisions = [name for name in OUTPUT_FILES if (output_dir / name).exists()]
    if output_dir.exists() and (collisions or any(output_dir.iterdir())) and not args.overwrite:
        raise ValidationError(
            f"output path collision at {output_dir}; pass --overwrite to replace Phase 0 outputs"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    input_paths = {
        "chunks": chunks_path,
        "qrels": qrels_path,
        "queries": queries_path,
        "reported_summary": reported_summary_path,
        **{f"run:{name}": path for name, path in sorted(run_paths.items())},
    }
    manifest = {
        "git_head": _git_head(),
        "inputs": {
            label: {
                "bytes": path.stat().st_size,
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for label, path in sorted(input_paths.items())
        },
    }

    chunks = load_jsonl(chunks_path, "chunks")
    queries = load_jsonl(queries_path, "queries")
    qrels = load_qrels(qrels_path)
    reported = load_reported_summary(reported_summary_path)
    runs = {name: load_jsonl(path, f"run {name}") for name, path in run_paths.items()}
    per_query, aggregate = evaluate(chunks, queries, qrels, runs)
    computed_systems = set(aggregate["systems"])
    if set(reported) != computed_systems:
        raise ValidationError(
            "reported summary system set mismatch: "
            f"reported={sorted(reported)}, runs={sorted(computed_systems)}"
        )
    aggregate["reported_comparison"] = {
        system: {
            "matches_reported_at_4_decimals": all(
                round(aggregate["systems"][system]["macro_metrics"][metric], 4)
                == round(value, 4)
                for metric, value in reported[system].items()
            ),
            "reported": reported[system],
        }
        for system in sorted(reported)
    }

    command = shlex.join([sys.executable, str(Path(__file__).resolve()), *(argv or sys.argv[1:])])
    environment = {
        "git_head": manifest["git_head"],
        "platform": platform.platform(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }
    jsonl = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in per_query
    )
    findings = (
        "# Phase 0 historical metric recomputation\n\n"
        "- Status: numerically recomputable from committed inputs.\n"
        "- Scope: forensic 28-query benchmark; not final inferential evidence.\n"
        "- Relevance: binary; every qrel value greater than zero is relevant.\n"
        "- Supplementary analysis: graded nDCG@10 uses positive qrel values as gains.\n"
        "- Aggregation: unweighted macro mean across queries.\n"
        "- nDCG root cause: historical qrels contain grades 1 and 2, but historical code "
        "converted all positive grades to a set of chunk IDs. Published nDCG therefore uses "
        "binary relevance. A graded-relevance recomputation answers a different metric and "
        "must not be compared as if it were the same definition. Published binary nDCG "
        "reproduction remains unchanged; graded nDCG is supplementary.\n"
    )

    contents = {
        "command.txt": command + "\n",
        "environment.json": _json_text(environment),
        "input_manifest.json": _json_text(manifest),
        "per_query.jsonl": jsonl,
        "recomputed_metrics.json": _json_text(aggregate),
        "findings.md": findings,
    }
    for name, content in contents.items():
        _atomic_write(output_dir / name, content)
    hashes = "".join(
        f"{sha256_file(output_dir / name)}  {name}\n"
        for name in sorted(contents)
    )
    _atomic_write(output_dir / "hashes.txt", hashes)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
