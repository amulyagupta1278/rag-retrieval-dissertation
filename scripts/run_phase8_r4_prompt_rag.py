#!/usr/bin/env python3
"""Run approved R4 Prompt-RAG V2 recovery after preserved V1 failure."""

from __future__ import annotations

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
from src.retrievers.prompt_rag_phase8_r4_v2 import MAX_OUTPUT_TOKENS, build_request, validate_response  # noqa: E402
from src.utils.atomic_io import stable_json, write_json  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
FREEZE = BASE / "prompt_rag_r4_v2_freeze"
CONFIG = FREEZE / "execution_config.json"
PLAN = FREEZE / "request_plan.jsonl"
APPROVAL = ROOT / "audits/phase8_r4/prompt_rag_v2_owner_approval.json"
QA = BASE / "benchmark/qa_dev_test.jsonl"
CHUNKS = BASE / "corpus/chunks_section_aware_450w.jsonl"
BM25 = BASE / "retrieval/bm25_section_aware_run.jsonl"
FAISS = BASE / "retrieval/faiss_cosine/faiss_run.jsonl"
PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
TRACE = BASE / "prompt_rag_r4_v2_trace"
FULL = BASE / "prompt_rag_r4_v2_full"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def obj(path: Path) -> dict:
    return json.loads(path.read_text())


def req_hash(request: dict) -> str:
    return hashlib.sha256(stable_json(request).encode()).hexdigest()


def preflight() -> dict:
    config, approval = obj(CONFIG), obj(APPROVAL)
    if config["status"] != "frozen_pending_owner_approval" or approval["status"] != "owner_approved":
        raise ClaudeContractError("R4 approval status differs")
    if approval["execution_config_sha256"] != sha(CONFIG) or approval["request_plan_sha256"] != sha(PLAN):
        raise ClaudeContractError("R4 approved hashes differ")
    if config["total_additional_r4_hard_cap_usd"] != 3.70 or config["zero_retries"] is not True or config["max_output_tokens"] != 1024:
        raise ClaudeContractError("R4 cap/failure policy differs")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", config["approved_base_commit"], "HEAD"], cwd=ROOT)
    if result.returncode:
        raise ClaudeContractError("approved base commit not in history")
    for rel, expected in config["inputs"].items():
        if sha(ROOT / rel) != expected:
            raise ClaudeContractError(f"protected input differs: {rel}")
    plans = {p["query_id"]: p for p in load(PLAN)}
    qa = {r["question_id"]: r for r in load(QA)}
    chunks = {r["chunk_id"]: r for r in load(CHUNKS)}
    bm25 = {r["query_id"]: r for r in load(BM25)}
    faiss = {r["query_id"]: r for r in load(FAISS)}
    prompt = PROMPT.read_text()
    requests = {}
    for qid in sorted(plans):
        left = [r["chunk_id"] for r in bm25[qid]["results"][:25]]
        ids = left + [r["chunk_id"] for r in faiss[qid]["results"][:25] if r["chunk_id"] not in set(left)]
        if ids != plans[qid]["candidate_chunk_ids"]:
            raise ClaudeContractError(f"R4 union differs: {qid}")
        request = build_request(query={"query_id": qid, "question": qa[qid]["question"]}, candidates=[{"chunk_id": cid, "text": " ".join(chunks[cid]["text"].split()[:300])} for cid in ids], system_instruction=prompt)
        if req_hash(request) != plans[qid]["request_sha256"]:
            raise ClaudeContractError(f"R4 request hash differs: {qid}")
        requests[qid] = request
    if any(path.exists() and any(path.rglob("*")) for path in (TRACE, FULL)):
        raise ClaudeContractError("R4 output exists; refusing rerun")
    return {"config": config, "plans": plans, "requests": requests}


def projection(ledger: dict, query_ids: list[str], plans: dict, reserve: float) -> float:
    future_input = sum(plans[q]["input_token_envelope"] for q in query_ids)
    return observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]) + reserve + future_input / 1e6 + len(query_ids) * MAX_OUTPUT_TOKENS * 5 / 1e6


