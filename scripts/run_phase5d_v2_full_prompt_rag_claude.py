#!/usr/bin/env python3
"""Execute only owner-approved Phase 5D V2 remaining 26 primaries."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_phase5d_v2_prompt_rag_claude import (  # noqa: E402
    OUTPUT_ROOT,
    ExecutionLock,
    preflight as base_preflight,
)
from src.retrievers.prompt_rag_claude_v2 import (  # noqa: E402
    MAX_OUTPUT_TOKENS,
    MODEL,
    ClaudeContractError,
    ClaudeProviderError,
    create_client_from_environment,
    extract_usage,
    make_live_sender,
    observed_cost_usd,
    request_sha256,
    response_mapping,
    validate_response,
)
from src.utils.atomic_io import stable_json, write_json  # noqa: E402
from src.utils.hashing import sha256_file, sha256_text  # noqa: E402


AMENDMENT_CONFIG_PATH = ROOT / "configs/prompt_rag_claude_v2_full_amendment.json"
AMENDMENT_MANIFEST_PATH = ROOT / "audits/phase5d_v2_full/freeze_manifest.json"
APPROVAL_PATH = ROOT / "audits/phase5d_v2_full/full_execution_approval.json"
TRACE_MANIFEST_PATH = OUTPUT_ROOT / "trace/artifact_manifest.json"
TRACE_LEDGER_PATH = OUTPUT_ROOT / "trace/control/ledger.json"
TRACE_DECISION_PATH = OUTPUT_ROOT / "trace/repeatability_decision.json"
FULL_ROOT = OUTPUT_ROOT / "full"

FULL_REQUEST_N = 26
PRIOR_CUMULATIVE_SPEND_USD = 1.040028
FULL_COUNTED_INPUT_TOKENS = 771_768
OBSERVED_CORRECTION_TOKENS = 52
FULL_CORRECTED_INPUT_TOKENS = 771_820
INPUT_UNCERTAINTY_RESERVE_TOKENS = 21_000
FULL_BUDGETED_INPUT_TOKENS = 792_820
FULL_MAXIMUM_OUTPUT_TOKENS = 53_248
FULL_CORRECTED_WORST_CASE_USD = 1.038060
FULL_BUDGETED_WORST_CASE_USD = 1.059060
CUMULATIVE_BUDGETED_WORST_CASE_USD = 2.099088
CUMULATIVE_HARD_CAP_USD = 2.10


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaudeContractError(f"invalid JSON artifact: {path.relative_to(ROOT)}") from exc
    if not isinstance(value, dict):
        raise ClaudeContractError(f"JSON artifact must be object: {path.relative_to(ROOT)}")
    return value


def _canonical(relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ClaudeContractError("manifest path must be non-empty and relative")
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        raise ClaudeContractError("manifest path escapes repository") from None
    if path != ROOT / relative:
        raise ClaudeContractError("manifest path is not canonical")
    return path


def _verify_hash_map(path: Path) -> None:
    hashes = _json(path).get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ClaudeContractError(f"artifact hashes missing: {path.relative_to(ROOT)}")
    for relative, expected in hashes.items():
        artifact = _canonical(relative)
        if artifact == path or not artifact.is_file() or sha256_file(artifact) != expected:
            raise ClaudeContractError(f"artifact hash mismatch: {relative}")


def build_full_plan(query_ids: list[str], trace_ids: list[str]) -> list[tuple[str, str]]:
    """Return ordered non-trace primary scope exactly once."""

    if len(query_ids) != 34 or len(set(query_ids)) != 34:
        raise ClaudeContractError("full plan requires 34 unique ordered query IDs")
    if len(trace_ids) != 8 or len(set(trace_ids)) != 8:
        raise ClaudeContractError("full plan requires eight unique trace IDs")
    if not set(trace_ids).issubset(query_ids):
        raise ClaudeContractError("trace IDs are not subset of query IDs")
    plan = [
        (f"{query_id}:primary", query_id)
        for query_id in query_ids
        if query_id not in set(trace_ids)
    ]
    if len(plan) != FULL_REQUEST_N:
        raise ClaudeContractError("remaining-primary plan must contain 26 requests")
    return plan


def _verify_trace_checkpoint() -> None:
    """Require complete passed trace while preserving every trace byte."""

    _verify_hash_map(TRACE_MANIFEST_PATH)
    ledger = _json(TRACE_LEDGER_PATH)
    if (
        ledger.get("status") != "complete"
        or ledger.get("attempted_generation_request_n") != 24
        or len(ledger.get("completed_logical_request_ids", [])) != 24
        or ledger.get("cumulative_observed_cost_usd") != PRIOR_CUMULATIVE_SPEND_USD
    ):
        raise ClaudeContractError("trace ledger is not exact complete checkpoint")
    decision = _json(TRACE_DECISION_PATH)
    if (
        decision.get("status") != "repeatability_gate_passed"
        or decision.get("trace_record_n") != 24
        or decision.get("relevance_metrics_calculated") is not False
    ):
        raise ClaudeContractError("trace repeatability gate is not passed")


def preflight() -> dict[str, Any]:
    """Verify additive amendment, base requests, and immutable trace evidence."""

    _verify_hash_map(AMENDMENT_MANIFEST_PATH)
    config = _json(AMENDMENT_CONFIG_PATH)
    if config.get("base_config_sha256") != sha256_file(
        ROOT / config["base_config_path"]
    ):
        raise ClaudeContractError("base V2 config hash mismatch")
    if config.get("trace_artifact_manifest_sha256") != sha256_file(
        TRACE_MANIFEST_PATH
    ):
        raise ClaudeContractError("trace artifact manifest hash mismatch")
    budget = config.get("budget", {})
    expected_budget = {
        "corrected_counted_input_tokens": FULL_CORRECTED_INPUT_TOKENS,
        "counted_input_tokens_before_observed_correction": FULL_COUNTED_INPUT_TOKENS,
        "cumulative_budgeted_worst_case_usd": CUMULATIVE_BUDGETED_WORST_CASE_USD,
        "cumulative_hard_cap_usd": CUMULATIVE_HARD_CAP_USD,
        "input_token_uncertainty_reserve": INPUT_UNCERTAINTY_RESERVE_TOKENS,
        "maximum_output_tokens_total": FULL_MAXIMUM_OUTPUT_TOKENS,
        "prior_cumulative_observed_spend_usd": PRIOR_CUMULATIVE_SPEND_USD,
        "remaining_run_budgeted_input_ceiling": FULL_BUDGETED_INPUT_TOKENS,
    }
    for key, expected in expected_budget.items():
        if budget.get(key) != expected:
            raise ClaudeContractError(f"budget contract mismatch: {key}")
    if CUMULATIVE_BUDGETED_WORST_CASE_USD > CUMULATIVE_HARD_CAP_USD:
        raise ClaudeContractError("budgeted worst case exceeds raised cap")
    frozen = base_preflight()
    if frozen["config"].get("model") != MODEL:
        raise ClaudeContractError("base model changed")
    _verify_trace_checkpoint()
    frozen["full_config"] = config
    frozen["full_plan"] = build_full_plan(frozen["query_ids"], frozen["trace_ids"])
    return frozen


def expected_approval_statement(amendment_commit: str) -> str:
    """Build exact owner statement bound to committed full-run amendment."""

    return (
        "Approve Phase 5D V2 remaining 26-primary full run at commit "
        f"{amendment_commit}, with unchanged model, fixed-key schema, prompt, "
        "candidates, scoring, ranking, and no retries; cumulative hard cap $2.10, "
        "$1.040028 spent, budgeted cumulative worst case $2.099088."
    )


def _validate_approval() -> dict[str, Any]:
    approval = _json(APPROVAL_PATH)
    commit = approval.get("approved_amendment_commit")
    if approval.get("status") != "owner_approved" or not isinstance(commit, str):
        raise ClaudeContractError("remaining-primary run lacks owner approval")
    if approval.get("owner_statement") != expected_approval_statement(commit):
        raise ClaudeContractError("full-run owner approval statement mismatch")
    if approval.get("amendment_config_sha256") != sha256_file(AMENDMENT_CONFIG_PATH):
        raise ClaudeContractError("owner approval amendment hash mismatch")
    if approval.get("freeze_manifest_sha256") != sha256_file(AMENDMENT_MANIFEST_PATH):
        raise ClaudeContractError("owner approval manifest hash mismatch")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ClaudeContractError("approved amendment commit is not current history")
    return approval


def _initial_ledger(plan: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "actual_input_tokens": 0,
        "actual_output_tokens": 0,
        "attempted_generation_request_n": 0,
        "completed_logical_request_ids": [],
        "cumulative_hard_cap_usd": CUMULATIVE_HARD_CAP_USD,
        "cumulative_observed_cost_usd": PRIOR_CUMULATIVE_SPEND_USD,
        "full_observed_cost_usd": 0.0,
        "input_budget_tokens": FULL_BUDGETED_INPUT_TOKENS,
        "planned_logical_request_ids": [logical_id for logical_id, _ in plan],
        "prior_cumulative_observed_cost_usd": PRIOR_CUMULATIVE_SPEND_USD,
        "schema_version": 1,
        "status": "ready",
    }


def _save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_json(path, ledger, overwrite=path.exists())


def projected_cumulative_cost(ledger: dict[str, Any], remaining_n: int) -> float:
    """Project observed usage plus reserved remaining input and maximum output."""

    actual_input = int(ledger["actual_input_tokens"])
    remaining_input_budget = max(0, FULL_BUDGETED_INPUT_TOKENS - actual_input)
    full_observed = observed_cost_usd(
        actual_input, int(ledger["actual_output_tokens"])
    )
    remaining_output_usd = (
        remaining_n * MAX_OUTPUT_TOKENS * 5.0 / 1_000_000
    )
    return (
        PRIOR_CUMULATIVE_SPEND_USD
        + full_observed
        + remaining_input_budget / 1_000_000
        + remaining_output_usd
    )


def run_full(
    frozen: dict[str, Any],
    *,
    client_factory: Callable[[], Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    """Execute exact remaining primaries once with no retry or trace mutation."""

    _validate_approval()
    plan = frozen["full_plan"]
    ledger_path = FULL_ROOT / "control/ledger.json"
    ledger = _json(ledger_path) if ledger_path.exists() else _initial_ledger(plan)
    _save_ledger(ledger_path, ledger)
    if ledger.get("planned_logical_request_ids") != [row[0] for row in plan]:
        raise ClaudeContractError("full-run ledger plan mismatch")
    if ledger.get("status") in {"failed", "complete"}:
        raise ClaudeContractError(f"full-run ledger is terminal: {ledger['status']}")
    if ledger.get("status") == "attempt_counted_before_dispatch":
        raise ClaudeContractError("prior dispatch outcome ambiguous; refusing duplicate billing")
    if ledger.get("attempted_generation_request_n", 0) > FULL_REQUEST_N:
        raise ClaudeContractError("full-run hard request cap exceeded")

    client = client_factory()
    sender = make_live_sender(client)
    for logical_id, query_id in plan:
        if logical_id in ledger["completed_logical_request_ids"]:
            continue
        remaining_n = len(plan) - len(ledger["completed_logical_request_ids"])
        projected = projected_cumulative_cost(ledger, remaining_n)
        if projected > CUMULATIVE_HARD_CAP_USD:
            raise ClaudeContractError(
                f"cumulative projection ${projected:.6f} exceeds raised cap"
            )
        if ledger["attempted_generation_request_n"] >= FULL_REQUEST_N:
            raise ClaudeContractError("full-run hard request cap reached")
        request = frozen["requests"][query_id]
        request_hash = request_sha256(request)
        safe_name = logical_id.replace(":", "__")
        raw_path = FULL_ROOT / "raw" / f"{safe_name}.json"
        if raw_path.exists():
            raise ClaudeContractError("full response exists outside ledger")

        ledger["attempted_generation_request_n"] += 1
        ledger["status"] = "attempt_counted_before_dispatch"
        _save_ledger(ledger_path, ledger)
        started_at = now()
        started_monotonic = time.monotonic()
        try:
            response = sender(request)
        except ClaudeProviderError as exc:
            ledger["status"] = "failed"
            ledger["billing_ambiguous"] = True
            _save_ledger(ledger_path, ledger)
            write_json(
                FULL_ROOT / "failures" / f"{safe_name}.json",
                {
                    "error_class": type(exc).__name__,
                    "http_status": exc.status_code,
                    "logical_request_id": logical_id,
                    "provider_error_body_preserved": False,
                    "request_sha256": request_hash,
                    "schema_version": 1,
                },
                overwrite=False,
            )
            return 76
        ended_at = now()
        latency_ms = (time.monotonic() - started_monotonic) * 1000
        try:
            raw_response = response_mapping(response)
            usage = extract_usage(raw_response)
        except ClaudeContractError as exc:
            ledger["status"] = "failed"
            ledger["billing_ambiguous"] = True
            _save_ledger(ledger_path, ledger)
            write_json(
                FULL_ROOT / "failures" / f"{safe_name}.json",
                {
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                    "logical_request_id": logical_id,
                    "request_sha256": request_hash,
                    "schema_version": 1,
                },
                overwrite=False,
            )
            return 76

        ledger["actual_input_tokens"] += usage["input_tokens"]
        ledger["actual_output_tokens"] += usage["output_tokens"]
        ledger["full_observed_cost_usd"] = observed_cost_usd(
            ledger["actual_input_tokens"], ledger["actual_output_tokens"]
        )
        ledger["cumulative_observed_cost_usd"] = (
            PRIOR_CUMULATIVE_SPEND_USD + ledger["full_observed_cost_usd"]
        )
        if ledger["actual_input_tokens"] > FULL_BUDGETED_INPUT_TOKENS:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            raise ClaudeContractError("observed input exceeded reserved token budget")
        if ledger["cumulative_observed_cost_usd"] > CUMULATIVE_HARD_CAP_USD:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            raise ClaudeContractError("observed cumulative cost exceeded raised cap")
        try:
            validated = validate_response(
                raw_response, expected_chunk_ids=frozen["rankings"][query_id]
            )
        except ClaudeContractError as exc:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                FULL_ROOT / "failures" / f"{safe_name}.json",
                {
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                    "invalid_raw_response": raw_response,
                    "logical_request_id": logical_id,
                    "request_sha256": request_hash,
                    "schema_version": 1,
                    "usage_accounted_before_validation": usage,
                },
                overwrite=False,
            )
            return 76

        ledger["completed_logical_request_ids"].append(logical_id)
        write_json(
            raw_path,
            {
                "ended_at": ended_at.isoformat(),
                "latency_ms": latency_ms,
                "logical_request_id": logical_id,
                "model": validated["model"],
                "ranking": validated["ranking"],
                "raw_request": request,
                "raw_response": validated["raw_response"],
                "request_sha256": request_hash,
                "response_id": validated["response_id"],
                "response_sha256": sha256_text(stable_json(validated["raw_response"])),
                "schema_version": 1,
                "started_at": started_at.isoformat(),
                "usage": usage,
            },
            overwrite=False,
        )
        ledger["status"] = "running"
        _save_ledger(ledger_path, ledger)

    ledger["status"] = "complete"
    _save_ledger(ledger_path, ledger)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=("full",), required=True)
    result.add_argument(
        "--acknowledge-paid-api-and-hard-cap",
        action="store_true",
        required=True,
        help="confirm paid API and cumulative USD 2.10 hard cap",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.acknowledge_paid_api_and_hard_cap:
        print("refused: paid API acknowledgement missing", file=sys.stderr)
        return 78
    try:
        frozen = preflight()
        with ExecutionLock(FULL_ROOT / "control/execution.lock"):
            return run_full(frozen, client_factory=create_client_from_environment)
    except (ClaudeContractError, ClaudeProviderError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
