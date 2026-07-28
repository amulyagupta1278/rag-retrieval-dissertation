#!/usr/bin/env python3
"""Execute approved Phase 8 cost-adapted Prompt-RAG top-10 trace once."""

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
    ClaudeContractError, ClaudeProviderError, create_client_from_environment,
    make_live_sender, observed_cost_usd,
)
from src.retrievers.prompt_rag_phase8_top10 import (  # noqa: E402
    MAX_OUTPUT_TOKENS, build_request, validate_response,
)
from src.utils.atomic_io import stable_json, write_json  # noqa: E402
from src.utils.io_utils import load_jsonl  # noqa: E402


BASE = ROOT / "runs/phase8_exploratory_five_system"
CONFIG = BASE / "cost_safe_amendment/execution_config.json"
PLAN = BASE / "cost_safe_amendment/prompt_rag_top10_request_plan.jsonl"
APPROVAL = ROOT / "audits/phase8_exploratory/cost_safe_prompt_rag_trace_approval.json"
QA = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qa_dataset.jsonl"
CHUNKS = ROOT / "releases/v3_clean/data/chunks/chunks_v3_clean.jsonl"
BM25 = BASE / "bm25_top50/retrieval/bm25_run.jsonl"
PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
OUT = BASE / "prompt_rag_top10_trace"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def obj(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ClaudeContractError(f"object required: {path.relative_to(ROOT)}")
    return value


def request_hash(request: dict) -> str:
    return hashlib.sha256(stable_json(request).encode()).hexdigest()


def preflight() -> dict:
    config, approval = obj(CONFIG), obj(APPROVAL)
    rerank = config["prompt_rag"]
    if config["status"] != "offline_frozen_pending_owner_prompt_rag_trace_approval":
        raise ClaudeContractError("cost-safe amendment status differs")
    if approval.get("status") != "owner_approved" or approval.get("execution_config_sha256") != sha(CONFIG):
        raise ClaudeContractError("approved config differs")
    if approval.get("request_plan_sha256") != sha(PLAN) or approval.get("hard_cap_usd") != 0.15:
        raise ClaudeContractError("approved plan/cap differs")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", approval["approved_commit"], "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ClaudeContractError("approved commit not current history")
    qa = {row["question_id"]: row for row in load_jsonl(QA)}
    chunks = {row["chunk_id"]: row for row in load_jsonl(CHUNKS)}
    bm25 = {row["query_id"]: row for row in load_jsonl(BM25)}
    plans = {row["query_id"]: row for row in load_jsonl(PLAN)}
    prompt = PROMPT.read_text(encoding="utf-8")
    requests = {}
    for query_id in rerank["trace_query_ids"]:
        plan = plans[query_id]
        ids = plan["candidate_chunk_ids"]
        if ids != [row["chunk_id"] for row in bm25[query_id]["results"][:10]]:
            raise ClaudeContractError(f"candidate order differs: {query_id}")
        request = build_request(
            query={"query_id": query_id, "question": qa[query_id]["question"]},
            candidates=[{"chunk_id": cid, "text": chunks[cid]["text"]} for cid in ids],
            system_instruction=prompt,
        )
        if request_hash(request) != plan["request_sha256"]:
            raise ClaudeContractError(f"request hash differs: {query_id}")
        requests[query_id] = request
    if OUT.exists() and any(OUT.rglob("*")):
        raise ClaudeContractError("top-10 trace output exists; refusing rerun")
    return {"config": config, "plans": plans, "requests": requests}


def projected(ledger: dict, remaining: list[str], plans: dict, reserve: float) -> float:
    observed = observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"])
    future_input = sum(plans[qid]["input_token_envelope"] for qid in remaining)
    return observed + reserve + future_input / 1_000_000 + len(remaining) * MAX_OUTPUT_TOKENS * 5 / 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    frozen = preflight()
    query_ids = list(frozen["requests"])
    if args.preflight:
        print(json.dumps({"status": "ready", "trace_query_ids": query_ids}, indent=2))
        return 0
    env = {key: value for key, value in dotenv_values(ROOT / ".env").items() if value is not None}
    sender = make_live_sender(create_client_from_environment(environ=env))
    rerank = frozen["config"]["prompt_rag"]
    reserve, cap = rerank["ambiguous_dispatch_reserve_usd"], rerank["trace_hard_cap_usd"]
    ledger = {
        "status": "ready", "planned_query_ids": query_ids, "completed_query_ids": [],
        "attempt_n": 0, "input_tokens": 0, "output_tokens": 0,
        "observed_cost_usd": 0.0, "hard_cap_usd": cap, "automatic_retries": 0,
    }
    write_json(OUT / "ledger.json", ledger, overwrite=False)
    started = time.perf_counter()
    for query_id in query_ids:
        remaining = [qid for qid in query_ids if qid not in ledger["completed_query_ids"]]
        if projected(ledger, remaining, frozen["plans"], reserve) > cap:
            raise ClaudeContractError("projected trace exposure exceeds hard cap")
        ledger["attempt_n"] += 1
        ledger["status"] = "attempt_counted_before_dispatch"
        write_json(OUT / "ledger.json", ledger, overwrite=True)
        try:
            response = sender(frozen["requests"][query_id])
        except ClaudeProviderError as exc:
            ledger["status"] = "failed_ambiguous_dispatch"
            ledger["failure"] = {"query_id": query_id, "error_class": type(exc).__name__, "http_status": exc.status_code}
            write_json(OUT / "ledger.json", ledger, overwrite=True)
            return 76
        validated = validate_response(response, frozen["plans"][query_id]["candidate_chunk_ids"])
        usage = validated["usage"]
        ledger["input_tokens"] += usage["input_tokens"]
        ledger["output_tokens"] += usage["output_tokens"]
        ledger["observed_cost_usd"] = round(observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6)
        if ledger["observed_cost_usd"] + reserve > cap:
            ledger["status"] = "failed_cost_cap"
            write_json(OUT / "ledger.json", ledger, overwrite=True)
            return 77
        write_json(OUT / "raw" / f"{query_id}.json", validated["raw_response"], overwrite=False)
        write_json(OUT / "rankings" / f"{query_id}.json", {
            "query_id": query_id, "ranking": validated["ranking"], "usage": usage,
            "request_sha256": frozen["plans"][query_id]["request_sha256"],
        }, overwrite=False)
        ledger["completed_query_ids"].append(query_id)
        ledger["status"] = "running"
        write_json(OUT / "ledger.json", ledger, overwrite=True)
    ledger["status"] = "complete"
    ledger["latency_seconds"] = round(time.perf_counter() - started, 6)
    write_json(OUT / "ledger.json", ledger, overwrite=True)
    artifacts = sorted(path for path in OUT.rglob("*") if path.is_file())
    summary = {
        "status": "trace_complete", "request_n": 5, "valid_n": 5, "retry_n": 0,
        "input_tokens": ledger["input_tokens"], "output_tokens": ledger["output_tokens"],
        "observed_cost_usd": ledger["observed_cost_usd"], "hard_cap_usd": cap,
        "artifacts": {str(path.relative_to(ROOT)): sha(path) for path in artifacts},
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(OUT / "trace_summary.json", summary, overwrite=False)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
