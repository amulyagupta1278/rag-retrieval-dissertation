#!/usr/bin/env python3
"""Validate Phase 5D V3 evidence and freeze 34 primary rankings offline."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_phase5d_v3_transport_recovery import (  # noqa: E402
    AMBIGUOUS_RESERVE_USD,
    CUMULATIVE_HARD_CAP_USD,
    OUTPUT_ROOT,
    RECORDED_PRIOR_SPEND_USD,
    RESERVED_PRIOR_EXPOSURE_USD,
    preflight,
)
from src.retrievers.prompt_rag_claude_v2 import (  # noqa: E402
    CANDIDATE_N,
    MODEL,
    ClaudeContractError,
    request_sha256,
    validate_response,
)
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file, sha256_text  # noqa: E402


TRACE_ROOT = ROOT / "runs/v2/phase5d_prompt_rag_claude_v2/trace"
RANKINGS_PATH = OUTPUT_ROOT / "complete_primary_rankings.jsonl"
SUMMARY_PATH = OUTPUT_ROOT / "operational_summary.json"
CHECKPOINT_PATH = OUTPUT_ROOT / "phase5d_v3_checkpoint.json"
MANIFEST_PATH = OUTPUT_ROOT / "artifact_manifest.json"
EXECUTION_BASE_COMMIT = "ec14f756aa29c0c5d819b517dd17ba69227ae1b7"
APPROVED_FREEZE_COMMIT = "fa05de13da0c0ae46f81d4f53d92d4df2d9328d4"


def load_json(path: Path) -> dict[str, Any]:
    """Load one required JSON object."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaudeContractError(f"invalid checkpoint JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ClaudeContractError(f"checkpoint JSON must be object: {path}")
    return value


def validate_record(
    path: Path, *, logical_id: str, query_id: str, frozen: dict[str, Any]
) -> dict[str, Any]:
    """Revalidate one stored provider response against frozen request contract."""

    record = load_json(path)
    if record.get("logical_request_id") != logical_id:
        raise ClaudeContractError(f"logical request mismatch: {path}")
    request = frozen["requests"][query_id]
    if record.get("raw_request") != request:
        raise ClaudeContractError(f"stored request differs from freeze: {path}")
    if record.get("request_sha256") != request_sha256(request):
        raise ClaudeContractError(f"stored request hash mismatch: {path}")
    raw_response = record.get("raw_response")
    if not isinstance(raw_response, dict):
        raise ClaudeContractError(f"stored response is not object: {path}")
    if record.get("response_sha256") != sha256_text(stable_json(raw_response)):
        raise ClaudeContractError(f"stored response hash mismatch: {path}")
    validated = validate_response(
        raw_response, expected_chunk_ids=frozen["rankings"][query_id]
    )
    if record.get("model") != MODEL or validated["model"] != MODEL:
        raise ClaudeContractError(f"stored model mismatch: {path}")
    if record.get("ranking") != validated["ranking"]:
        raise ClaudeContractError(f"stored ranking mismatch: {path}")
    ranking = validated["ranking"]
    if len(ranking) != CANDIDATE_N or len({row["chunk_id"] for row in ranking}) != CANDIDATE_N:
        raise ClaudeContractError(f"stored ranking must contain 50 unique chunks: {path}")
    if ranking != sorted(ranking, key=lambda row: (-row["score"], row["chunk_id"])):
        raise ClaudeContractError(f"stored ranking tie order mismatch: {path}")
    usage = record.get("usage")
    if not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens"}:
        raise ClaudeContractError(f"stored usage mismatch: {path}")
    if not isinstance(record.get("latency_ms"), (int, float)) or record["latency_ms"] <= 0:
        raise ClaudeContractError(f"stored latency invalid: {path}")
    return record


