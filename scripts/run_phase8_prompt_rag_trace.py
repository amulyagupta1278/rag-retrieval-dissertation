#!/usr/bin/env python3
"""Execute owner-approved Phase 8 Prompt-RAG five-request trace once."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values  # noqa: E402

from src.retrievers.prompt_rag_claude_v2 import (  # noqa: E402
    INPUT_USD_PER_MILLION,
    MAX_OUTPUT_TOKENS,
    OUTPUT_USD_PER_MILLION,
    ClaudeContractError,
    ClaudeProviderError,
    build_request,
    create_client_from_environment,
    make_live_sender,
    observed_cost_usd,
    request_sha256,
    validate_response,
)
from src.utils.atomic_io import write_json  # noqa: E402
from src.utils.io_utils import load_jsonl  # noqa: E402


QA = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qa_dataset.jsonl"
CHUNKS = ROOT / "releases/v3_clean/data/chunks/chunks_v3_clean.jsonl"
BM25 = ROOT / "runs/phase8_exploratory_five_system/bm25_top50/retrieval/bm25_run.jsonl"
PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
FREEZE = ROOT / "runs/phase8_exploratory_five_system/prompt_rag_freeze/execution_config.json"
PLAN = ROOT / "runs/phase8_exploratory_five_system/prompt_rag_freeze/request_plan.jsonl"
APPROVAL = ROOT / "audits/phase8_exploratory/prompt_rag_trace_approval.json"
OUT = ROOT / "runs/phase8_exploratory_five_system/prompt_rag_trace"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ClaudeContractError(f"object required: {path.relative_to(ROOT)}")
    return value


def preflight() -> dict:
    freeze = load_object(FREEZE)
    approval = load_object(APPROVAL)
    if freeze["status"] != "offline_frozen_pending_owner_trace_approval":
        raise ClaudeContractError("Prompt-RAG freeze status differs")
    if approval.get("status") != "owner_approved":
        raise ClaudeContractError("trace lacks owner approval")
    if approval.get("execution_config_sha256") != sha256(FREEZE):
        raise ClaudeContractError("approved execution config hash differs")
    if approval.get("request_plan_sha256") != sha256(PLAN):
        raise ClaudeContractError("approved request plan hash differs")
    if approval.get("request_n") != 5 or approval.get("hard_cap_usd") != 0.62:
        raise ClaudeContractError("approved trace scope/cap differs")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", approval["approved_commit"], "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ClaudeContractError("approved commit is not current history")

    qa = {row["question_id"]: row for row in load_jsonl(QA)}
    chunks = {row["chunk_id"]: row for row in load_jsonl(CHUNKS)}
    bm25 = {row["query_id"]: row for row in load_jsonl(BM25)}
    plans = {row["query_id"]: row for row in load_jsonl(PLAN)}
    prompt = PROMPT.read_text(encoding="utf-8")
    requests = {}
    for query_id in freeze["trace_query_ids"]:
        plan = plans[query_id]
        candidates = [
            {"chunk_id": chunk_id, "text": chunks[chunk_id]["text"]}
            for chunk_id in plan["candidate_chunk_ids"]
        ]
        request = build_request(
            query={"query_id": query_id, "question": qa[query_id]["question"]},
            candidates=candidates,
            system_instruction=prompt,
        )
        if request_sha256(request) != plan["request_sha256"]:
            raise ClaudeContractError(f"request reconstruction differs: {query_id}")
        if [row["chunk_id"] for row in bm25[query_id]["results"][:50]] != plan["candidate_chunk_ids"]:
            raise ClaudeContractError(f"BM25 candidates differ: {query_id}")
        requests[query_id] = request
    if OUT.exists() and any(OUT.rglob("*")):
        raise ClaudeContractError("trace output already exists; refusing rerun")
    return {"freeze": freeze, "plans": plans, "requests": requests}


def projection(ledger: dict, remaining: list[str], plans: dict, reserve: float) -> float:
    observed = observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"])
    remaining_input = sum(plans[qid]["input_token_envelope"] for qid in remaining)
    remaining_output = len(remaining) * MAX_OUTPUT_TOKENS
    return observed + reserve + (
        remaining_input * INPUT_USD_PER_MILLION
        + remaining_output * OUTPUT_USD_PER_MILLION
    ) / 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    frozen = preflight()
    if args.preflight:
        print(json.dumps({"status": "ready", "trace_query_ids": list(frozen["requests"])}, indent=2))
        return 0

    environment = {key: value for key, value in dotenv_values(ROOT / ".env").items() if value is not None}
    client = create_client_from_environment(environ=environment)
    sender = make_live_sender(client)
    query_ids = list(frozen["requests"])
    reserve = frozen["freeze"]["ambiguous_dispatch_reserve_usd"]
    cap = frozen["freeze"]["trace_hard_cap_usd"]
    ledger = {
        "status": "ready", "planned_query_ids": query_ids,
        "completed_query_ids": [], "attempt_n": 0, "input_tokens": 0,
        "output_tokens": 0, "observed_cost_usd": 0.0, "hard_cap_usd": cap,
        "automatic_retries": 0,
    }
    write_json(OUT / "ledger.json", ledger, overwrite=False)
    started = time.perf_counter()
    for query_id in query_ids:
        remaining = [value for value in query_ids if value not in ledger["completed_query_ids"]]
        projected = projection(ledger, remaining, frozen["plans"], reserve)
        if projected > cap:
            raise ClaudeContractError(f"projected ${projected:.6f} exceeds trace cap")
        ledger["attempt_n"] += 1
        ledger["status"] = "attempt_counted_before_dispatch"
        write_json(OUT / "ledger.json", ledger, overwrite=True)
        request = frozen["requests"][query_id]
        try:
            response = sender(request)
        except ClaudeProviderError as exc:
            ledger["status"] = "failed_ambiguous_dispatch"
            ledger["failure"] = {"query_id": query_id, "error_class": type(exc).__name__, "http_status": exc.status_code}
            write_json(OUT / "ledger.json", ledger, overwrite=True)
            return 76
        validated = validate_response(
            response,
            expected_chunk_ids=frozen["plans"][query_id]["candidate_chunk_ids"],
        )
        usage = validated["usage"]
        ledger["input_tokens"] += usage["input_tokens"]
        ledger["output_tokens"] += usage["output_tokens"]
        ledger["observed_cost_usd"] = round(
            observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6
        )
        if ledger["observed_cost_usd"] + reserve > cap:
            ledger["status"] = "failed_cost_cap"
            write_json(OUT / "ledger.json", ledger, overwrite=True)
            return 77
        write_json(OUT / "raw" / f"{query_id}.json", validated["raw_response"], overwrite=False)
        write_json(OUT / "rankings" / f"{query_id}.json", {
            "query_id": query_id,
            "request_sha256": frozen["plans"][query_id]["request_sha256"],
            "ranking": validated["ranking"],
            "usage": usage,
        }, overwrite=False)
        ledger["completed_query_ids"].append(query_id)
        ledger["status"] = "running"
        write_json(OUT / "ledger.json", ledger, overwrite=True)

    ledger["status"] = "complete"
    ledger["latency_seconds"] = round(time.perf_counter() - started, 6)
    write_json(OUT / "ledger.json", ledger, overwrite=True)
    artifacts = sorted(path for path in OUT.rglob("*") if path.is_file())
    manifest = {
        "status": "trace_complete",
        "request_n": len(query_ids),
        "valid_n": len(ledger["completed_query_ids"]),
        "retry_n": 0,
        "observed_cost_usd": ledger["observed_cost_usd"],
        "hard_cap_usd": cap,
        "input_tokens": ledger["input_tokens"],
        "output_tokens": ledger["output_tokens"],
        "artifacts": {str(path.relative_to(ROOT)): sha256(path) for path in artifacts},
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(OUT / "trace_summary.json", manifest, overwrite=False)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
