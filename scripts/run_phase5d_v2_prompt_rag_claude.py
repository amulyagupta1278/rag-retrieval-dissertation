#!/usr/bin/env python3
"""Execute only owner-approved Phase 5D V2 24-call Claude trace."""

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

from src.retrievers.prompt_rag_claude_v2 import (  # noqa: E402
    API_VERSION,
    CANDIDATE_N,
    HARD_COST_CAP_USD,
    MAX_OUTPUT_TOKENS,
    MODEL,
    PRIOR_SPENT_USD,
    SDK_VERSION,
    TRACE_INPUT_TOKEN_ENVELOPE,
    TRACE_REQUEST_N,
    TRACE_WORST_CASE_COST_USD,
    ClaudeContractError,
    ClaudeProviderError,
    build_request,
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


CONFIG_PATH = ROOT / "configs/prompt_rag_claude_v2_frozen.json"
MANIFEST_PATH = ROOT / "audits/phase5d_v2/freeze_manifest.json"
REQUEST_PLAN_PATH = ROOT / "audits/phase5d_v2/request_plan.json"
APPROVAL_PATH = ROOT / "audits/phase5d_v2/trace_execution_approval.json"
V1_PRESERVATION_PATH = ROOT / "audits/phase5d_v2/v1_preservation.json"
TRACE_SELECTION_PATH = ROOT / "audits/phase5b/trace_selection.json"
OUTPUT_ROOT = ROOT / "runs/v2/phase5d_prompt_rag_claude_v2"
TRACE_DECISION_PATH = OUTPUT_ROOT / "trace/repeatability_decision.json"
EXPECTED_QUERY_IDS = tuple(f"v2q-{index:03d}" for index in range(1, 35))


class ExecutionLock:
    """Exclusive process lock; ambiguous stale lock requires inspection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "ExecutionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ClaudeContractError("another V2 runner holds execution lock") from None
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
        raise ClaudeContractError(f"invalid JSON artifact: {path.relative_to(ROOT)}") from exc
    if not isinstance(value, dict):
        raise ClaudeContractError(f"JSON artifact must be object: {path.relative_to(ROOT)}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ClaudeContractError(f"cannot read JSONL: {path.relative_to(ROOT)}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ClaudeContractError(
                f"invalid JSONL at {path.relative_to(ROOT)}:{line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise ClaudeContractError("JSONL rows must be objects")
        rows.append(row)
    if not rows:
        raise ClaudeContractError(f"empty JSONL: {path.relative_to(ROOT)}")
    return rows


def _canonical(relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ClaudeContractError("config path must be non-empty and relative")
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        raise ClaudeContractError("config path escapes repository") from None
    if path != ROOT / relative:
        raise ClaudeContractError("config path is not canonical")
    return path


def build_trace_plan(trace_ids: list[str]) -> list[tuple[str, str]]:
    """Return frozen 24-call order: primary, replicate-1, replicate-2."""

    if len(trace_ids) != 8 or len(set(trace_ids)) != 8:
        raise ClaudeContractError("exactly eight unique trace IDs required")
    return [
        (f"{query_id}:{role}", query_id)
        for role in ("primary", "replicate-1", "replicate-2")
        for query_id in trace_ids
    ]


def _verify_hash_map(path: Path, field: str = "artifact_hashes") -> None:
    rows = _json(path).get(field)
    if not isinstance(rows, dict) or not rows:
        raise ClaudeContractError(f"hash map missing: {path.relative_to(ROOT)}")
    for relative, expected in rows.items():
        candidate = _canonical(relative)
        if candidate == path or not candidate.is_file() or sha256_file(candidate) != expected:
            raise ClaudeContractError(f"frozen hash mismatch: {relative}")


def preflight() -> dict[str, Any]:
    """Rebuild 34 requests from frozen inputs; never read V1 outputs as inputs."""

    _verify_hash_map(MANIFEST_PATH)
    _verify_hash_map(V1_PRESERVATION_PATH, "v1_artifact_hashes")
    config = _json(CONFIG_PATH)
    if config.get("provider") != "Anthropic Claude API":
        raise ClaudeContractError("provider mismatch")
    if config.get("model") != MODEL or config.get("api_version") != API_VERSION:
        raise ClaudeContractError("model or API version mismatch")
    if config.get("sdk") != {"name": "anthropic", "version": SDK_VERSION}:
        raise ClaudeContractError("SDK contract mismatch")
    if config.get("candidate_count") != CANDIDATE_N:
        raise ClaudeContractError("candidate count mismatch")

    inputs = config["inputs"]
    prompt_path = _canonical(config["prompt"]["path"])
    query_path = _canonical(inputs["query_path"])
    chunk_path = _canonical(inputs["chunk_path"])
    ranking_path = _canonical(inputs["sanitized_ranking_path"])
    source_ranking_path = _canonical(inputs["source_ranking_path"])
    for path, expected in (
        (prompt_path, config["prompt"]["sha256"]),
        (query_path, inputs["query_sha256"]),
        (chunk_path, inputs["chunk_sha256"]),
        (ranking_path, inputs["sanitized_ranking_sha256"]),
        (source_ranking_path, inputs["source_ranking_sha256"]),
    ):
        if sha256_file(path) != expected:
            raise ClaudeContractError(f"input hash mismatch: {path.relative_to(ROOT)}")

    query_rows = _jsonl(query_path)
    query_ids = [row.get("query_id") for row in query_rows]
    if query_ids != list(EXPECTED_QUERY_IDS) or any(
        set(row) != {"query_id", "question"} for row in query_rows
    ):
        raise ClaudeContractError("query-only input differs from frozen contract")
    chunks: dict[str, str] = {}
    for row in _jsonl(chunk_path):
        chunk_id, text = row.get("chunk_id"), row.get("text")
        if (
            not isinstance(chunk_id, str)
            or not isinstance(text, str)
            or not text.strip()
            or chunk_id in chunks
        ):
            raise ClaudeContractError("chunk input contains invalid or duplicate row")
        chunks[chunk_id] = text
    if len(chunks) != 140:
        raise ClaudeContractError("frozen corpus must contain 140 chunks")

    rankings: dict[str, list[str]] = {}
    for row in _jsonl(ranking_path):
        if set(row) != {"query_id", "chunk_ids"}:
            raise ClaudeContractError("sanitized ranking contains forbidden fields")
        ids = row["chunk_ids"]
        if not isinstance(ids, list) or len(ids) != 50 or len(set(ids)) != 50:
            raise ClaudeContractError("each query requires 50 unique candidates")
        if any(chunk_id not in chunks for chunk_id in ids):
            raise ClaudeContractError("ranking contains unknown chunk ID")
        rankings[row["query_id"]] = ids
    if list(rankings) != query_ids:
        raise ClaudeContractError("ranking query order mismatch")
    source = {
        row.get("query_id"): [item.get("chunk_id") for item in row.get("ranking", [])]
        for row in _jsonl(source_ranking_path)
    }
    if source != rankings:
        raise ClaudeContractError("sanitized rankings differ from frozen BM25 top-50")

    prompt = prompt_path.read_text(encoding="utf-8")
    query_by_id = {row["query_id"]: row for row in query_rows}
    requests = {
        query_id: build_request(
            query=query_by_id[query_id],
            candidates=[
                {"chunk_id": chunk_id, "text": chunks[chunk_id]}
                for chunk_id in rankings[query_id]
            ],
            system_instruction=prompt,
        )
        for query_id in query_ids
    }
    request_plan = _json(REQUEST_PLAN_PATH)
    expected_hashes = {
        row["query_id"]: row["request_sha256"] for row in request_plan["per_query"]
    }
    actual_hashes = {
        query_id: request_sha256(request) for query_id, request in requests.items()
    }
    if expected_hashes != actual_hashes:
        raise ClaudeContractError("V2 request hashes differ from frozen plan")
    trace = _json(TRACE_SELECTION_PATH)
    trace_ids = [row.get("query_id") for row in trace.get("selected", [])]
    if trace_ids != config["trace_query_ids"]:
        raise ClaudeContractError("trace IDs differ from frozen structural selection")
    if len(build_trace_plan(trace_ids)) != TRACE_REQUEST_N:
        raise ClaudeContractError("trace request scope mismatch")
    return {
        "config": config,
        "query_ids": query_ids,
        "rankings": rankings,
        "requests": requests,
        "trace_ids": trace_ids,
    }


def expected_approval_statement(freeze_commit: str) -> str:
    """Build exact owner statement bound to committed V2 freeze."""

    return (
        "Approve Phase 5D V2 24-call trace at commit "
        f"{freeze_commit}, using fixed-key object schema, "
        "claude-haiku-4-5-20251001, no retries, separate V2 outputs, and "
        "cumulative $1.90 hard cap ($0.177402 spent; $1.722598 remaining before V2)."
    )


def _validate_approval() -> dict[str, Any]:
    approval = _json(APPROVAL_PATH)
    commit = approval.get("approved_freeze_commit")
    if approval.get("status") != "owner_approved" or not isinstance(commit, str):
        raise ClaudeContractError("Phase 5D V2 trace lacks owner approval")
    if approval.get("owner_statement") != expected_approval_statement(commit):
        raise ClaudeContractError("owner approval statement mismatch")
    if approval.get("config_sha256") != sha256_file(CONFIG_PATH):
        raise ClaudeContractError("owner approval config hash mismatch")
    if approval.get("freeze_manifest_sha256") != sha256_file(MANIFEST_PATH):
        raise ClaudeContractError("owner approval manifest hash mismatch")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ClaudeContractError("approved freeze commit is not current history")
    return approval


def _initial_ledger(plan: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "actual_input_tokens": 0,
        "actual_output_tokens": 0,
        "attempted_generation_request_n": 0,
        "completed_logical_request_ids": [],
        "cumulative_observed_cost_usd": PRIOR_SPENT_USD,
        "hard_cost_cap_usd": HARD_COST_CAP_USD,
        "planned_logical_request_ids": [logical_id for logical_id, _ in plan],
        "prior_spent_usd": PRIOR_SPENT_USD,
        "schema_version": 2,
        "status": "ready",
        "v2_observed_cost_usd": 0.0,
    }


def _save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_json(path, ledger, overwrite=path.exists())


def _projected_cumulative_cost(ledger: dict[str, Any], remaining_n: int) -> float:
    """Use observed spend plus full input envelope again: conservative cap gate."""

    return (
        PRIOR_SPENT_USD
        + observed_cost_usd(
            int(ledger["actual_input_tokens"]), int(ledger["actual_output_tokens"])
        )
        + TRACE_INPUT_TOKEN_ENVELOPE / 1_000_000
        + remaining_n * MAX_OUTPUT_TOKENS * 5.0 / 1_000_000
    )


def run_trace(
    frozen: dict[str, Any],
    *,
    client_factory: Callable[[], Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    """Execute exact 24-call V2 trace once; no retry, fallback, or V1 selection."""

    _validate_approval()
    plan = build_trace_plan(frozen["trace_ids"])
    mode_root = OUTPUT_ROOT / "trace"
    ledger_path = mode_root / "control/ledger.json"
    ledger = _json(ledger_path) if ledger_path.exists() else _initial_ledger(plan)
    _save_ledger(ledger_path, ledger)
    if ledger.get("planned_logical_request_ids") != [row[0] for row in plan]:
        raise ClaudeContractError("V2 ledger plan mismatch")
    if ledger.get("status") in {"failed", "complete"}:
        raise ClaudeContractError(f"V2 ledger is terminal: {ledger['status']}")
    if ledger.get("status") == "attempt_counted_before_dispatch":
        raise ClaudeContractError("prior dispatch outcome ambiguous; refusing duplicate billing")
    if ledger.get("attempted_generation_request_n", 0) > TRACE_REQUEST_N:
        raise ClaudeContractError("trace hard request cap exceeded")

    client = client_factory()
    sender = make_live_sender(client)
    for logical_id, query_id in plan:
        if logical_id in ledger["completed_logical_request_ids"]:
            continue
        remaining_n = len(plan) - len(ledger["completed_logical_request_ids"])
        projected = _projected_cumulative_cost(ledger, remaining_n)
        if projected > HARD_COST_CAP_USD:
            raise ClaudeContractError(
                f"conservative cumulative projection ${projected:.6f} exceeds cap"
            )
        if ledger["attempted_generation_request_n"] >= TRACE_REQUEST_N:
            raise ClaudeContractError("trace hard request cap reached")
        request = frozen["requests"][query_id]
        request_hash = request_sha256(request)
        safe_name = logical_id.replace(":", "__")
        raw_path = mode_root / "raw" / f"{safe_name}.json"
        if raw_path.exists():
            raise ClaudeContractError("V2 response exists outside ledger")

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
                mode_root / "failures" / f"{safe_name}.json",
                {
                    "error_class": type(exc).__name__,
                    "http_status": exc.status_code,
                    "logical_request_id": logical_id,
                    "provider_error_body_preserved": False,
                    "request_sha256": request_hash,
                    "schema_version": 2,
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
                mode_root / "failures" / f"{safe_name}.json",
                {
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                    "logical_request_id": logical_id,
                    "request_sha256": request_hash,
                    "schema_version": 2,
                },
                overwrite=False,
            )
            return 76

        # Provider returned billable usage. Account before content validation.
        ledger["actual_input_tokens"] += usage["input_tokens"]
        ledger["actual_output_tokens"] += usage["output_tokens"]
        ledger["v2_observed_cost_usd"] = observed_cost_usd(
            ledger["actual_input_tokens"], ledger["actual_output_tokens"]
        )
        ledger["cumulative_observed_cost_usd"] = (
            PRIOR_SPENT_USD + ledger["v2_observed_cost_usd"]
        )
        if ledger["cumulative_observed_cost_usd"] > HARD_COST_CAP_USD:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            raise ClaudeContractError("observed cumulative cost exceeded hard cap")
        try:
            validated = validate_response(
                raw_response, expected_chunk_ids=frozen["rankings"][query_id]
            )
        except ClaudeContractError as exc:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                mode_root / "failures" / f"{safe_name}.json",
                {
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                    "invalid_raw_response": raw_response,
                    "logical_request_id": logical_id,
                    "request_sha256": request_hash,
                    "schema_version": 2,
                    "usage_accounted_before_validation": usage,
                },
                overwrite=False,
            )
            return 76

        ledger["completed_logical_request_ids"].append(logical_id)
        record = {
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
            "schema_version": 2,
            "started_at": started_at.isoformat(),
            "usage": usage,
        }
        write_json(raw_path, record, overwrite=False)
        ledger["status"] = "running"
        _save_ledger(ledger_path, ledger)

    ledger["status"] = "complete"
    _save_ledger(ledger_path, ledger)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=("trace",), required=True)
    result.add_argument(
        "--acknowledge-paid-api-and-hard-cap",
        action="store_true",
        required=True,
        help="confirm paid API and cumulative USD 1.90 hard cap",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.acknowledge_paid_api_and_hard_cap:
        print("refused: paid API acknowledgement missing", file=sys.stderr)
        return 78
    try:
        frozen = preflight()
        with ExecutionLock(OUTPUT_ROOT / "trace/control/execution.lock"):
            return run_trace(frozen, client_factory=create_client_from_environment)
    except (ClaudeContractError, ClaudeProviderError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
