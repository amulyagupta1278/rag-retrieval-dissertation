#!/usr/bin/env python3
"""Count tokens or execute one frozen Claude Prompt-RAG recovery scope."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.retrievers.prompt_rag_claude_v1 import (  # noqa: E402
    API_VERSION,
    HARD_COST_CAP_USD,
    MODEL,
    ClaudeContractError,
    ClaudeProviderError,
    build_request,
    create_client_from_environment,
    make_live_sender,
    make_token_counter,
    maximum_cost_usd,
    observed_cost_usd,
    request_sha256,
    validate_response,
)
from src.utils.atomic_io import stable_json, write_json  # noqa: E402
from src.utils.hashing import sha256_file, sha256_text  # noqa: E402


CONFIG_PATH = ROOT / "configs/prompt_rag_claude_v1_frozen.json"
MANIFEST_PATH = ROOT / "audits/phase5d/freeze_manifest.json"
REQUEST_PLAN_PATH = ROOT / "audits/phase5d/request_plan.json"
TRACE_SELECTION_PATH = ROOT / "audits/phase5b/trace_selection.json"
PROMPT_PATH = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
OUTPUT_ROOT = ROOT / "runs/v2/phase5d_prompt_rag_claude_v1"
TOKEN_AUDIT_PATH = OUTPUT_ROOT / "token_count_audit.json"
TRACE_DECISION_PATH = OUTPUT_ROOT / "trace/repeatability_decision.json"
EXPECTED_QUERY_IDS = tuple(f"v2q-{index:03d}" for index in range(1, 35))


class ExecutionLock:
    """Exclusive process lock; stale locks require manual inspection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "ExecutionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ClaudeContractError("another Claude runner holds execution lock") from None
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


def build_logical_plan(
    mode: str, query_ids: list[str], trace_ids: list[str]
) -> list[tuple[str, str]]:
    """Build trace 24-call or remaining-primary 26-call scope."""

    if query_ids != list(EXPECTED_QUERY_IDS):
        raise ClaudeContractError("exact ordered R5 query IDs required")
    if len(trace_ids) != 8 or len(set(trace_ids)) != 8:
        raise ClaudeContractError("exactly eight unique trace IDs required")
    if mode == "trace":
        return [
            (f"{query_id}:{role}", query_id)
            for role in ("primary", "replicate-1", "replicate-2")
            for query_id in trace_ids
        ]
    if mode == "full":
        selected = set(trace_ids)
        return [
            (f"{query_id}:primary", query_id)
            for query_id in query_ids
            if query_id not in selected
        ]
    raise ClaudeContractError(f"unsupported generation mode: {mode}")


def _verify_manifest() -> None:
    manifest = _json(MANIFEST_PATH)
    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ClaudeContractError("Claude freeze manifest lacks artifact hashes")
    for relative, expected in hashes.items():
        path = _canonical(relative)
        if path == MANIFEST_PATH or not path.is_file() or sha256_file(path) != expected:
            raise ClaudeContractError(f"freeze hash mismatch: {relative}")


