#!/usr/bin/env python3
"""Run only remaining 160 requests in owner-approved Phase 7 V2 panel."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.run_phase7_v2_generation_trace as trace_runner  # noqa: E402
from src.generation.phase7_freeze import Phase7ExecutionFailure  # noqa: E402
from src.generation.phase7_v2_freeze import (  # noqa: E402
    HARD_COST_CAP_USD,
    MAX_OUTPUT_TOKENS,
    MODEL,
    V1_SPENT_USD,
    assert_v2_output_path,
    projected_cumulative_exposure_usd,
    request_sha256,
    validate_provider_response,
)
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file, sha256_text  # noqa: E402


RUN_ROOT = ROOT / "runs/v2/phase7_generation_claude_top3_v2"
V1_ROOT = ROOT / "runs/v2/phase7_generation_claude_top3"
TRACE_ROOT = RUN_ROOT / "trace_v2"
FULL_ROOT = RUN_ROOT / "full_v2"
PAYLOAD_PATH = RUN_ROOT / "blinded/request_payloads.jsonl"
REQUEST_PLAN_PATH = RUN_ROOT / "sealed/request_plan.jsonl"
COST_PLAN_PATH = RUN_ROOT / "cost_plan.json"
APPROVAL_PATH = ROOT / "audits/phase7_generation/v2/full_execution_approval.json"
TRACE_CHECKPOINT_PATH = ROOT / "audits/phase7_generation/v2/trace_v2_success_checkpoint.json"
APPROVED_EVIDENCE_COMMIT = "04c68403eaf449f836ab90f564f8ad14adbc5b07"
EXPECTED_APPROVAL = (
    "Approve Phase 7 V2 remaining 160-request full-panel execution at evidence "
    "commit 04c68403eaf449f836ab90f564f8ad14adbc5b07, using "
    "claude-haiku-4-5-20251001, frozen 512-token configuration, prompt, schema, "
    "top-3 contexts, request plan, temperature 0, exact-model policy, zero "
    "retries, no fallback, no replacement, and separate V2 outputs.\n\n"
    "Reuse the 10 successful V2 trace records only where request hashes exactly "
    "match frozen full-panel requests. Do not dispatch or bill those 10 requests "
    "again.\n\nObserved cumulative Phase 7 cost is $0.038404. Remaining "
    "160-request worst-case cost is $1.040134, ambiguous-dispatch reserve is "
    "$0.007295, and projected cumulative worst-case exposure is $1.085833 under "
    "cumulative $3.00 hard cap.\n\nStop immediately on model drift, truncation, "
    "malformed output, invalid citations, missing usage, ambiguous dispatch, "
    "credential failure, or projected cost-cap breach.\n\nPreserve every success "
    "and failure. Do not retry, backfill, replace, overwrite, or select outputs. "
    "Freeze and commit full-panel ledger, 170-record coverage manifest, costs, "
    "token usage, latency, failures, hashes, tests, and secret scan.\n\nDo not run "
    "LLM judging, owner-audit scoring, H5 analysis, Phase 8 work, or additional API "
    "calls after generation. Stop after full-panel validation and commit."
)
TRACE_INPUT_TOKENS = 21052
TRACE_OUTPUT_TOKENS = 2301
TRACE_OBSERVED_COST_USD = 0.032557
REMAINING_N = 160


class FullPanelContractError(ValueError):
    """Raised before dispatch when full-panel contract differs."""


def _verify_approval() -> None:
    approval = trace_runner._json(APPROVAL_PATH)
    expected = {
        "approved_evidence_commit": APPROVED_EVIDENCE_COMMIT,
        "ambiguous_dispatch_reserve_usd": 0.007295,
        "hard_cap_usd": HARD_COST_CAP_USD,
        "model": MODEL,
        "observed_cumulative_usd": 0.038404,
        "owner_statement": EXPECTED_APPROVAL,
        "projected_cumulative_worst_case_usd": 1.085833,
        "remaining_request_n": REMAINING_N,
        "remaining_worst_case_usd": 1.040134,
        "reuse_trace_record_n": 10,
        "status": "owner_approved",
    }
    for field, value in expected.items():
        if approval.get(field) != value:
            raise FullPanelContractError(f"full-run approval differs: {field}")
    hashes = {
        "config_sha256": RUN_ROOT / "execution_config.json",
        "freeze_manifest_sha256": RUN_ROOT / "freeze_manifest.json",
        "trace_checkpoint_sha256": TRACE_CHECKPOINT_PATH,
        "trace_manifest_sha256": TRACE_ROOT / "trace_manifest.json",
        "trace_reuse_manifest_sha256": TRACE_ROOT / "sealed/reuse_manifest.jsonl",
    }
    for field, path in hashes.items():
        if approval.get(field) != sha256_file(path):
            raise FullPanelContractError(f"full-run approval hash differs: {field}")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", APPROVED_EVIDENCE_COMMIT, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FullPanelContractError("approved evidence commit is not current history")


def _available_ids(request: Mapping[str, Any]) -> list[str]:
    try:
        context = json.loads(request["messages"][0]["content"])
        return [item["evidence_id"] for item in context["evidence"]]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise FullPanelContractError("frozen request context is invalid") from exc


def preflight() -> dict[str, Any]:
    """Validate trace reuse and exact 160-request remainder without credentials."""

    trace_runner.preflight()
    _verify_approval()
    assert_v2_output_path(FULL_ROOT, v2_root=RUN_ROOT, v1_root=V1_ROOT)
    cost = trace_runner._json(COST_PLAN_PATH)
    payload_rows = trace_runner._jsonl(PAYLOAD_PATH)
    plan_rows = trace_runner._jsonl(REQUEST_PLAN_PATH)
    payloads = {row["blinded_request_id"]: row for row in payload_rows}
    plans = {row["blinded_request_id"]: row for row in plan_rows}
    if len(payloads) != 170 or len(plans) != 170 or set(payloads) != set(plans):
        raise FullPanelContractError("frozen full panel differs")

    trace_ledger = trace_runner._json(TRACE_ROOT / "sealed/ledger.json")
    trace_summary = trace_runner._json(TRACE_ROOT / "operational_summary.json")
    reuse_rows = trace_runner._jsonl(TRACE_ROOT / "sealed/reuse_manifest.jsonl")
    if (
        trace_ledger.get("status") != "complete"
        or trace_ledger.get("attempted_request_n") != 10
        or len(reuse_rows) != 10
        or trace_summary.get("v2_input_tokens") != TRACE_INPUT_TOKENS
        or trace_summary.get("v2_output_tokens") != TRACE_OUTPUT_TOKENS
        or trace_summary.get("v2_observed_cost_usd") != TRACE_OBSERVED_COST_USD
    ):
        raise FullPanelContractError("successful trace checkpoint differs")

    trace_ids: set[str] = set()
    trace_coverage: list[dict[str, Any]] = []
    for reuse in reuse_rows:
        blinded_id = reuse.get("blinded_request_id")
        payload = payloads.get(blinded_id)
        plan = plans.get(blinded_id)
        if payload is None or plan is None or blinded_id in trace_ids:
            raise FullPanelContractError("trace reuse mapping differs")
        request = payload["request"]
        if (
            reuse.get("reusable_in_v2_panel") is not True
            or reuse.get("frozen_panel_request_sha256") != payload["request_sha256"]
            or request_sha256(request) != payload["request_sha256"]
        ):
            raise FullPanelContractError("trace request cannot be reused")
        raw_path = TRACE_ROOT / f"blinded/raw_responses/{blinded_id}.json"
        answer_path = TRACE_ROOT / f"blinded/validated_answers/{blinded_id}.json"
        raw = trace_runner._json(raw_path)
        validated = validate_provider_response(
            raw,
            available_evidence_ids=_available_ids(request),
        )
        response_hash = sha256_text(stable_json(raw))
        if (
            reuse.get("response_sha256") != response_hash
            or trace_runner._json(answer_path).get("response_sha256") != response_hash
        ):
            raise FullPanelContractError("trace response hash differs")
        trace_ids.add(blinded_id)
        trace_coverage.append(
            {
                "blinded_request_id": blinded_id,
                "dispatched_in_full_run": False,
                "logical_request_id": plan["logical_request_id"],
                "raw_response_path": str(raw_path.relative_to(ROOT)),
                "request_sha256": payload["request_sha256"],
                "response_id": validated["response_id"],
                "response_sha256": response_hash,
                "source": "trace_v2_reuse",
                "validated_answer_path": str(answer_path.relative_to(ROOT)),
            }
        )

    remaining: list[dict[str, Any]] = []
    for plan in plan_rows:
        blinded_id = plan["blinded_request_id"]
        if blinded_id in trace_ids:
            continue
        payload = payloads[blinded_id]
        request = payload["request"]
        if (
            request.get("max_tokens") != MAX_OUTPUT_TOKENS
            or request_sha256(request) != plan["request_hash"]
        ):
            raise FullPanelContractError("remaining request differs from frozen panel")
        remaining.append(
            {
                "available_evidence_ids": _available_ids(request),
                "blinded_request_id": blinded_id,
                "logical_request_id": plan["logical_request_id"],
                "planned_input_token_envelope": plan["planned_input_token_envelope"],
                "request": request,
                "request_sha256": payload["request_sha256"],
            }
        )
    if len(remaining) != REMAINING_N:
        raise FullPanelContractError("remaining request count differs")
    remaining_input = sum(row["planned_input_token_envelope"] for row in remaining)
    if remaining_input != cost["remaining_after_trace"]["input_token_envelope"]:
        raise FullPanelContractError("remaining token envelope differs")
    projected = projected_cumulative_exposure_usd(
        v2_observed_input_tokens=TRACE_INPUT_TOKENS,
        v2_observed_output_tokens=TRACE_OUTPUT_TOKENS,
        unexecuted_input_token_envelope=remaining_input,
        unexecuted_request_n=REMAINING_N,
        ambiguous_dispatch_reserve_usd=cost["ambiguous_dispatch_reserve"]["usd"],
    )
    if abs(projected - 1.085833) > 1e-12 or projected > HARD_COST_CAP_USD:
        raise FullPanelContractError("initial full-run cost projection differs")
    return {
        "cost": cost,
        "projected_initial_usd": projected,
        "remaining": remaining,
        "trace_coverage": trace_coverage,
    }


def _initial_ledger(rows: list[dict[str, Any]], projected: float) -> dict[str, Any]:
    return {
        "attempted_request_n": 0,
        "billing_ambiguity": False,
        "completed_blinded_request_ids": [],
        "hard_cap_usd": HARD_COST_CAP_USD,
        "planned_blinded_request_ids": [row["blinded_request_id"] for row in rows],
        "projected_cumulative_worst_case_usd": projected,
        "retry_n": 0,
        "reused_trace_record_n": 10,
        "schema_version": 2,
        "status": "ready",
        "trace_dispatch_n": 0,
        "v1_spent_usd": V1_SPENT_USD,
        "v2_full_input_tokens": 0,
        "v2_full_observed_cost_usd": 0.0,
        "v2_full_output_tokens": 0,
        "v2_trace_input_tokens": TRACE_INPUT_TOKENS,
        "v2_trace_observed_cost_usd": TRACE_OBSERVED_COST_USD,
        "v2_trace_output_tokens": TRACE_OUTPUT_TOKENS,
    }


def _save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_json(path, ledger, overwrite=path.exists())


def _projected(frozen: dict[str, Any], ledger: dict[str, Any], completed: list[dict[str, Any]]) -> float:
    completed_envelope = sum(row["planned_input_token_envelope"] for row in completed)
    total_remaining_input = sum(
        row["planned_input_token_envelope"] for row in frozen["remaining"]
    )
    return projected_cumulative_exposure_usd(
        v2_observed_input_tokens=TRACE_INPUT_TOKENS + ledger["v2_full_input_tokens"],
        v2_observed_output_tokens=TRACE_OUTPUT_TOKENS + ledger["v2_full_output_tokens"],
        unexecuted_input_token_envelope=total_remaining_input - completed_envelope,
        unexecuted_request_n=REMAINING_N - len(completed),
        ambiguous_dispatch_reserve_usd=frozen["cost"]["ambiguous_dispatch_reserve"]["usd"],
    )


def _write_manifest() -> None:
    paths = sorted(
        path
        for path in FULL_ROOT.rglob("*")
        if path.is_file() and path.name != "full_manifest.json"
    )


def _artifact_reference(path: Path) -> str:
    """Return repository path in production and full-root path under tests."""

    if path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return str(path.relative_to(FULL_ROOT))
    write_json(
        FULL_ROOT / "full_manifest.json",
        {
            "artifact_root": "runs/v2/phase7_generation_claude_top3_v2/full_v2",
            "artifacts": {
                str(path.relative_to(FULL_ROOT)): sha256_file(path) for path in paths
            },
            "schema_version": 2,
            "status": "phase7_v2_full_panel_checkpoint",
        },
        overwrite=(FULL_ROOT / "full_manifest.json").exists(),
    )


def run_full(
    frozen: dict[str, Any],
    *,
    sender: Callable[[dict[str, Any]], Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    """Dispatch exact 160 remainder once; trace requests never reach sender."""

    rows = frozen["remaining"]
    ledger_path = FULL_ROOT / "sealed/ledger.json"
    if ledger_path.exists():
        raise FullPanelContractError("full-panel ledger already exists; refusing rerun")
    ledger = _initial_ledger(rows, frozen["projected_initial_usd"])
    _save_ledger(ledger_path, ledger)
    completed: list[dict[str, Any]] = []
    response_ids = {row["response_id"] for row in frozen["trace_coverage"]}

    for row in rows:
        if ledger["attempted_request_n"] >= REMAINING_N:
            raise FullPanelContractError("160-request hard cap reached")
        projected = _projected(frozen, ledger, completed)
        if projected > HARD_COST_CAP_USD + 1e-12:
            ledger["failure_class"] = "cost_cap_breach"
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            _write_manifest()
            return 76
        blinded_id = row["blinded_request_id"]
        ledger["attempted_request_n"] += 1
        ledger["current_blinded_request_id"] = blinded_id
        ledger["status"] = "attempt_counted_before_dispatch"
        _save_ledger(ledger_path, ledger)
        started_at = now()
        started = time.monotonic()
        try:
            response = sender(row["request"])
        except Exception as exc:
            failure_class, status_code, ambiguous = trace_runner._provider_failure(exc)
            ledger["billing_ambiguity"] = ambiguous
            ledger["failure_class"] = failure_class
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                FULL_ROOT / f"sealed/failures/{blinded_id}.json",
                {
                    "billing_ambiguity": ambiguous,
                    "blinded_request_id": blinded_id,
                    "error_type": type(exc).__name__,
                    "failure_class": failure_class,
                    "http_status": status_code,
                    "provider_error_body_preserved": False,
                    "request_sha256": row["request_sha256"],
                    "schema_version": 2,
                },
            )
            _write_manifest()
            return 76
        ended_at = now()
        latency_seconds = time.monotonic() - started
        try:
            raw = trace_runner._response_mapping(response)
        except Phase7ExecutionFailure as exc:
            ledger["billing_ambiguity"] = True
            ledger["failure_class"] = exc.failure_class
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            _write_manifest()
            return 76
        raw_path = FULL_ROOT / f"blinded/raw_responses/{blinded_id}.json"
        write_json(raw_path, raw)
        usage = raw.get("usage")
        if isinstance(usage, Mapping):
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            if (
                not isinstance(input_tokens, bool)
                and isinstance(input_tokens, int)
                and input_tokens > 0
                and not isinstance(output_tokens, bool)
                and isinstance(output_tokens, int)
                and output_tokens > 0
            ):
                ledger["v2_full_input_tokens"] += input_tokens
                ledger["v2_full_output_tokens"] += output_tokens
                ledger["v2_full_observed_cost_usd"] = (
                    ledger["v2_full_input_tokens"] + 5 * ledger["v2_full_output_tokens"]
                ) / 1_000_000
        try:
            validated = validate_provider_response(
                raw,
                available_evidence_ids=row["available_evidence_ids"],
            )
            if validated["response_id"] in response_ids:
                raise Phase7ExecutionFailure("duplicate_response")
            response_ids.add(validated["response_id"])
        except Phase7ExecutionFailure as exc:
            if exc.failure_class == "missing_usage":
                ledger["billing_ambiguity"] = True
            ledger["failure_class"] = exc.failure_class
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                FULL_ROOT / f"sealed/failures/{blinded_id}.json",
                {
                    "billing_ambiguity": ledger["billing_ambiguity"],
                    "blinded_request_id": blinded_id,
                    "error_message": str(exc),
                    "failure_class": exc.failure_class,
                    "raw_response_path": _artifact_reference(raw_path),
                    "request_sha256": row["request_sha256"],
                    "schema_version": 2,
                    "usage_accounted_before_validation": True,
                },
            )
            _write_manifest()
            return 76
        response_hash = sha256_text(stable_json(raw))
        answer_path = FULL_ROOT / f"blinded/validated_answers/{blinded_id}.json"
        write_json(
            answer_path,
            {
                "answer": validated["answer"],
                "blinded_request_id": blinded_id,
                "response_id": validated["response_id"],
                "response_sha256": response_hash,
            },
        )
        completed.append(row)
        ledger["completed_blinded_request_ids"].append(blinded_id)
        ledger["current_blinded_request_id"] = None
        ledger["status"] = "running"
        ledger.setdefault("request_records", []).append(
            {
                "blinded_request_id": blinded_id,
                "ended_at": ended_at.isoformat(),
                "input_tokens": validated["usage"]["input_tokens"],
                "latency_seconds": latency_seconds,
                "logical_request_id": row["logical_request_id"],
                "output_tokens": validated["usage"]["output_tokens"],
                "request_sha256": row["request_sha256"],
                "response_id": validated["response_id"],
                "response_sha256": response_hash,
                "returned_model": validated["model"],
                "started_at": started_at.isoformat(),
            }
        )
        ledger["projected_cumulative_worst_case_usd"] = _projected(
            frozen, ledger, completed
        )
        if ledger["projected_cumulative_worst_case_usd"] > HARD_COST_CAP_USD + 1e-12:
            ledger["failure_class"] = "cost_cap_breach"
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            _write_manifest()
            return 76
        _save_ledger(ledger_path, ledger)

    if ledger["attempted_request_n"] != REMAINING_N or len(completed) != REMAINING_N:
        raise FullPanelContractError("full-panel remainder completed with wrong count")
    new_coverage = [
        {
            "blinded_request_id": record["blinded_request_id"],
            "dispatched_in_full_run": True,
            "logical_request_id": record["logical_request_id"],
            "raw_response_path": _artifact_reference(
                FULL_ROOT / f"blinded/raw_responses/{record['blinded_request_id']}.json"
            ),
            "request_sha256": record["request_sha256"],
            "response_id": record["response_id"],
            "response_sha256": record["response_sha256"],
            "source": "full_v2_new",
            "validated_answer_path": _artifact_reference(
                FULL_ROOT / f"blinded/validated_answers/{record['blinded_request_id']}.json"
            ),
        }
        for record in ledger["request_records"]
    ]
    coverage = frozen["trace_coverage"] + new_coverage
    if (
        len(coverage) != 170
        or len({row["blinded_request_id"] for row in coverage}) != 170
    ):
        raise FullPanelContractError("170-record coverage manifest differs")
    write_jsonl(
        FULL_ROOT / "sealed/coverage_manifest.jsonl",
        coverage,
        key="blinded_request_id",
    )
    latencies = [row["latency_seconds"] for row in ledger["request_records"]]
    cumulative_observed = (
        V1_SPENT_USD + TRACE_OBSERVED_COST_USD + ledger["v2_full_observed_cost_usd"]
    )
    ledger["cumulative_observed_phase7_cost_usd"] = cumulative_observed
    ledger["status"] = "complete"
    _save_ledger(ledger_path, ledger)
    write_json(
        FULL_ROOT / "operational_summary.json",
        {
            "cumulative_observed_phase7_cost_usd": cumulative_observed,
            "full_panel_coverage_n": 170,
            "hard_cap_usd": HARD_COST_CAP_USD,
            "latency_seconds_new_160": {
                "maximum": max(latencies),
                "mean": sum(latencies) / len(latencies),
                "minimum": min(latencies),
            },
            "model": MODEL,
            "new_attempted_request_n": REMAINING_N,
            "new_successful_request_n": REMAINING_N,
            "reused_trace_record_n": 10,
            "schema_version": 2,
            "status": "complete_pending_offline_evaluation_approval",
            "v1_spent_usd": V1_SPENT_USD,
            "v2_full_input_tokens": ledger["v2_full_input_tokens"],
            "v2_full_observed_cost_usd": ledger["v2_full_observed_cost_usd"],
            "v2_full_output_tokens": ledger["v2_full_output_tokens"],
            "v2_trace_observed_cost_usd": TRACE_OBSERVED_COST_USD,
        },
    )
    _write_manifest()
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=("full",), required=True)
    result.add_argument(
        "--acknowledge-paid-api-and-hard-cap",
        action="store_true",
        required=True,
        help="confirm exact remaining 160 requests and cumulative USD 3.00 cap",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.acknowledge_paid_api_and_hard_cap:
        print("refused: paid API acknowledgement missing", file=sys.stderr)
        return 78
    try:
        frozen = preflight()
        if FULL_ROOT.exists():
            raise FullPanelContractError("full-panel output exists; refusing rerun")
        with trace_runner.ExecutionLock(RUN_ROOT / ".full_v2_execution.lock"):
            sender = trace_runner.create_live_sender()
            return run_full(frozen, sender=sender)
    except (FullPanelContractError, trace_runner.TraceV2ContractError, Phase7ExecutionFailure) as exc:
        print(f"refused: {type(exc).__name__}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
