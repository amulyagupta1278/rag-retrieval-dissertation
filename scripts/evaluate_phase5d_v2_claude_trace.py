#!/usr/bin/env python3
"""Evaluate V2 trace repeatability only; never read relevance or V1 outputs."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_phase5d_v2_prompt_rag_claude import (  # noqa: E402
    OUTPUT_ROOT,
    TRACE_DECISION_PATH,
    build_trace_plan,
    preflight,
)
from src.retrievers.prompt_rag_claude_v2 import (  # noqa: E402
    CANDIDATE_N,
    MODEL,
    TRACE_REQUEST_N,
    ClaudeContractError,
    request_sha256,
    validate_response,
)
from src.utils.atomic_io import write_json  # noqa: E402


PROTOCOL_PATH = ROOT / "audits/phase5b/repeatability_protocol.json"


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaudeContractError(f"invalid V2 trace artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ClaudeContractError(f"V2 trace artifact must be object: {path}")
    return value


def _pearson(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ClaudeContractError("correlation vectors differ or are empty")
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_ss = sum((value - left_mean) ** 2 for value in left)
    right_ss = sum((value - right_mean) ** 2 for value in right)
    if left_ss == 0 or right_ss == 0:
        return 1.0 if left == right else 0.0
    return numerator / math.sqrt(left_ss * right_ss)


def _kendall_tau_b(left: list[int], right: list[int]) -> float:
    concordant = discordant = ties_left = ties_right = 0
    for first in range(len(left) - 1):
        for second in range(first + 1, len(left)):
            delta_left = left[first] - left[second]
            delta_right = right[first] - right[second]
            if delta_left == 0 and delta_right == 0:
                continue
            if delta_left == 0:
                ties_left += 1
            elif delta_right == 0:
                ties_right += 1
            elif delta_left * delta_right > 0:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + ties_left)
        * (concordant + discordant + ties_right)
    )
    if denominator == 0:
        return 1.0 if left == right else 0.0
    return (concordant - discordant) / denominator


def compare(
    first: list[dict[str, Any]], second: list[dict[str, Any]]
) -> dict[str, float]:
    """Compute frozen five-metric repeatability panel."""

    if len(first) != CANDIDATE_N or len(second) != CANDIDATE_N:
        raise ClaudeContractError("repeatability rankings must contain 50 rows")
    left = {row["chunk_id"]: row for row in first}
    right = {row["chunk_id"]: row for row in second}
    if len(left) != CANDIDATE_N or set(left) != set(right):
        raise ClaudeContractError("repeatability candidate sets differ")
    ids = sorted(left)
    left_scores = [int(left[chunk_id]["score"]) for chunk_id in ids]
    right_scores = [int(right[chunk_id]["score"]) for chunk_id in ids]
    left_ranks = [int(left[chunk_id]["rank"]) for chunk_id in ids]
    right_ranks = [int(right[chunk_id]["rank"]) for chunk_id in ids]
    left_top = {row["chunk_id"] for row in first if row["rank"] <= 10}
    right_top = {row["chunk_id"] for row in second if row["rank"] <= 10}
    return {
        "candidate_score_agreement": sum(
            a == b for a, b in zip(left_scores, right_scores)
        )
        / CANDIDATE_N,
        "kendall_tau_b": _kendall_tau_b(left_scores, right_scores),
        "ranking_position_agreement": sum(
            a == b for a, b in zip(left_ranks, right_ranks)
        )
        / CANDIDATE_N,
        "spearman_rho": _pearson(
            [float(value) for value in left_ranks],
            [float(value) for value in right_ranks],
        ),
        "top_10_overlap": len(left_top & right_top) / 10,
    }


def evaluate() -> dict[str, Any]:
    """Revalidate exact V2 records and calculate no relevance metrics."""

    frozen = preflight()
    ledger = _json(OUTPUT_ROOT / "trace/control/ledger.json")
    if ledger.get("status") != "complete" or ledger.get(
        "attempted_generation_request_n"
    ) != TRACE_REQUEST_N:
        raise ClaudeContractError("V2 trace ledger is not complete 24-call scope")
    plan = build_trace_plan(frozen["trace_ids"])
    records: dict[str, dict[str, Any]] = {}
    for logical_id, query_id in plan:
        path = OUTPUT_ROOT / "trace/raw" / f"{logical_id.replace(':', '__')}.json"
        record = _json(path)
        if record.get("logical_request_id") != logical_id:
            raise ClaudeContractError("V2 trace logical ID mismatch")
        request = frozen["requests"][query_id]
        if record.get("raw_request") != request or record.get(
            "request_sha256"
        ) != request_sha256(request):
            raise ClaudeContractError("V2 trace request differs from frozen payload")
        validated = validate_response(
            record.get("raw_response"),
            expected_chunk_ids=frozen["rankings"][query_id],
        )
        if record.get("ranking") != validated["ranking"]:
            raise ClaudeContractError("saved V2 ranking differs from raw response")
        records[logical_id] = record

    protocol = _json(PROTOCOL_PATH)
    thresholds = {
        name: float(row["minimum"])
        for name, row in protocol["comparisons"].items()
    }
    comparisons: list[dict[str, Any]] = []
    all_pass = True
    roles = ("primary", "replicate-1", "replicate-2")
    for query_id in frozen["trace_ids"]:
        ids = [f"{query_id}:{role}" for role in roles]
        for left_index, right_index in ((0, 1), (0, 2), (1, 2)):
            metrics = compare(
                records[ids[left_index]]["ranking"],
                records[ids[right_index]]["ranking"],
            )
            passed = all(metrics[name] >= minimum for name, minimum in thresholds.items())
            all_pass = all_pass and passed
            comparisons.append(
                {
                    "left_logical_request_id": ids[left_index],
                    "metrics": metrics,
                    "passed": passed,
                    "query_id": query_id,
                    "right_logical_request_id": ids[right_index],
                }
            )
    return {
        "comparison_n": len(comparisons),
        "comparisons": comparisons,
        "first_valid_execution_role": "primary",
        "model": MODEL,
        "relevance_metrics_calculated": False,
        "schema_version": 2,
        "selected_query_ids": frozen["trace_ids"],
        "status": "repeatability_gate_passed" if all_pass else "repeatability_gate_failed",
        "thresholds": dict(sorted(thresholds.items())),
        "trace_record_n": len(records),
    }


def main() -> int:
    try:
        decision = evaluate()
        if TRACE_DECISION_PATH.exists():
            raise ClaudeContractError("V2 trace decision exists; refusing overwrite")
        write_json(TRACE_DECISION_PATH, decision, overwrite=False)
        return 0 if decision["status"] == "repeatability_gate_passed" else 2
    except ClaudeContractError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