def preflight() -> dict[str, Any]:
    """Rebuild all 34 payloads using only frozen non-sensitive inputs."""

    _verify_manifest()
    config = _json(CONFIG_PATH)
    if config.get("provider") != "Anthropic Claude API":
        raise ClaudeContractError("provider mismatch")
    if config.get("model") != MODEL or config.get("api_version") != API_VERSION:
        raise ClaudeContractError("model or API version mismatch")
    prompt_path = _canonical(config["prompt"]["path"])
    query_path = _canonical(config["inputs"]["query_path"])
    chunk_path = _canonical(config["inputs"]["chunk_path"])
    ranking_path = _canonical(config["inputs"]["sanitized_ranking_path"])
    source_ranking_path = _canonical(config["inputs"]["source_ranking_path"])
    for path, expected in (
        (prompt_path, config["prompt"]["sha256"]),
        (query_path, config["inputs"]["query_sha256"]),
        (chunk_path, config["inputs"]["chunk_sha256"]),
        (ranking_path, config["inputs"]["sanitized_ranking_sha256"]),
        (source_ranking_path, config["inputs"]["source_ranking_sha256"]),
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
    ranking_rows = _jsonl(ranking_path)
    for row in ranking_rows:
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
        raise ClaudeContractError("Claude request hashes differ from frozen plan")
    trace = _json(TRACE_SELECTION_PATH)
    trace_ids = [row.get("query_id") for row in trace.get("selected", [])]
    if trace_ids != config["trace_query_ids"]:
        raise ClaudeContractError("trace IDs differ from frozen structural selection")
    return {
        "config": config,
        "query_ids": query_ids,
        "rankings": rankings,
        "requests": requests,
        "trace_ids": trace_ids,
    }


def run_token_audit(
    frozen: dict[str, Any], *, client_factory: Callable[[], Any]
) -> int:
    """Count exact Anthropic input tokens once per unique query payload."""

    if TOKEN_AUDIT_PATH.exists():
        raise ClaudeContractError("token audit already exists; refusing overwrite")
    client = client_factory()
    counter = make_token_counter(client)
    per_query: list[dict[str, Any]] = []
    for query_id in frozen["query_ids"]:
        count = counter(frozen["requests"][query_id])
        per_query.append(
            {
                "input_tokens": count,
                "query_id": query_id,
                "request_sha256": request_sha256(frozen["requests"][query_id]),
            }
        )
    counts = {row["query_id"]: row["input_tokens"] for row in per_query}
    trace_ids = set(frozen["trace_ids"])
    trace_input = sum(counts[query_id] * 3 for query_id in frozen["trace_ids"])
    full_input = sum(
        count for query_id, count in counts.items() if query_id not in trace_ids
    )
    max_cost = maximum_cost_usd(trace_input + full_input, 50)
    if max_cost > HARD_COST_CAP_USD:
        raise ClaudeContractError(
            f"worst-case cost ${max_cost:.6f} exceeds hard cap ${HARD_COST_CAP_USD:.2f}"
        )
    write_json(
        TOKEN_AUDIT_PATH,
        {
            "api_version": API_VERSION,
            "count_token_network_request_n": 34,
            "generation_request_n": 0,
            "hard_cost_cap_usd": HARD_COST_CAP_USD,
            "model": MODEL,
            "per_query": per_query,
            "schema_version": 1,
            "scope": {
                "full_input_tokens": full_input,
                "full_request_n": 26,
                "total_input_tokens": trace_input + full_input,
                "total_request_n": 50,
                "trace_input_tokens": trace_input,
                "trace_request_n": 24,
                "worst_case_cost_usd": max_cost,
            },
            "status": "provider_token_counts_complete_no_generation",
        },
        overwrite=False,
    )
    return 0


def _validated_token_audit(frozen: dict[str, Any]) -> dict[str, Any]:
    audit = _json(TOKEN_AUDIT_PATH)
    if (
        audit.get("model") != MODEL
        or audit.get("status") != "provider_token_counts_complete_no_generation"
        or audit.get("hard_cost_cap_usd") != HARD_COST_CAP_USD
    ):
        raise ClaudeContractError("token audit contract mismatch")
    rows = audit.get("per_query")
    if not isinstance(rows, list) or len(rows) != 34:
        raise ClaudeContractError("token audit must contain 34 query rows")
    expected = {
        query_id: request_sha256(request)
        for query_id, request in frozen["requests"].items()
    }
    if {row.get("query_id"): row.get("request_sha256") for row in rows} != expected:
        raise ClaudeContractError("token audit request hashes mismatch")
    if float(audit["scope"]["worst_case_cost_usd"]) > HARD_COST_CAP_USD:
        raise ClaudeContractError("token audit exceeds hard cost cap")
    return audit


def _initial_ledger(mode: str, plan: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "actual_input_tokens": 0,
        "actual_output_tokens": 0,
        "attempted_generation_request_n": 0,
        "completed_logical_request_ids": [],
        "hard_cost_cap_usd": HARD_COST_CAP_USD,
        "mode": mode,
        "observed_cost_usd": 0.0,
        "planned_logical_request_ids": [logical_id for logical_id, _ in plan],
        "schema_version": 1,
        "status": "ready",
    }


def _save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_json(path, ledger, overwrite=path.exists())


def _prior_actual_usage(mode: str) -> tuple[int, int]:
    if mode == "trace":
        return 0, 0
    trace_ledger = _json(OUTPUT_ROOT / "trace/control/ledger.json")
    if trace_ledger.get("status") != "complete":
        raise ClaudeContractError("full mode requires complete trace ledger")
    decision = _json(TRACE_DECISION_PATH)
    if decision.get("status") != "repeatability_gate_passed":
        raise ClaudeContractError("full mode requires passed repeatability gate")
    return int(trace_ledger["actual_input_tokens"]), int(
        trace_ledger["actual_output_tokens"]
    )


def run_generation(
    mode: str,
    frozen: dict[str, Any],
    *,
    client_factory: Callable[[], Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    """Execute exact scope once, with no retries, fallback, or overwrite."""

    audit = _validated_token_audit(frozen)
    plan = build_logical_plan(mode, frozen["query_ids"], frozen["trace_ids"])
    mode_root = OUTPUT_ROOT / mode
    ledger_path = mode_root / "control/ledger.json"
    if ledger_path.exists():
        ledger = _json(ledger_path)
    else:
        ledger = _initial_ledger(mode, plan)
        _save_ledger(ledger_path, ledger)
    if ledger.get("planned_logical_request_ids") != [row[0] for row in plan]:
        raise ClaudeContractError("generation ledger plan mismatch")
    if ledger.get("status") in {"failed", "complete"}:
        raise ClaudeContractError(f"generation ledger is terminal: {ledger['status']}")
    if ledger.get("status") == "attempt_counted_before_dispatch":
        raise ClaudeContractError(
            "prior dispatch outcome is ambiguous; refusing possible duplicate billing"
        )

    prior_input, prior_output = _prior_actual_usage(mode)
    per_query_counts = {
        row["query_id"]: row["input_tokens"] for row in audit["per_query"]
    }
    remaining_input = sum(
        per_query_counts[query_id]
        for logical_id, query_id in plan
        if logical_id not in ledger["completed_logical_request_ids"]
    )
    total_projected = observed_cost_usd(
        prior_input + ledger["actual_input_tokens"],
        prior_output + ledger["actual_output_tokens"],
    ) + maximum_cost_usd(
        remaining_input,
        len(plan) - len(ledger["completed_logical_request_ids"]),
    )
    if total_projected > HARD_COST_CAP_USD:
        raise ClaudeContractError(
            f"remaining worst-case cost ${total_projected:.6f} exceeds hard cap"
        )

    client = client_factory()
    sender = make_live_sender(client)
    for logical_id, query_id in plan:
        if logical_id in ledger["completed_logical_request_ids"]:
            continue
        pending = [
            pending_query_id
            for pending_logical_id, pending_query_id in plan
            if pending_logical_id not in ledger["completed_logical_request_ids"]
        ]
        remaining_worst_case = observed_cost_usd(
            prior_input + ledger["actual_input_tokens"],
            prior_output + ledger["actual_output_tokens"],
        ) + maximum_cost_usd(
            sum(per_query_counts[pending_query_id] for pending_query_id in pending),
            len(pending),
        )
        if remaining_worst_case > HARD_COST_CAP_USD:
            raise ClaudeContractError(
                f"updated remaining worst-case cost ${remaining_worst_case:.6f} exceeds hard cap"
            )
        request = frozen["requests"][query_id]
        request_hash = request_sha256(request)
        safe_name = logical_id.replace(":", "__")
        raw_path = mode_root / "raw" / f"{safe_name}.json"
        if raw_path.exists():
            raise ClaudeContractError("uncommitted response exists outside ledger")

        ledger["attempted_generation_request_n"] += 1
        ledger["status"] = "attempt_counted_before_dispatch"
        _save_ledger(ledger_path, ledger)
        started_at = now()
        started_monotonic = time.monotonic()
        try:
            response = sender(request)
        except ClaudeProviderError as exc:
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                mode_root / "failures" / f"{safe_name}.json",
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
            validated = validate_response(
                response, expected_chunk_ids=frozen["rankings"][query_id]
            )
        except ClaudeContractError as exc:
            raw = (
                response.model_dump(mode="json", by_alias=True, exclude_none=True)
                if hasattr(response, "model_dump")
                else {}
            )
            ledger["status"] = "failed"
            _save_ledger(ledger_path, ledger)
            write_json(
                mode_root / "failures" / f"{safe_name}.json",
                {
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                    "invalid_raw_response": raw,
                    "logical_request_id": logical_id,
                    "request_sha256": request_hash,
                    "schema_version": 1,
                },
                overwrite=False,
            )
            return 76

        usage = validated["usage"]
        ledger["actual_input_tokens"] += usage["input_tokens"]
        ledger["actual_output_tokens"] += usage["output_tokens"]
        ledger["observed_cost_usd"] = observed_cost_usd(
            ledger["actual_input_tokens"], ledger["actual_output_tokens"]
        )
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
            "schema_version": 1,
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
    result.add_argument("--mode", choices=("token-audit", "trace", "full"), required=True)
    result.add_argument(
        "--acknowledge-paid-api-and-hard-cap",
        action="store_true",
        required=True,
        help="confirm Anthropic calls are paid and total frozen cap is USD 1.90",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.acknowledge_paid_api_and_hard_cap:
        print("refused: paid API acknowledgement missing", file=sys.stderr)
        return 78
    try:
        frozen = preflight()
        lock_mode = args.mode.replace("-", "_")
        with ExecutionLock(OUTPUT_ROOT / lock_mode / "control/execution.lock"):
            if args.mode == "token-audit":
                return run_token_audit(
                    frozen, client_factory=create_client_from_environment
                )
            return run_generation(
                args.mode, frozen, client_factory=create_client_from_environment
            )
    except (ClaudeContractError, ClaudeProviderError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