def dispatch(sender, frozen: dict, query_ids: list[str], out: Path, ledger: dict) -> bool:
    config, plans = frozen["config"], frozen["plans"]
    reserve, cap = config["ambiguous_dispatch_reserve_usd"], config["retrieval_hard_cap_usd"]
    write_json(out / "ledger.json", ledger, overwrite=False)
    for qid in query_ids:
        remaining = [x for x in query_ids if x not in ledger["completed_query_ids"]]
        if projection(ledger, remaining, plans, reserve) > cap:
            ledger.update(status="failed_projected_cost_cap", failed_query_id=qid)
            write_json(out / "ledger.json", ledger, overwrite=True)
            return False
        ledger.update(status="attempt_counted_before_dispatch", attempt_n=ledger["attempt_n"] + 1)
        write_json(out / "ledger.json", ledger, overwrite=True)
        started = time.perf_counter()
        try:
            response = sender(frozen["requests"][qid])
        except ClaudeProviderError as exc:
            ledger.update(status="failed_ambiguous_dispatch", failure={"query_id": qid, "error_class": type(exc).__name__, "http_status": exc.status_code})
            write_json(out / "ledger.json", ledger, overwrite=True)
            return False
        latency = time.perf_counter() - started
        try:
            valid = validate_response(response, plans[qid]["candidate_chunk_ids"])
        except ClaudeContractError as exc:
            ledger.update(status="failed_terminal_validation", failure={"query_id": qid, "error": str(exc)})
            write_json(out / "ledger.json", ledger, overwrite=True)
            return False
        usage = valid["usage"]
        ledger["input_tokens"] += usage["input_tokens"]
        ledger["output_tokens"] += usage["output_tokens"]
        ledger["observed_cost_usd"] = round(observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6)
        if ledger["observed_cost_usd"] + reserve > cap:
            ledger.update(status="failed_observed_cost_cap", failed_query_id=qid)
            write_json(out / "ledger.json", ledger, overwrite=True)
            return False
        write_json(out / "raw" / f"{qid}.json", valid["raw_response"], overwrite=False)
        write_json(out / "rankings" / f"{qid}.json", {"query_id": qid, "request_sha256": plans[qid]["request_sha256"], "ranking": valid["ranking"], "usage": usage, "latency_seconds": round(latency, 6)}, overwrite=False)
        ledger["completed_query_ids"].append(qid)
        ledger["latencies_seconds"].append(round(latency, 6))
        ledger["status"] = "running"
        write_json(out / "ledger.json", ledger, overwrite=True)
    ledger["status"] = "complete"
    write_json(out / "ledger.json", ledger, overwrite=True)
    return True


def main() -> int:
    frozen = preflight()
    env = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    sender = make_live_sender(create_client_from_environment(environ=env))
    trace_ids = frozen["config"]["trace_query_ids"]
    ledger = {"status": "ready", "attempt_n": 0, "completed_query_ids": [], "input_tokens": 0, "output_tokens": 0, "observed_cost_usd": 0.0, "automatic_retries": 0, "latencies_seconds": []}
    if not dispatch(sender, frozen, trace_ids, TRACE, ledger):
        return 76
    trace_summary = {"status": "trace_complete", "valid_n": 5, "request_n": 5, "retry_n": 0, "cost_usd": ledger["observed_cost_usd"], "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(TRACE / "summary.json", trace_summary, overwrite=False)
    remaining = [q for q in sorted(frozen["requests"]) if q not in set(trace_ids)]
    if projection(ledger, remaining, frozen["plans"], frozen["config"]["ambiguous_dispatch_reserve_usd"]) > frozen["config"]["retrieval_hard_cap_usd"]:
        return 77
    full_ledger = {**ledger, "status": "ready", "reused_trace_query_ids": trace_ids}
    if not dispatch(sender, frozen, remaining, FULL, full_ledger):
        return 78
    rows = []
    for qid in sorted(frozen["requests"]):
        source = TRACE if qid in trace_ids else FULL
        row = obj(source / "rankings" / f"{qid}.json")
        rows.append({"query_id": qid, "retriever": "prompt_rag_claude_mixed_bm25_faiss_r4", "top_k": len(row["ranking"]), "results": row["ranking"], "latency_seconds": row["latency_seconds"], "request_sha256": row["request_sha256"]})
    run = FULL / "prompt_rag_run.jsonl"
    run.write_text("".join(stable_json(r) + "\n" for r in rows), encoding="utf-8")
    summary = {"status": "full_complete", "coverage": "100/100", "trace_reused": 5, "new_full_calls": 95, "retry_n": 0, "failure_n": 0, "input_tokens": full_ledger["input_tokens"], "output_tokens": full_ledger["output_tokens"], "cost_usd": full_ledger["observed_cost_usd"], "mean_latency_seconds": round(sum(full_ledger["latencies_seconds"]) / 100, 6), "run_sha256": sha(run), "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(FULL / "summary.json", summary, overwrite=False)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