def freeze(*, overwrite: bool = False) -> dict[str, Any]:
    """Freeze successful recovery evidence without network or relevance inputs."""

    frozen = preflight()
    ledger_path = OUTPUT_ROOT / "control/ledger.json"
    ledger = load_json(ledger_path)
    expected_recovery_ids = [logical_id for logical_id, _ in frozen["full_plan"]]
    if ledger.get("status") != "complete":
        raise ClaudeContractError("V3 recovery ledger is not complete")
    if ledger.get("attempted_generation_request_n") != 26:
        raise ClaudeContractError("V3 recovery attempt count must equal 26")
    if ledger.get("completed_logical_request_ids") != expected_recovery_ids:
        raise ClaudeContractError("V3 completed request order differs from freeze")
    failure_paths = sorted((OUTPUT_ROOT / "failures").glob("*.json")) if (OUTPUT_ROOT / "failures").exists() else []
    if failure_paths:
        raise ClaudeContractError("V3 recovery contains failure records")

    ranking_rows: list[dict[str, Any]] = []
    recovery_records: list[dict[str, Any]] = []
    for logical_id, query_id in frozen["full_plan"]:
        path = OUTPUT_ROOT / "raw" / f"{logical_id.replace(':', '__')}.json"
        record = validate_record(
            path, logical_id=logical_id, query_id=query_id, frozen=frozen
        )
        recovery_records.append(record)
        ranking_rows.append(
            {
                "query_id": query_id,
                "ranking": record["ranking"],
                "source_logical_request_id": logical_id,
                "source_record_path": str(path.relative_to(ROOT)),
                "source_scope": "v3_recovery_primary",
                "system": "prompt_rag_claude_haiku_4_5_reranker",
            }
        )

    for query_id in frozen["trace_ids"]:
        logical_id = f"{query_id}:primary"
        path = TRACE_ROOT / "raw" / f"{query_id}__primary.json"
        record = validate_record(
            path, logical_id=logical_id, query_id=query_id, frozen=frozen
        )
        ranking_rows.append(
            {
                "query_id": query_id,
                "ranking": record["ranking"],
                "source_logical_request_id": logical_id,
                "source_record_path": str(path.relative_to(ROOT)),
                "source_scope": "v2_trace_primary",
                "system": "prompt_rag_claude_haiku_4_5_reranker",
            }
        )

    if len(ranking_rows) != 34 or {row["query_id"] for row in ranking_rows} != set(frozen["query_ids"]):
        raise ClaudeContractError("complete primary rankings must cover all 34 queries")

    input_tokens = sum(row["usage"]["input_tokens"] for row in recovery_records)
    output_tokens = sum(row["usage"]["output_tokens"] for row in recovery_records)
    if input_tokens != ledger.get("actual_input_tokens") or output_tokens != ledger.get("actual_output_tokens"):
        raise ClaudeContractError("V3 ledger usage differs from raw records")
    latencies = sorted(float(row["latency_ms"]) for row in recovery_records)
    p95 = latencies[math.ceil(0.95 * len(latencies)) - 1]
    recovery_cost = float(ledger["recovery_observed_cost_usd"])
    cumulative_recorded = round(
        float(ledger["cumulative_recorded_observed_cost_usd"]), 6
    )
    reserved_exposure = round(
        float(ledger["cumulative_budgeted_exposure_usd"]), 6
    )
    if abs(cumulative_recorded - (RECORDED_PRIOR_SPEND_USD + recovery_cost)) > 1e-12:
        raise ClaudeContractError("recorded cumulative cost arithmetic mismatch")
    if abs(reserved_exposure - (RESERVED_PRIOR_EXPOSURE_USD + recovery_cost)) > 1e-12:
        raise ClaudeContractError("reserved exposure arithmetic mismatch")
    if reserved_exposure > CUMULATIVE_HARD_CAP_USD:
        raise ClaudeContractError("V3 reserved exposure exceeded hard cap")

    summary = {
        "automatic_retry_n": 0,
        "failure_n": 0,
        "latency_ms": {
            "mean": statistics.fmean(latencies),
            "median": statistics.median(latencies),
            "p95": p95,
            "p95_method": "nearest-rank",
            "sample_n": len(latencies),
        },
        "model": MODEL,
        "recovery": {
            "actual_input_tokens": input_tokens,
            "actual_output_tokens": output_tokens,
            "attempted_request_n": 26,
            "observed_cost_usd": recovery_cost,
            "valid_request_n": 26,
        },
        "schema_version": 1,
        "spend": {
            "ambiguous_prior_attempt_reserve_usd": AMBIGUOUS_RESERVE_USD,
            "cumulative_hard_cap_usd": CUMULATIVE_HARD_CAP_USD,
            "cumulative_recorded_observed_cost_usd": cumulative_recorded,
            "recorded_prior_spend_usd": RECORDED_PRIOR_SPEND_USD,
            "reserved_cumulative_exposure_usd": reserved_exposure,
            "reserved_margin_usd": round(
                CUMULATIVE_HARD_CAP_USD - reserved_exposure, 6
            ),
        },
        "status": "v3_recovery_complete",
    }
    checkpoint = {
        "answer_generation_performed": False,
        "approved_freeze_commit": APPROVED_FREEZE_COMMIT,
        "automatic_retries": 0,
        "complete_primary_rankings": {
            "query_n": 34,
            "ranking_depth": 50,
            "trace_primary_n": 8,
            "v3_recovery_primary_n": 26,
        },
        "execution_base_commit": EXECUTION_BASE_COMMIT,
        "owner_judging_performed": False,
        "pool_expansion_performed": False,
        "relevance_metrics_calculated": False,
        "rerun_after_wrapper_error": False,
        "schema_version": 1,
        "status": "phase5d_v3_recovery_complete_rankings_frozen",
        "wrapper_post_runner_error": {
            "effect_on_runner": "none; ledger was already complete",
            "message": "zsh:5: read-only variable: status",
            "occurred": True,
        },
    }
    write_jsonl(RANKINGS_PATH, ranking_rows, key="query_id", overwrite=overwrite)
    write_json(SUMMARY_PATH, summary, overwrite=overwrite)
    write_json(CHECKPOINT_PATH, checkpoint, overwrite=overwrite)

    fixed_paths = [
        ROOT / "audits/phase5d_v2_full/failure_manifest.json",
        ROOT / "audits/phase5d_v3_recovery/freeze_manifest.json",
        ROOT / "audits/phase5d_v3_recovery/live_execution_approval.json",
        ROOT / "configs/prompt_rag_claude_v3_transport_recovery.json",
        ROOT / "prompts/prompt_rag_retrieval_v1.txt",
        TRACE_ROOT / "artifact_manifest.json",
        ROOT / "scripts/freeze_phase5d_v3_recovery.py",
        ROOT / "scripts/run_phase5d_v3_transport_recovery.py",
        ROOT / "tests/test_phase5d_v3_recovery_checkpoint.py",
    ]
    output_paths = sorted(
        path for path in OUTPUT_ROOT.rglob("*") if path.is_file() and path != MANIFEST_PATH
    )
    artifact_paths = sorted(set(fixed_paths + output_paths))
    manifest = {
        "artifact_hashes": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in artifact_paths
        },
        "artifact_n": len(artifact_paths),
        "complete_primary_query_n": 34,
        "credentials_stored": False,
        "generation_performed": False,
        "manifest_self_hash_excluded": True,
        "owner_judging_performed": False,
        "pool_expansion_performed": False,
        "relevance_metrics_included": False,
        "schema_version": 1,
        "status": "phase5d_v3_recovery_artifacts_frozen",
    }
    write_json(MANIFEST_PATH, manifest, overwrite=overwrite)
    return manifest


def parser() -> argparse.ArgumentParser:
    """Build command-line parser."""

    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--overwrite", action="store_true")
    return result


def main() -> int:
    """Freeze artifacts and print non-sensitive counts."""

    args = parser().parse_args()
    manifest = freeze(overwrite=args.overwrite)
    print(stable_json({"artifact_n": manifest["artifact_n"], "query_n": 34, "status": manifest["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
