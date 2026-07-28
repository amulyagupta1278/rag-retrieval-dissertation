#!/usr/bin/env python3
"""Run exact owner-approved Phase 7 V2 ten-request Claude trace once."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Mapping

import anthropic

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.generation.phase7_freeze import Phase7ExecutionFailure  # noqa: E402
from src.generation.phase7_v2_freeze import (  # noqa: E402
    API_VERSION,
    HARD_COST_CAP_USD,
    MAX_OUTPUT_TOKENS,
    MODEL,
    RETRY_N,
    SDK_VERSION,
    TEMPERATURE,
    TIMEOUT_SECONDS,
    TRACE_N,
    V1_SPENT_USD,
    assert_v2_output_path,
    projected_cumulative_exposure_usd,
    request_sha256,
    validate_provider_response,
    validate_trace_reuse,
)
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file, sha256_text  # noqa: E402


RUN_ROOT = ROOT / "runs/v2/phase7_generation_claude_top3_v2"
V1_ROOT = ROOT / "runs/v2/phase7_generation_claude_top3"
TRACE_ROOT = RUN_ROOT / "trace_v2"
CONFIG_PATH = RUN_ROOT / "execution_config.json"
FREEZE_MANIFEST_PATH = RUN_ROOT / "freeze_manifest.json"
PAYLOAD_PATH = RUN_ROOT / "blinded/request_payloads.jsonl"
REQUEST_PLAN_PATH = RUN_ROOT / "sealed/request_plan.jsonl"
TRACE_PLAN_PATH = RUN_ROOT / "sealed/trace_plan.json"
COST_PLAN_PATH = RUN_ROOT / "cost_plan.json"
APPROVAL_PATH = ROOT / "audits/phase7_generation/v2/trace_execution_approval.json"
APPROVED_FREEZE_COMMIT = "ac09f538f6b818d7d3f332b775fb62e2024a00e6"
EXPECTED_APPROVAL = (
    "Approve Phase 7 V2 512-token 10-request recovery trace at commit "
    "ac09f538f6b818d7d3f332b775fb62e2024a00e6, using "
    "claude-haiku-4-5-20251001, frozen prompt, schema, top-3 contexts, and trace "
    "IDs, temperature 0, zero retries, no fallback or replacement, and separate "
    "V2 outputs, under owner-amended cumulative Phase 7 generation hard cap of "
    "$3.00, including $0.005847 V1 spend, $1.106295 V2 full-panel worst case, "
    "and $0.007295 ambiguous-dispatch reserve. Valid V2 trace records may be "
    "reused only for byte-identical frozen V2 panel requests and must not be "
    "billed twice. Full-panel execution remains prohibited pending V2 trace review."
)


class TraceV2ContractError(ValueError):
    """Raised before dispatch when V2 execution contract differs."""


class ExecutionLock:
    """Exclusive process lock; stale lock requires manual inspection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "ExecutionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise TraceV2ContractError("another Phase 7 V2 trace process holds lock") from None
        os.write(self.fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(self.fd)
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.path.unlink(missing_ok=True)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TraceV2ContractError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise TraceV2ContractError(f"JSON artifact must be object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TraceV2ContractError(f"cannot read JSONL artifact: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TraceV2ContractError(f"invalid JSONL row: {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise TraceV2ContractError(f"JSONL row must be object: {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise TraceV2ContractError(f"empty JSONL artifact: {path}")
    return rows


def _repo_path(relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise TraceV2ContractError("manifest path must be nonempty and relative")
    candidate = (ROOT / relative).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        raise TraceV2ContractError("manifest path escapes repository") from None
    if candidate != ROOT / relative:
        raise TraceV2ContractError("manifest path is not canonical")
    return candidate


def _verify_hash_map(values: Any, *, label: str) -> None:
    if not isinstance(values, dict) or not values:
        raise TraceV2ContractError(f"missing hash map: {label}")
    for relative, expected in values.items():
        path = _repo_path(relative)
        if not path.is_file() or sha256_file(path) != expected:
            raise TraceV2ContractError(f"frozen hash mismatch: {relative}")


def _verify_freeze() -> None:
    manifest = _json(FREEZE_MANIFEST_PATH)
    _verify_hash_map(manifest.get("artifacts"), label="V2 artifacts")
    _verify_hash_map(manifest.get("code"), label="V2 code")
    if (
        manifest.get("live_api_calls_n") != 0
        or manifest.get("max_output_tokens") != MAX_OUTPUT_TOKENS
        or manifest.get("hard_cap_pass") is not True
        or manifest.get("execution_authorized") is not False
    ):
        raise TraceV2ContractError("V2 freeze status differs")
    preservation = _json(ROOT / "audits/phase7_generation/v2/v1_preservation.json")
    _verify_hash_map(preservation.get("v1_artifact_hashes"), label="V1 preservation")


def _verify_approval() -> None:
    approval = _json(APPROVAL_PATH)
    if (
        approval.get("status") != "owner_approved"
        or approval.get("approved_freeze_commit") != APPROVED_FREEZE_COMMIT
        or approval.get("owner_statement") != EXPECTED_APPROVAL
        or approval.get("trace_request_n") != TRACE_N
        or approval.get("full_panel_authorized") is not False
        or approval.get("hard_cap_usd") != HARD_COST_CAP_USD
        or approval.get("model") != MODEL
        or approval.get("config_sha256") != sha256_file(CONFIG_PATH)
        or approval.get("freeze_manifest_sha256") != sha256_file(FREEZE_MANIFEST_PATH)
    ):
        raise TraceV2ContractError("owner V2 trace approval differs from freeze")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", APPROVED_FREEZE_COMMIT, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TraceV2ContractError("approved V2 freeze commit is not current history")


def preflight() -> dict[str, Any]:
    """Validate frozen V2 payloads and approval without credential or network use."""

    _verify_freeze()
    _verify_approval()
    config = _json(CONFIG_PATH)
    cost = _json(COST_PLAN_PATH)
    trace = _json(TRACE_PLAN_PATH)
    if (
        config.get("model") != MODEL
        or config.get("api", {}).get("api_version") != API_VERSION
        or config.get("api", {}).get("sdk_version") != SDK_VERSION
        or config.get("generation", {}).get("temperature") != TEMPERATURE
        or config.get("generation", {}).get("max_output_tokens") != MAX_OUTPUT_TOKENS
        or config.get("retry_n") != 0
        or RETRY_N != 0
        or config.get("trace_request_n") != TRACE_N
        or config.get("hard_cap_usd") != HARD_COST_CAP_USD
    ):
        raise TraceV2ContractError("V2 execution config differs")
    if (
        cost.get("current_hard_cap_usd") != HARD_COST_CAP_USD
        or cost.get("hard_cap_pass") is not True
        or cost.get("v1_spent_usd") != V1_SPENT_USD
        or cost.get("full_panel", {}).get("request_n") != 170
        or cost.get("trace", {}).get("request_n") != TRACE_N
    ):
        raise TraceV2ContractError("V2 cost plan differs")

    payload_rows = _jsonl(PAYLOAD_PATH)
    plan_rows = _jsonl(REQUEST_PLAN_PATH)
    payloads = {row.get("blinded_request_id"): row for row in payload_rows}
    plans = {row.get("blinded_request_id"): row for row in plan_rows}
    if len(payloads) != 170 or len(plans) != 170 or set(payloads) != set(plans):
        raise TraceV2ContractError("V2 frozen panel differs")
    selected = trace.get("selected")
    if not isinstance(selected, list) or len(selected) != TRACE_N:
        raise TraceV2ContractError("V2 trace must contain exact ten requests")
    rows: list[dict[str, Any]] = []
    for selection in selected:
        blinded_id = selection.get("blinded_request_id") if isinstance(selection, dict) else None
        payload = payloads.get(blinded_id)
        plan = plans.get(blinded_id)
        if payload is None or plan is None:
            raise TraceV2ContractError("V2 trace selection lacks frozen request")
        request = payload.get("request")
        if (
            selection.get("logical_request_id") != plan.get("logical_request_id")
            or payload.get("request_sha256") != plan.get("request_hash")
            or not isinstance(request, dict)
            or request.get("max_tokens") != MAX_OUTPUT_TOKENS
            or request_sha256(request) != payload.get("request_sha256")
        ):
            raise TraceV2ContractError("V2 trace request differs from panel")
        try:
            context = json.loads(request["messages"][0]["content"])
            available_ids = [item["evidence_id"] for item in context["evidence"]]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise TraceV2ContractError("V2 trace context is invalid") from exc
        if available_ids != list(plan.get("evidence_id_to_chunk_id", {})):
            raise TraceV2ContractError("V2 trace evidence mapping differs")
        rows.append(
            {
                "available_evidence_ids": available_ids,
                "blinded_request_id": blinded_id,
                "logical_request_id": plan["logical_request_id"],
                "planned_input_token_envelope": plan["planned_input_token_envelope"],
                "request": request,
                "request_sha256": payload["request_sha256"],
            }
        )
    if sum(row["planned_input_token_envelope"] for row in rows) != cost["trace"][
        "input_token_envelope"
    ]:
        raise TraceV2ContractError("V2 trace token envelope differs")
    if sum(row["planned_input_token_envelope"] for row in plan_rows) != cost[
        "full_panel"
    ]["input_token_envelope"]:
        raise TraceV2ContractError("V2 full-panel token envelope differs")
    assert_v2_output_path(TRACE_ROOT, v2_root=RUN_ROOT, v1_root=V1_ROOT)
    return {"cost": cost, "rows": rows}


def _response_mapping(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return copy.deepcopy(dict(response))
    if hasattr(response, "model_dump"):
        value = response.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(value, dict):
            return value
    raise Phase7ExecutionFailure("missing_response", "response is not serializable")


def _initial_ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "attempted_request_n": 0,
        "billing_ambiguity": False,
        "completed_blinded_request_ids": [],
        "full_panel_authorized": False,
        "hard_cap_usd": HARD_COST_CAP_USD,
        "planned_blinded_request_ids": [row["blinded_request_id"] for row in rows],
        "retry_n": 0,
        "schema_version": 2,
        "status": "ready",
        "trace_request_cap": TRACE_N,
        "v1_spent_usd": V1_SPENT_USD,
        "v2_input_tokens": 0,
        "v2_observed_cost_usd": 0.0,
        "v2_output_tokens": 0,
    }


def _save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_json(path, ledger, overwrite=path.exists())


def _projected(frozen: dict[str, Any], ledger: dict[str, Any], completed: list[dict[str, Any]]) -> float:
    completed_envelope = sum(row["planned_input_token_envelope"] for row in completed)
    remaining_input = frozen["cost"]["full_panel"]["input_token_envelope"] - completed_envelope
    remaining_n = frozen["cost"]["full_panel"]["request_n"] - len(completed)
    return projected_cumulative_exposure_usd(
        v2_observed_input_tokens=ledger["v2_input_tokens"],
        v2_observed_output_tokens=ledger["v2_output_tokens"],
        unexecuted_input_token_envelope=remaining_input,
        unexecuted_request_n=remaining_n,
        ambiguous_dispatch_reserve_usd=frozen["cost"]["ambiguous_dispatch_reserve"]["usd"],
    )


def _write_manifest() -> None:
    paths = sorted(
        path
        for path in TRACE_ROOT.rglob("*")
        if path.is_file() and path.name != "trace_manifest.json"
    )
    write_json(
        TRACE_ROOT / "trace_manifest.json",
        {
            "artifact_root": "runs/v2/phase7_generation_claude_top3_v2/trace_v2",
            "artifacts": {
                str(path.relative_to(TRACE_ROOT)): sha256_file(path) for path in paths
            },
            "schema_version": 2,
            "status": "phase7_v2_trace_checkpoint",
        },
        overwrite=(TRACE_ROOT / "trace_manifest.json").exists(),
    )


def _provider_failure(exc: Exception) -> tuple[str, int | None, bool]:
    if isinstance(exc, anthropic.APITimeoutError):
        return "timeout", 408, True
    if isinstance(exc, anthropic.APIConnectionError):
        return "ambiguous_dispatch", None, True
    if isinstance(exc, anthropic.APIStatusError):
        return "non_2xx_response", exc.status_code, False
    return "ambiguous_dispatch", None, True


def create_live_sender() -> Callable[[dict[str, Any]], Any]:
    """Create exact no-retry Claude client from environment only."""

    try:
        installed = metadata.version("anthropic")
    except metadata.PackageNotFoundError:
        raise TraceV2ContractError("required anthropic SDK is not installed") from None
    if installed != SDK_VERSION:
        raise TraceV2ContractError(
            f"anthropic version mismatch: expected {SDK_VERSION}, got {installed}"
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise Phase7ExecutionFailure("credential_unavailable")
    client = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=TIMEOUT_SECONDS)

    def send(request: dict[str, Any]) -> Any:
        return client.messages.create(**copy.deepcopy(request))

    return send


def run_trace(
    frozen: dict[str, Any],
    *,
    sender: Callable[[dict[str, Any]], Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    """Execute exact V2 trace once; stop on first terminal failure."""

    rows = frozen["rows"]
    ledger_path = TRACE_ROOT / "sealed/ledger.json"
    if ledger_path.exists():
        raise TraceV2ContractError("V2 trace ledger already exists; refusing rerun")
    ledger = _initial_ledger(rows)
    _save_ledger(ledger_path, ledger)
    completed: list[dict[str, Any]] = []
    response_ids: set[str] = set()
    reuse_rows: list[dict[str, Any]] = []

    for row in rows:
        if ledger["attempted_request_n"] >= TRACE_N:
            raise TraceV2ContractError("V2 trace request cap reached")
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
            failure_class, status_code, ambiguous = _provider_failure(exc)
            ledger["billing_ambiguity"] = ambiguous
            ledger["failure_class"] = failure_class
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                TRACE_ROOT / f"sealed/failures/{blinded_id}.json",
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
            raw_response = _response_mapping(response)
        except Phase7ExecutionFailure as exc:
            ledger["billing_ambiguity"] = True
            ledger["failure_class"] = exc.failure_class
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            _write_manifest()
            return 76

        raw_path = TRACE_ROOT / f"blinded/raw_responses/{blinded_id}.json"
        write_json(raw_path, raw_response)
        usage = raw_response.get("usage")
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
                ledger["v2_input_tokens"] += input_tokens
                ledger["v2_output_tokens"] += output_tokens
                ledger["v2_observed_cost_usd"] = (
                    ledger["v2_input_tokens"] + 5 * ledger["v2_output_tokens"]
                ) / 1_000_000
        try:
            validated = validate_provider_response(
                raw_response,
                available_evidence_ids=row["available_evidence_ids"],
            )
            if validated["response_id"] in response_ids:
                raise Phase7ExecutionFailure("duplicate_response")
            response_ids.add(validated["response_id"])
            reuse_hash = validate_trace_reuse(
                trace_request=row["request"],
                frozen_panel_request=row["request"],
                response_valid=True,
                already_has_panel_output=False,
            )
        except (Phase7ExecutionFailure, ValueError) as exc:
            failure_class = (
                exc.failure_class if isinstance(exc, Phase7ExecutionFailure) else "context_mismatch"
            )
            if failure_class == "missing_usage":
                ledger["billing_ambiguity"] = True
            ledger["failure_class"] = failure_class
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                TRACE_ROOT / f"sealed/failures/{blinded_id}.json",
                {
                    "billing_ambiguity": ledger["billing_ambiguity"],
                    "blinded_request_id": blinded_id,
                    "error_message": str(exc),
                    "failure_class": failure_class,
                    "raw_response_path": str(raw_path.relative_to(ROOT)),
                    "request_sha256": row["request_sha256"],
                    "schema_version": 2,
                    "usage_accounted_before_validation": True,
                },
            )
            _write_manifest()
            return 76

        response_hash = sha256_text(stable_json(raw_response))
        write_json(
            TRACE_ROOT / f"blinded/validated_answers/{blinded_id}.json",
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
        reuse_rows.append(
            {
                "blinded_request_id": blinded_id,
                "frozen_panel_request_sha256": reuse_hash,
                "reusable_in_v2_panel": True,
                "response_sha256": response_hash,
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

    if ledger["attempted_request_n"] != TRACE_N or len(completed) != TRACE_N:
        raise TraceV2ContractError("V2 trace completed with wrong count")
    write_jsonl(
        TRACE_ROOT / "sealed/reuse_manifest.jsonl",
        reuse_rows,
        key="blinded_request_id",
    )
    latencies = [row["latency_seconds"] for row in ledger["request_records"]]
    ledger["status"] = "complete"
    _save_ledger(ledger_path, ledger)
    write_json(
        TRACE_ROOT / "operational_summary.json",
        {
            "attempted_request_n": TRACE_N,
            "cumulative_observed_phase7_cost_usd": V1_SPENT_USD
            + ledger["v2_observed_cost_usd"],
            "full_panel_executed": False,
            "hard_cap_usd": HARD_COST_CAP_USD,
            "latency_seconds": {
                "maximum": max(latencies),
                "mean": sum(latencies) / len(latencies),
                "minimum": min(latencies),
            },
            "model": MODEL,
            "schema_version": 2,
            "status": "complete_pending_owner_trace_review",
            "successful_request_n": TRACE_N,
            "v1_spent_usd": V1_SPENT_USD,
            "v2_input_tokens": ledger["v2_input_tokens"],
            "v2_observed_cost_usd": ledger["v2_observed_cost_usd"],
            "v2_output_tokens": ledger["v2_output_tokens"],
        },
    )
    _write_manifest()
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=("trace",), required=True)
    result.add_argument(
        "--acknowledge-paid-api-and-hard-cap",
        action="store_true",
        required=True,
        help="confirm exact V2 ten-request paid trace and cumulative USD 3.00 cap",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.acknowledge_paid_api_and_hard_cap:
        print("refused: paid API acknowledgement missing", file=sys.stderr)
        return 78
    try:
        frozen = preflight()
        if TRACE_ROOT.exists():
            raise TraceV2ContractError("V2 trace output exists; refusing rerun")
        with ExecutionLock(RUN_ROOT / ".trace_v2_execution.lock"):
            sender = create_live_sender()
            return run_trace(frozen, sender=sender)
    except (TraceV2ContractError, Phase7ExecutionFailure) as exc:
        print(f"refused: {type(exc).__name__}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
