#!/usr/bin/env python3
"""Execute owner-approved Phase 8 five-request generation trace once."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Mapping

import anthropic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase7_freeze import Phase7ExecutionFailure  # noqa: E402
from src.generation.phase7_v2_freeze import (  # noqa: E402
    MAX_OUTPUT_TOKENS,
    MODEL,
    SDK_VERSION,
    TEMPERATURE,
    observed_cost_usd,
    request_sha256,
    validate_provider_response,
)
from src.utils.atomic_io import write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


FREEZE = ROOT / "runs/phase8_exploratory_five_system/generation_freeze_v1"
TRACE_OUT = ROOT / "runs/phase8_exploratory_five_system/generation_trace_v1"
APPROVAL = ROOT / "audits/phase8_exploratory/generation_trace_v1_approval.json"
TRACE_N = 5
TRACE_CAP_USD = 0.10
FULL_CAP_USD = 1.25
TIMEOUT_SECONDS = 120.0


class Phase8GenerationError(ValueError):
    """Raised when frozen Phase 8 generation contract differs."""


def expected_approval(commit: str) -> str:
    return (
        "Approve Phase 8 cost-adapted generation 5-request trace at commit "
        f"{commit}, using claude-haiku-4-5-20251001, five frozen trace requests "
        "covering all five systems and all five available Phase 8 categories, "
        "top-3 contexts drawn only from each system's frozen top-10 results, "
        "frozen prompt, strict citation schema, temperature 0, 512 maximum output "
        "tokens, zero retries, no fallback or replacement, separate trace outputs, "
        "a $0.10 trace cap, and cumulative 100-request generation hard cap $1.25. "
        "Stop after trace validation and cost reporting. Do not run remaining 95 "
        "requests, evaluation, judging, or H5 analysis."
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Phase8GenerationError(f"JSON object required: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise Phase8GenerationError(f"nonempty JSONL objects required: {path}")
    return rows


def verify_manifest() -> None:
    manifest = load_json(FREEZE / "freeze_manifest.json")
    if manifest.get("live_api_calls_n") != 0 or manifest.get("execution_authorized") is not False:
        raise Phase8GenerationError("freeze state differs")
    for section in ("inputs", "artifacts", "code"):
        for relative, expected in manifest[section].items():
            path = ROOT / relative
            if not path.is_file() or sha256_file(path) != expected:
                raise Phase8GenerationError(f"frozen hash mismatch: {relative}")


def verify_approval() -> dict[str, Any]:
    approval = load_json(APPROVAL)
    commit = approval.get("approved_freeze_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        raise Phase8GenerationError("approved freeze commit missing")
    if (
        approval.get("status") != "owner_approved"
        or approval.get("owner_statement") != expected_approval(commit)
        or approval.get("trace_request_n") != TRACE_N
        or approval.get("full_run_authorized") is not False
        or approval.get("trace_hard_cap_usd") != TRACE_CAP_USD
        or approval.get("generation_hard_cap_usd") != FULL_CAP_USD
        or approval.get("execution_config_sha256") != sha256_file(FREEZE / "execution_config.json")
        or approval.get("freeze_manifest_sha256") != sha256_file(FREEZE / "freeze_manifest.json")
    ):
        raise Phase8GenerationError("owner approval differs from freeze")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT, capture_output=True)
    if result.returncode != 0:
        raise Phase8GenerationError("approved commit is not current history")
    return approval


def preflight(*, require_approval: bool = True) -> dict[str, Any]:
    verify_manifest()
    if require_approval:
        verify_approval()
    config = load_json(FREEZE / "execution_config.json")
    cost = load_json(FREEZE / "cost_plan.json")
    trace = load_json(FREEZE / "sealed/trace_plan.json")["selected"]
    payloads = {row["blinded_request_id"]: row for row in load_jsonl(FREEZE / "blinded/request_payloads.jsonl")}
    plans = {row["blinded_request_id"]: row for row in load_jsonl(FREEZE / "sealed/request_plan.jsonl")}
    if (
        config["request_n"] != 100
        or config["trace_request_n"] != TRACE_N
        or config["retry_n"] != 0
        or config["generation"] != {"max_output_tokens": 512, "model": MODEL, "temperature": TEMPERATURE}
        or cost["trace_hard_cap_usd"] != TRACE_CAP_USD
        or cost["full_hard_cap_usd"] != FULL_CAP_USD
        or cost["hard_cap_pass"] is not True
        or len(payloads) != 100
        or len(plans) != 100
    ):
        raise Phase8GenerationError("generation config differs")
    rows = []
    for selected in trace:
        blind_id = selected["blinded_request_id"]
        payload, plan = payloads[blind_id], plans[blind_id]
        request = payload["request"]
        if (
            payload["request_sha256"] != plan["request_sha256"]
            or request_sha256(request) != plan["request_sha256"]
            or request["max_tokens"] != MAX_OUTPUT_TOKENS
            or plan["context_chunk_ids"] != plan["top10_chunk_ids"][:3]
            or selected["request_sha256"] != plan["request_sha256"]
        ):
            raise Phase8GenerationError("trace request differs")
        rows.append({"blinded_request_id": blind_id, "plan": plan, "request": request})
    if len(rows) != TRACE_N or len({row["plan"]["system_id"] for row in rows}) != 5 or len({row["plan"]["category"] for row in rows}) != 5:
        raise Phase8GenerationError("trace coverage differs")
    return {"config": config, "cost": cost, "rows": rows}


def create_sender() -> Callable[[dict[str, Any]], Any]:
    if metadata.version("anthropic") != SDK_VERSION:
        raise Phase8GenerationError("anthropic SDK version differs")
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise Phase7ExecutionFailure("credential_unavailable")
    client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=TIMEOUT_SECONDS)
    return lambda request: client.messages.create(**copy.deepcopy(request))


def response_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return copy.deepcopy(dict(response))
    value = response.model_dump(mode="json", by_alias=True, exclude_none=True)
    if not isinstance(value, dict):
        raise Phase7ExecutionFailure("missing_response")
    return value


def run(frozen: dict[str, Any], sender: Callable[[dict[str, Any]], Any]) -> int:
    if TRACE_OUT.exists():
        raise Phase8GenerationError("trace output already exists; never overwrite or rerun")
    TRACE_OUT.mkdir(parents=True)
    ledger = {
        "attempted_request_n": 0,
        "completed_blinded_request_ids": [],
        "full_run_authorized": False,
        "generation_hard_cap_usd": FULL_CAP_USD,
        "input_tokens": 0,
        "observed_cost_usd": 0.0,
        "output_tokens": 0,
        "retry_n": 0,
        "status": "ready",
        "trace_hard_cap_usd": TRACE_CAP_USD,
    }
    write_json(TRACE_OUT / "ledger.json", ledger)
    for row in frozen["rows"]:
        remaining = frozen["rows"][ledger["attempted_request_n"] :]
        projected_trace = ledger["observed_cost_usd"] + sum(
            item["plan"]["planned_input_token_envelope"] / 1_000_000 + MAX_OUTPUT_TOKENS * 5 / 1_000_000
            for item in remaining
        ) + frozen["cost"]["ambiguous_dispatch_reserve_usd"]
        if projected_trace > TRACE_CAP_USD + 1e-12:
            raise Phase7ExecutionFailure("cost_cap_breach")
        ledger["attempted_request_n"] += 1
        ledger["status"] = "attempt_counted_before_dispatch"
        write_json(TRACE_OUT / "ledger.json", ledger, overwrite=True)
        try:
            raw = response_dict(sender(row["request"]))
            validated = validate_provider_response(raw, available_evidence_ids=list(row["plan"]["evidence_id_to_chunk_id"]))
        except Exception as exc:
            ledger["status"] = "failed_terminal_no_retry"
            ledger["failure"] = {"message": str(exc), "type": type(exc).__name__}
            write_json(TRACE_OUT / "ledger.json", ledger, overwrite=True)
            return 1
        (TRACE_OUT / "raw").mkdir(exist_ok=True)
        (TRACE_OUT / "validated").mkdir(exist_ok=True)
        write_json(TRACE_OUT / "raw" / f"{row['blinded_request_id']}.json", raw)
        write_json(TRACE_OUT / "validated" / f"{row['blinded_request_id']}.json", {"blinded_request_id": row["blinded_request_id"], **validated})
        ledger["completed_blinded_request_ids"].append(row["blinded_request_id"])
        ledger["input_tokens"] += validated["usage"]["input_tokens"]
        ledger["output_tokens"] += validated["usage"]["output_tokens"]
        ledger["observed_cost_usd"] = round(observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6)
        ledger["status"] = "running"
        write_json(TRACE_OUT / "ledger.json", ledger, overwrite=True)
    ledger["status"] = "trace_complete"
    ledger["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(TRACE_OUT / "ledger.json", ledger, overwrite=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--offline-preflight", action="store_true")
    args = parser.parse_args()
    frozen = preflight(require_approval=not args.offline_preflight)
    if args.preflight or args.offline_preflight:
        print(json.dumps({"status": "ready" if not args.offline_preflight else "frozen_pending_approval", "trace_n": len(frozen["rows"]), "trace_cap_usd": TRACE_CAP_USD}, indent=2))
        return 0
    return run(frozen, create_sender())


if __name__ == "__main__":
    raise SystemExit(main())
