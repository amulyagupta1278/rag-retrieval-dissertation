#!/usr/bin/env python3
"""Validate Phase 5C trace records and emit repeatability-only checkpoint artifacts."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_phase5b_prompt_rag import (  # noqa: E402
    CONFIG_PATH,
    EXPECTED_QUERY_IDS,
    FREE_TIER_CONFIRMATION_PATH,
    OUTPUT_ROOT,
    TRACE_APPROVAL_PATH,
    build_logical_plan,
)
from src.retrievers.prompt_rag_gemini_v1 import (  # noqa: E402
    NetworkAttemptCapError,
    NetworkAttemptLedger,
    PromptRAGContractError,
    recompute_trace_decision,
    require_free_tier_owner_confirmation,
    require_mode_execution_approval,
    stable_json,
)
from src.utils.atomic_io import write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


TRACE_ROOT = OUTPUT_ROOT / "trace"
RAW_ROOT = TRACE_ROOT / "raw"
LEDGER_PATH = TRACE_ROOT / "control/ledger.json"
DECISION_PATH = TRACE_ROOT / "repeatability_decision.json"
REPEATABILITY_SUMMARY_PATH = TRACE_ROOT / "repeatability_summary.json"
OPERATIONAL_SUMMARY_PATH = TRACE_ROOT / "operational_summary.json"
CHECKPOINT_PATH = TRACE_ROOT / "phase5c_checkpoint.json"
ARTIFACT_MANIFEST_PATH = TRACE_ROOT / "artifact_manifest.json"
TRACE_SELECTION_PATH = ROOT / "audits/phase5b/trace_selection.json"
REPEATABILITY_PROTOCOL_PATH = ROOT / "audits/phase5b/repeatability_protocol.json"
TOKEN_AUDIT_PATH = ROOT / "audits/phase5b/token_budget_audit.json"
PROMPT_PATH = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
TRACE_PLAN_PATH = ROOT / "audits/phase5c/trace_plan.json"
FREEZE_MANIFEST_PATH = ROOT / "audits/phase5c/freeze_manifest.json"
TRACE_LOGICAL_N = 24
TRACE_QUERY_N = 8


def _json(path: Path) -> dict[str, Any]:
    """Read one JSON object with actionable failure text."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromptRAGContractError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise PromptRAGContractError(f"JSON artifact must be object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    """Read non-empty JSONL objects."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PromptRAGContractError(f"cannot read JSONL artifact: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PromptRAGContractError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise PromptRAGContractError(f"JSONL row must be object at {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise PromptRAGContractError(f"JSONL artifact is empty: {path}")
    return rows


def _verify_freeze_manifest() -> dict[str, Any]:
    """Verify every immutable Phase 5C input before reading trace results."""

    manifest = _json(FREEZE_MANIFEST_PATH)
    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, dict) or len(hashes) != 14:
        raise PromptRAGContractError("Phase 5C freeze manifest is incomplete")
    if str(FREEZE_MANIFEST_PATH.relative_to(ROOT)) in hashes:
        raise PromptRAGContractError("Phase 5C freeze manifest must not hash itself")
    for relative, expected in hashes.items():
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise PromptRAGContractError("Phase 5C manifest path is not relative")
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            raise PromptRAGContractError("Phase 5C manifest path escapes repository") from None
        if path != ROOT / relative or not path.is_file() or sha256_file(path) != expected:
            raise PromptRAGContractError(f"Phase 5C freeze hash mismatch: {relative}")
    if manifest.get("mutable_runtime_controls_excluded") != [
        "audits/phase5b/free_tier_owner_confirmation.json",
        "audits/phase5b/trace_execution_approval.json",
    ]:
        raise PromptRAGContractError("Phase 5C mutable runtime controls are invalid")
    return manifest


def _logical_filename(logical_id: str) -> str:
    """Map one frozen logical request ID to canonical raw filename."""

    query_id, separator, role = logical_id.partition(":")
    if (
        separator != ":"
        or query_id not in EXPECTED_QUERY_IDS
        or role not in {"primary", "replicate-1", "replicate-2"}
    ):
        raise PromptRAGContractError("trace logical request ID is malformed")
    return f"{query_id}__{role}.json"


def _thresholds(protocol: Mapping[str, Any]) -> dict[str, float]:
    """Extract exact preregistered repeatability thresholds."""

    comparisons = protocol.get("comparisons")
    if not isinstance(comparisons, dict):
        raise PromptRAGContractError("repeatability protocol comparisons are invalid")
    result: dict[str, float] = {}
    for name, value in comparisons.items():
        if not isinstance(value, dict) or isinstance(value.get("minimum"), bool):
            raise PromptRAGContractError("repeatability threshold is invalid")
        minimum = value.get("minimum")
        if not isinstance(minimum, (int, float)) or not math.isfinite(float(minimum)):
            raise PromptRAGContractError("repeatability threshold is invalid")
        result[str(name)] = float(minimum)
    return result


def _percentile(values: Iterable[float], probability: float) -> float:
    """Return deterministic linearly interpolated percentile."""

    ordered = sorted(float(value) for value in values)
    if not ordered or not 0 <= probability <= 1 or any(not math.isfinite(v) for v in ordered):
        raise PromptRAGContractError("latency percentile input is invalid")
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _duration_ms(attempt: Mapping[str, Any]) -> float:
    """Calculate one network-attempt duration from preserved UTC timestamps."""

    started_at = attempt.get("started_at")
    ended_at = attempt.get("ended_at")
    if not isinstance(started_at, str) or not isinstance(ended_at, str):
        raise PromptRAGContractError("trace attempt lacks timestamps")
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
    except ValueError as exc:
        raise PromptRAGContractError("trace attempt timestamp is malformed") from exc
    if start.tzinfo is None or end.tzinfo is None or end < start:
        raise PromptRAGContractError("trace attempt timestamp order is invalid")
    return (end - start).total_seconds() * 1000


def _usage(raw_response: Mapping[str, Any]) -> dict[str, int]:
    """Normalize required provider usage metadata without estimating missing totals."""

    usage = raw_response.get("usageMetadata", raw_response.get("usage_metadata"))
    if not isinstance(usage, Mapping):
        raise PromptRAGContractError("trace response lacks provider usage metadata")
    aliases = {
        "input_tokens": ("promptTokenCount", "prompt_token_count"),
        "output_tokens": ("candidatesTokenCount", "candidates_token_count"),
        "thinking_tokens": ("thoughtsTokenCount", "thoughts_token_count"),
        "total_tokens": ("totalTokenCount", "total_token_count"),
        "cached_input_tokens": ("cachedContentTokenCount", "cached_content_token_count"),
    }
    normalized: dict[str, int] = {}
    for name, field_names in aliases.items():
        value: Any = None
        for field_name in field_names:
            if field_name in usage:
                value = usage[field_name]
                break
        if value is None and name in {"thinking_tokens", "cached_input_tokens"}:
            value = 0
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PromptRAGContractError(f"provider usage field is missing or invalid: {name}")
        normalized[name] = value
    return normalized


def _write_exact(path: Path, payload: Mapping[str, Any]) -> None:
    """Write once, allowing idempotent recovery only for byte-equivalent JSON."""

    expected = json.loads(stable_json(dict(payload)))
    if path.exists():
        if _json(path) != expected:
            raise PromptRAGContractError(f"output collision with different content: {path}")
        return
    write_json(path, expected, overwrite=False)


def _load_trace_records(plan: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Load exactly one canonical raw record for each frozen trace call."""

    expected = {RAW_ROOT / _logical_filename(logical_id) for logical_id, _ in plan}
    if not RAW_ROOT.is_dir():
        raise PromptRAGContractError("Phase 5C raw trace directory is missing")
    actual = set(RAW_ROOT.glob("*.json"))
    if actual != expected:
        raise PromptRAGContractError("raw trace directory contains missing or extra JSON records")
    return [_json(RAW_ROOT / _logical_filename(logical_id)) for logical_id, _ in plan]


