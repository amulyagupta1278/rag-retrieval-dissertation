#!/usr/bin/env python3
"""Execute only separately approved Phase 5D V3 transport recovery."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_phase5d_v2_full_prompt_rag_claude import (  # noqa: E402
    ExecutionLock,
    preflight as v2_full_preflight,
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


CONFIG_PATH = ROOT / "configs/prompt_rag_claude_v3_transport_recovery.json"
MANIFEST_PATH = ROOT / "audits/phase5d_v3_recovery/freeze_manifest.json"
APPROVAL_PATH = ROOT / "audits/phase5d_v3_recovery/live_execution_approval.json"
FAILURE_MANIFEST_PATH = ROOT / "audits/phase5d_v2_full/failure_manifest.json"
V2_FULL_ROOT = ROOT / "runs/v2/phase5d_prompt_rag_claude_v2/full"
OUTPUT_ROOT = ROOT / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full"

REQUEST_N = 26
RECORDED_PRIOR_SPEND_USD = 1.040028
AMBIGUOUS_INPUT_RESERVE_TOKENS = 40_000
AMBIGUOUS_MAX_OUTPUT_TOKENS = 2_048
AMBIGUOUS_RESERVE_USD = 0.050240
RESERVED_PRIOR_EXPOSURE_USD = 1.090268
RECOVERY_INPUT_BUDGET_TOKENS = 792_820
RECOVERY_MAX_OUTPUT_TOKENS = 53_248
RECOVERY_BUDGETED_WORST_CASE_USD = 1.059060
CUMULATIVE_BUDGETED_WORST_CASE_USD = 2.149328
CUMULATIVE_HARD_CAP_USD = 2.15


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
    manifest = _json(path)
    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ClaudeContractError(f"artifact hashes missing: {path.relative_to(ROOT)}")
    for relative, expected in hashes.items():
        artifact = _canonical(relative)
        if artifact == path or not artifact.is_file() or sha256_file(artifact) != expected:
            raise ClaudeContractError(f"artifact hash mismatch: {relative}")


def _verify_failed_v2() -> None:
    """Require terminal V2 evidence and reject any valid V2 full output."""

    _verify_hash_map(FAILURE_MANIFEST_PATH)
    failure_manifest = _json(FAILURE_MANIFEST_PATH)
    if (
        failure_manifest.get("status") != "terminal_failure_checkpoint_frozen"
        or failure_manifest.get("failure_run_resumable") is not False
        or failure_manifest.get("new_live_call_authorized") is not False
    ):
        raise ClaudeContractError("V2 terminal failure manifest status mismatch")
    ledger = _json(V2_FULL_ROOT / "control/ledger.json")
    if (
        ledger.get("status") != "failed"
        or ledger.get("attempted_generation_request_n") != 1
        or ledger.get("completed_logical_request_ids") != []
        or ledger.get("billing_ambiguous") is not True
    ):
        raise ClaudeContractError("V2 full failure ledger contract mismatch")
    raw_dir = V2_FULL_ROOT / "raw"
    if raw_dir.exists() and any(raw_dir.glob("*.json")):
        raise ClaudeContractError("V2 full run unexpectedly contains valid raw output")


def preflight() -> dict[str, Any]:
    """Verify V3 freeze, unchanged requests, and all prior evidence hashes."""

    _verify_hash_map(MANIFEST_PATH)
    config = _json(CONFIG_PATH)
    if config.get("failure_checkpoint", {}).get("manifest_sha256") != sha256_file(
        FAILURE_MANIFEST_PATH
    ):
        raise ClaudeContractError("V2 failure manifest hash mismatch")
    if config.get("frozen_contract", {}).get("model") != MODEL:
        raise ClaudeContractError("recovery model mismatch")
    budget = config.get("budget", {})
    expected = {
        "ambiguous_attempt_input_reserve_tokens": AMBIGUOUS_INPUT_RESERVE_TOKENS,
        "ambiguous_attempt_max_output_tokens": AMBIGUOUS_MAX_OUTPUT_TOKENS,
        "ambiguous_attempt_reserve_usd": AMBIGUOUS_RESERVE_USD,
        "cumulative_budgeted_worst_case_usd": CUMULATIVE_BUDGETED_WORST_CASE_USD,
        "cumulative_hard_cap_usd": CUMULATIVE_HARD_CAP_USD,
        "recorded_prior_cumulative_usd": RECORDED_PRIOR_SPEND_USD,
        "recovery_budgeted_input_tokens": RECOVERY_INPUT_BUDGET_TOKENS,
        "recovery_budgeted_worst_case_usd": RECOVERY_BUDGETED_WORST_CASE_USD,
        "reserved_prior_exposure_usd": RESERVED_PRIOR_EXPOSURE_USD,
    }
    for key, value in expected.items():
        if budget.get(key) != value:
            raise ClaudeContractError(f"recovery budget mismatch: {key}")
    if CUMULATIVE_BUDGETED_WORST_CASE_USD > CUMULATIVE_HARD_CAP_USD:
        raise ClaudeContractError("recovery budget exceeds proposed hard cap")
    frozen = v2_full_preflight()
    _verify_failed_v2()
    if len(frozen["full_plan"]) != REQUEST_N:
        raise ClaudeContractError("recovery scope must contain 26 primaries")
    frozen["recovery_config"] = config
    return frozen


def expected_approval_statement(recovery_commit: str) -> str:
    """Build exact owner statement bound to committed V3 freeze."""

    return (
        "Approve Phase 5D V3 26-primary transport recovery at commit "
        f"{recovery_commit}, with unchanged model, fixed-key schema, prompt, "
        "candidates, scoring, ranking, and no automatic retries; separate V3 "
        "outputs; cumulative hard cap $2.15, including $0.050240 ambiguous-attempt "
        "reserve and $2.149328 budgeted cumulative worst case."
    )


def _validate_approval() -> dict[str, Any]:
    approval = _json(APPROVAL_PATH)
    commit = approval.get("approved_recovery_commit")
    if approval.get("status") != "owner_approved" or not isinstance(commit, str):
        raise ClaudeContractError("V3 recovery lacks owner live approval")
    if approval.get("owner_statement") != expected_approval_statement(commit):
        raise ClaudeContractError("V3 owner approval statement mismatch")
    if approval.get("recovery_config_sha256") != sha256_file(CONFIG_PATH):
        raise ClaudeContractError("V3 owner approval config hash mismatch")
    if approval.get("freeze_manifest_sha256") != sha256_file(MANIFEST_PATH):
        raise ClaudeContractError("V3 owner approval manifest hash mismatch")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ClaudeContractError("approved V3 commit is not current history")
    return approval


def _initial_ledger(plan: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "actual_input_tokens": 0,
        "actual_output_tokens": 0,
        "ambiguous_prior_attempt_reserve_usd": AMBIGUOUS_RESERVE_USD,
        "attempted_generation_request_n": 0,
        "completed_logical_request_ids": [],
        "cumulative_budgeted_exposure_usd": RESERVED_PRIOR_EXPOSURE_USD,
        "cumulative_hard_cap_usd": CUMULATIVE_HARD_CAP_USD,
        "cumulative_recorded_observed_cost_usd": RECORDED_PRIOR_SPEND_USD,
        "planned_logical_request_ids": [logical_id for logical_id, _ in plan],
        "recorded_prior_spend_usd": RECORDED_PRIOR_SPEND_USD,
        "recovery_input_budget_tokens": RECOVERY_INPUT_BUDGET_TOKENS,
        "recovery_observed_cost_usd": 0.0,
        "reserved_prior_exposure_usd": RESERVED_PRIOR_EXPOSURE_USD,
        "schema_version": 1,
        "status": "ready",
    }


def _save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_json(path, ledger, overwrite=path.exists())


def projected_budgeted_exposure(ledger: dict[str, Any], remaining_n: int) -> float:
    """Project reserved prior exposure plus recovery input/output ceilings."""

    actual_input = int(ledger["actual_input_tokens"])
    remaining_input = max(0, RECOVERY_INPUT_BUDGET_TOKENS - actual_input)
    recovery_observed = observed_cost_usd(
        actual_input, int(ledger["actual_output_tokens"])
    )
    remaining_output = remaining_n * MAX_OUTPUT_TOKENS * 5.0 / 1_000_000
    return (
        RESERVED_PRIOR_EXPOSURE_USD
        + recovery_observed
        + remaining_input / 1_000_000
        + remaining_output
    )


def run_recovery(
    frozen: dict[str, Any],
    *,
    client_factory: Callable[[], Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    """Execute V3 once; zero automatic retries and no V2 output selection."""

    _validate_approval()
    plan = frozen["full_plan"]
    ledger_path = OUTPUT_ROOT / "control/ledger.json"
    ledger = _json(ledger_path) if ledger_path.exists() else _initial_ledger(plan)
    _save_ledger(ledger_path, ledger)
    if ledger.get("planned_logical_request_ids") != [row[0] for row in plan]:
        raise ClaudeContractError("V3 ledger plan mismatch")
    if ledger.get("status") in {"failed", "complete"}:
        raise ClaudeContractError(f"V3 ledger is terminal: {ledger['status']}")
    if ledger.get("status") == "attempt_counted_before_dispatch":
        raise ClaudeContractError("prior V3 dispatch ambiguous; refusing duplicate billing")
    if ledger.get("attempted_generation_request_n", 0) > REQUEST_N:
        raise ClaudeContractError("V3 hard request cap exceeded")

    client = client_factory()
    sender = make_live_sender(client)
    for logical_id, query_id in plan:
        if logical_id in ledger["completed_logical_request_ids"]:
            continue
        remaining_n = len(plan) - len(ledger["completed_logical_request_ids"])
        projected = projected_budgeted_exposure(ledger, remaining_n)
        if projected > CUMULATIVE_HARD_CAP_USD:
            raise ClaudeContractError(
                f"V3 projected exposure ${projected:.6f} exceeds hard cap"
            )
        if ledger["attempted_generation_request_n"] >= REQUEST_N:
            raise ClaudeContractError("V3 hard request cap reached")
        request = frozen["requests"][query_id]
        request_hash = request_sha256(request)
        safe_name = logical_id.replace(":", "__")
        raw_path = OUTPUT_ROOT / "raw" / f"{safe_name}.json"
        if raw_path.exists():
            raise ClaudeContractError("V3 response exists outside ledger")

        ledger["attempted_generation_request_n"] += 1
        ledger["status"] = "attempt_counted_before_dispatch"
        _save_ledger(ledger_path, ledger)
        started_at = now()
        started_monotonic = time.monotonic()
        try:
            response = sender(request)
        except ClaudeProviderError as exc:
            ledger["status"] = "failed"
            ledger["additional_billing_ambiguous"] = True
            _save_ledger(ledger_path, ledger)
            write_json(
                OUTPUT_ROOT / "failures" / f"{safe_name}.json",
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
            ledger["additional_billing_ambiguous"] = True
            _save_ledger(ledger_path, ledger)
            write_json(
                OUTPUT_ROOT / "failures" / f"{safe_name}.json",
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
        ledger["recovery_observed_cost_usd"] = observed_cost_usd(
            ledger["actual_input_tokens"], ledger["actual_output_tokens"]
        )
        ledger["cumulative_recorded_observed_cost_usd"] = (
            RECORDED_PRIOR_SPEND_USD + ledger["recovery_observed_cost_usd"]
        )
        ledger["cumulative_budgeted_exposure_usd"] = (
            RESERVED_PRIOR_EXPOSURE_USD + ledger["recovery_observed_cost_usd"]
        )
        if ledger["actual_input_tokens"] > RECOVERY_INPUT_BUDGET_TOKENS:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            raise ClaudeContractError("V3 observed input exceeded token budget")
        if ledger["cumulative_budgeted_exposure_usd"] > CUMULATIVE_HARD_CAP_USD:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            raise ClaudeContractError("V3 budgeted exposure exceeded hard cap")
        try:
            validated = validate_response(
                raw_response, expected_chunk_ids=frozen["rankings"][query_id]
            )
        except ClaudeContractError as exc:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                OUTPUT_ROOT / "failures" / f"{safe_name}.json",
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
    result.add_argument("--mode", choices=("recovery",), required=True)
    result.add_argument(
        "--acknowledge-paid-api-and-hard-cap",
        action="store_true",
        required=True,
        help="confirm paid API and cumulative USD 2.15 hard cap",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.acknowledge_paid_api_and_hard_cap:
        print("refused: paid API acknowledgement missing", file=sys.stderr)
        return 78
    try:
        frozen = preflight()
        with ExecutionLock(OUTPUT_ROOT / "control/execution.lock"):
            return run_recovery(frozen, client_factory=create_client_from_environment)
    except (ClaudeContractError, ClaudeProviderError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