def _validate_ledger(
    *,
    config: Mapping[str, Any],
    query_ids: list[str],
    plan: list[tuple[str, str]],
    request_hashes: Mapping[str, str],
    records: Iterable[Mapping[str, Any]],
) -> NetworkAttemptLedger:
    """Reopen strict durable ledger and require complete zero-charge trace scope."""

    if not LEDGER_PATH.is_file():
        raise NetworkAttemptCapError("Phase 5C durable ledger is missing")
    logical_hashes = {
        logical_id: request_hashes[query_id] for logical_id, query_id in plan
    }
    ledger = NetworkAttemptLedger(
        LEDGER_PATH,
        mode="trace",
        frozen_config_sha256=sha256_file(CONFIG_PATH),
        prompt_sha256=sha256_file(PROMPT_PATH),
        plan_sha256=config["request_contract"]["trace_plan_sha256"],
        query_ids=query_ids,
        expected_logical_request_ids=[logical_id for logical_id, _ in plan],
        expected_request_hashes=logical_hashes,
        model=config["generation"]["model"],
        output_root="runs/v2/phase5b_prompt_rag/trace",
    )
    expected_logical = sorted(logical_hashes)
    state = ledger.state
    if (
        state.get("status") != "trace_network_scope_complete"
        or state.get("attempted_network_request_n") != TRACE_LOGICAL_N
        or state.get("network_attempt_cap") != TRACE_LOGICAL_N
        or state.get("completed_logical_request_ids") != expected_logical
        or state.get("quota_stop") is not None
        or state.get("monetary_cost_usd") != 0.0
    ):
        raise NetworkAttemptCapError("trace ledger is not complete zero-charge scope")
    by_logical = {str(record.get("logical_request_id")): record for record in records}
    for logical_id in expected_logical:
        ledger_row = state["requests"][logical_id]
        record = by_logical.get(logical_id)
        if (
            ledger_row.get("state") != "committed"
            or len(ledger_row.get("attempts", [])) != 1
            or not isinstance(record, Mapping)
            or record.get("attempts") != ledger_row["attempts"]
        ):
            raise NetworkAttemptCapError("trace record and durable ledger differ")
    return ledger


def _execution_authorization(config: Mapping[str, Any]) -> dict[str, Any]:
    """Revalidate and summarize exact owner controls used for trace execution."""

    confirmation = require_free_tier_owner_confirmation(
        FREE_TIER_CONFIRMATION_PATH, frozen_config_path=CONFIG_PATH
    )
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        git_tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise PromptRAGContractError("cannot resolve Phase 5C Git identity") from exc
    approval = require_mode_execution_approval(
        TRACE_APPROVAL_PATH,
        mode="trace",
        frozen_config_sha256=sha256_file(CONFIG_PATH),
        prompt_sha256=sha256_file(PROMPT_PATH),
        plan_sha256=config["request_contract"]["trace_plan_sha256"],
        free_tier_confirmation_sha256=sha256_file(FREE_TIER_CONFIRMATION_PATH),
        git_commit=git_commit,
        git_tree=git_tree,
        trace_decision_sha256=None,
    )
    return {
        "free_tier_confirmation_sha256": sha256_file(FREE_TIER_CONFIRMATION_PATH),
        "free_tier_confirmed_at": confirmation["confirmed_at"],
        "git_commit": git_commit,
        "git_tree": git_tree,
        "trace_approval_sha256": sha256_file(TRACE_APPROVAL_PATH),
        "trace_approved_at": approval["approved_at"],
    }


def _repeatability_summary(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate pairwise repeatability values without relevance evaluation."""

    comparisons = decision.get("comparisons")
    thresholds = decision.get("thresholds")
    if not isinstance(comparisons, list) or not comparisons or not isinstance(thresholds, dict):
        raise PromptRAGContractError("trace repeatability decision is malformed")
    names = sorted(thresholds)
    aggregates: dict[str, dict[str, Any]] = {}
    for name in names:
        values = [float(row["metrics"][name]) for row in comparisons]
        aggregates[name] = {
            "all_pairwise_passed": all(value >= float(thresholds[name]) for value in values),
            "maximum": max(values),
            "mean": sum(values) / len(values),
            "minimum": min(values),
            "threshold": float(thresholds[name]),
        }
    return {
        "artifact_type": "phase5c_repeatability_summary",
        "comparison_n": len(comparisons),
        "decision_status": decision["status"],
        "metric_aggregates": aggregates,
        "model_version": decision["model_version"],
        "schema_version": 1,
        "selected_query_ids": decision["selected_query_ids"],
        "trace_record_n": decision["trace_record_n"],
    }


def _operational_summary(
    records: Iterable[Mapping[str, Any]], ledger: NetworkAttemptLedger
) -> dict[str, Any]:
    """Summarize observed trace operations only; never compute relevance metrics."""

    rows = list(records)
    latencies: list[float] = []
    usage_rows: list[dict[str, int]] = []
    started: list[str] = []
    ended: list[str] = []
    primary_ids: set[str] = set()
    for row in rows:
        attempts = row.get("attempts")
        if not isinstance(attempts, list) or len(attempts) != 1:
            raise PromptRAGContractError("complete trace must have one attempt per logical call")
        attempt = attempts[0]
        if not isinstance(attempt, Mapping) or attempt.get("status") != "valid":
            raise PromptRAGContractError("complete trace contains non-valid attempt")
        latencies.append(_duration_ms(attempt))
        started.append(str(attempt["started_at"]))
        ended.append(str(attempt["ended_at"]))
        raw_response = row.get("raw_response")
        if not isinstance(raw_response, Mapping):
            raise PromptRAGContractError("trace record lacks raw response")
        usage_rows.append(_usage(raw_response))
        logical_id = str(row.get("logical_request_id"))
        if logical_id.endswith(":primary"):
            primary_ids.add(logical_id.split(":", 1)[0])
    totals = {
        name: sum(usage[name] for usage in usage_rows)
        for name in sorted(usage_rows[0])
    }
    return {
        "artifact_type": "phase5c_operational_summary",
        "attempted_network_request_n": ledger.state["attempted_network_request_n"],
        "latency_ms": {
            "maximum": max(latencies),
            "mean": sum(latencies) / len(latencies),
            "median": _percentile(latencies, 0.5),
            "minimum": min(latencies),
            "p95": _percentile(latencies, 0.95),
            "sample_n": len(latencies),
            "source": "preserved per-attempt started_at and ended_at timestamps",
        },
        "logical_request_n": len(rows),
        "malformed_response_n": 0,
        "model_version": ledger.state["returned_model_version"],
        "monetary_cost_usd": 0.0,
        "primary_query_coverage": {
            "expected": TRACE_QUERY_N,
            "rate": len(primary_ids) / TRACE_QUERY_N,
            "successful": len(primary_ids),
        },
        "provider_usage_totals": totals,
        "quota_stop_n": 0,
        "refusal_or_block_n": 0,
        "retry_n": ledger.state["attempted_network_request_n"] - len(rows),
        "schema_version": 1,
        "terminal_failure_n": 0,
        "trace_ended_at": max(ended),
        "trace_started_at": min(started),
    }


def evaluate() -> dict[str, Any]:
    """Validate trace scope and write deterministic Phase 5C checkpoint outputs."""

    _verify_freeze_manifest()
    config = _json(CONFIG_PATH)
    trace_selection = _json(TRACE_SELECTION_PATH)
    protocol = _json(REPEATABILITY_PROTOCOL_PATH)
    token_audit = _json(TOKEN_AUDIT_PATH)
    plan_audit = _json(TRACE_PLAN_PATH)
    query_rows = _jsonl(ROOT / config["benchmark_boundary"]["query_path"])
    query_ids = [row.get("query_id") for row in query_rows]
    if query_ids != list(EXPECTED_QUERY_IDS):
        raise PromptRAGContractError("Phase 5C query IDs differ from frozen R5 order")
    trace_ids = [row.get("query_id") for row in trace_selection.get("selected", [])]
    if trace_ids != protocol.get("selected_query_ids"):
        raise PromptRAGContractError("trace selection differs from repeatability protocol")
    plan = build_logical_plan("trace", query_ids, trace_ids)
    if len(plan) != TRACE_LOGICAL_N:
        raise PromptRAGContractError("Phase 5C trace plan must contain exactly 24 calls")
    request_hashes = {
        row.get("query_id"): row.get("request_sha256")
        for row in token_audit.get("per_query", [])
    }
    if set(request_hashes) != set(EXPECTED_QUERY_IDS):
        raise PromptRAGContractError("token audit request hashes are incomplete")
    network_scope = plan_audit.get("network_scope")
    permissions = plan_audit.get("permissions")
    if (
        not isinstance(network_scope, dict)
        or network_scope.get("logical_request_n") != TRACE_LOGICAL_N
        or not isinstance(permissions, dict)
        or permissions.get("relevance_metric_calculation") is not False
        or permissions.get("pool_expansion") is not False
    ):
        raise PromptRAGContractError("Phase 5C trace plan permissions are invalid")
    records = _load_trace_records(plan)
    authorization = _execution_authorization(config)
    ledger = _validate_ledger(
        config=config,
        query_ids=query_ids,
        plan=plan,
        request_hashes=request_hashes,
        records=records,
    )
    decision = recompute_trace_decision(
        records,
        trace_ids=trace_ids,
        expected_request_hashes=request_hashes,
        thresholds=_thresholds(protocol),
    )
    repeatability = _repeatability_summary(decision)
    operational = _operational_summary(records, ledger)
    checkpoint = {
        "artifact_type": "phase5c_trace_checkpoint",
        "full_run_authorized": False,
        "generation_permitted": False,
        "model_version": decision["model_version"],
        "owner_approval_required_before_full_run": True,
        "owner_judging_permitted": False,
        "pool_expansion_permitted": False,
        "relevance_metrics_permitted": False,
        "repeatability_decision": decision["status"],
        "schema_version": 1,
        "status": "stopped_for_owner_approval_after_trace_evaluation",
        "trace_logical_request_n": TRACE_LOGICAL_N,
        "trace_query_n": TRACE_QUERY_N,
    }
    _write_exact(DECISION_PATH, decision)
    _write_exact(REPEATABILITY_SUMMARY_PATH, repeatability)
    _write_exact(OPERATIONAL_SUMMARY_PATH, operational)
    _write_exact(CHECKPOINT_PATH, checkpoint)
    artifact_paths = [
        CONFIG_PATH,
        PROMPT_PATH,
        TRACE_SELECTION_PATH,
        REPEATABILITY_PROTOCOL_PATH,
        TOKEN_AUDIT_PATH,
        TRACE_PLAN_PATH,
        FREE_TIER_CONFIRMATION_PATH,
        TRACE_APPROVAL_PATH,
        LEDGER_PATH,
        DECISION_PATH,
        REPEATABILITY_SUMMARY_PATH,
        OPERATIONAL_SUMMARY_PATH,
        CHECKPOINT_PATH,
        *sorted(RAW_ROOT.glob("*.json")),
    ]
    artifact_hashes = {
        str(path.relative_to(ROOT)): sha256_file(path) for path in artifact_paths
    }
    manifest = {
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
        "artifact_type": "phase5c_trace_artifact_manifest",
        "execution_authorization": authorization,
        "manifest_self_hash_excluded": True,
        "raw_trace_record_n": len(records),
        "schema_version": 1,
        "status": checkpoint["status"],
    }
    _write_exact(ARTIFACT_MANIFEST_PATH, manifest)
    return {
        "artifact_manifest": str(ARTIFACT_MANIFEST_PATH.relative_to(ROOT)),
        "checkpoint": checkpoint,
        "operational_summary": operational,
        "repeatability_summary": repeatability,
    }


def parser() -> argparse.ArgumentParser:
    """Build fixed-path Phase 5C evaluator CLI."""

    return argparse.ArgumentParser(description=__doc__)


def main() -> int:
    parser().parse_args()
    try:
        result = evaluate()
    except (NetworkAttemptCapError, PromptRAGContractError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 78
    print(stable_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
