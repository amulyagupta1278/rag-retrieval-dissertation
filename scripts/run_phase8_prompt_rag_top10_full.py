#!/usr/bin/env python3
"""Execute approved 95-request Phase 8 Prompt-RAG top-10 full run."""

from __future__ import annotations

import argparse
import csv
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
from src.evaluation.evaluator import RetrievalEvaluator  # noqa: E402
from src.retrievers.prompt_rag_claude_v2 import (  # noqa: E402
    ClaudeContractError, ClaudeProviderError, create_client_from_environment,
    make_live_sender, observed_cost_usd,
)
from src.retrievers.prompt_rag_phase8_top10 import (  # noqa: E402
    MAX_OUTPUT_TOKENS, build_request, validate_response,
)
from src.utils.atomic_io import stable_json, write_json  # noqa: E402
from src.utils.io_utils import load_jsonl, save_jsonl  # noqa: E402


BASE = ROOT / "runs/phase8_exploratory_five_system"
CONFIG = BASE / "cost_safe_amendment/execution_config.json"
PLAN = BASE / "cost_safe_amendment/prompt_rag_top10_request_plan.jsonl"
TRACE = BASE / "prompt_rag_top10_trace"
APPROVAL = ROOT / "audits/phase8_exploratory/cost_safe_prompt_rag_full_approval.json"
QA = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qa_dataset.jsonl"
QRELS = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qrels_gold.tsv"
CATEGORIES = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/query_categories.json"
CHUNKS = ROOT / "releases/v3_clean/data/chunks/chunks_v3_clean.jsonl"
BM25 = BASE / "bm25_top50/retrieval/bm25_run.jsonl"
PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
OUT = BASE / "prompt_rag_top10_full"


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
    config, approval, trace_summary = obj(CONFIG), obj(APPROVAL), obj(TRACE / "trace_summary.json")
    rerank = config["prompt_rag"]
    if approval.get("status") != "owner_approved" or approval.get("execution_config_sha256") != sha(CONFIG):
        raise ClaudeContractError("full approval config differs")
    if approval.get("request_plan_sha256") != sha(PLAN) or approval.get("trace_summary_sha256") != sha(TRACE / "trace_summary.json"):
        raise ClaudeContractError("full approval plan/trace differs")
    if approval.get("remaining_request_n") != 95 or approval.get("trace_reuse_n") != 5:
        raise ClaudeContractError("full approval scope differs")
    if approval.get("cumulative_hard_cap_usd") != rerank["full_hard_cap_usd"]:
        raise ClaudeContractError("full approval cap differs")
    if trace_summary.get("status") != "trace_complete" or trace_summary.get("valid_n") != 5:
        raise ClaudeContractError("trace not reusable")
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
    for query_id in sorted(qa):
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

    trace_rankings = {}
    for query_id in rerank["trace_query_ids"]:
        row = obj(TRACE / "rankings" / f"{query_id}.json")
        if row.get("request_sha256") != plans[query_id]["request_sha256"]:
            raise ClaudeContractError(f"trace reuse hash differs: {query_id}")
        trace_rankings[query_id] = row
    if OUT.exists() and any(OUT.rglob("*")):
        raise ClaudeContractError("full output exists; refusing rerun")
    return {
        "config": config, "qa": qa, "chunks": chunks, "bm25": bm25,
        "plans": plans, "requests": requests, "trace_rankings": trace_rankings,
        "trace_summary": trace_summary,
    }


def projection(ledger: dict, remaining: list[str], plans: dict, reserve: float) -> float:
    observed = observed_cost_usd(ledger["cumulative_input_tokens"], ledger["cumulative_output_tokens"])
    future_input = sum(plans[qid]["input_token_envelope"] for qid in remaining)
    return observed + reserve + future_input / 1_000_000 + len(remaining) * MAX_OUTPUT_TOKENS * 5 / 1_000_000


def aggregate_metrics(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        row = next(row for row in csv.DictReader(handle) if row["query_category"] == "all")
    return {key: float(row[key]) for key in ("mrr@10", "recall@10", "ndcg@10", "precision@10")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    frozen = preflight()
    trace_ids = set(frozen["trace_rankings"])
    remaining_ids = [qid for qid in sorted(frozen["requests"]) if qid not in trace_ids]
    if args.preflight:
        initial = {
            "cumulative_input_tokens": frozen["trace_summary"]["input_tokens"],
            "cumulative_output_tokens": frozen["trace_summary"]["output_tokens"],
        }
        projected = projection(initial, remaining_ids, frozen["plans"], frozen["config"]["prompt_rag"]["ambiguous_dispatch_reserve_usd"])
        print(json.dumps({"status": "ready", "trace_reuse_n": 5, "remaining_n": 95, "projected_cumulative_usd": round(projected, 6)}, indent=2))
        return 0

    env = {key: value for key, value in dotenv_values(ROOT / ".env").items() if value is not None}
    sender = make_live_sender(create_client_from_environment(environ=env))
    rerank = frozen["config"]["prompt_rag"]
    reserve, cap = rerank["ambiguous_dispatch_reserve_usd"], rerank["full_hard_cap_usd"]
    ledger = {
        "status": "ready", "planned_new_query_ids": remaining_ids,
        "completed_new_query_ids": [], "trace_reuse_query_ids": sorted(trace_ids),
        "new_attempt_n": 0, "new_input_tokens": 0, "new_output_tokens": 0,
        "trace_input_tokens": frozen["trace_summary"]["input_tokens"],
        "trace_output_tokens": frozen["trace_summary"]["output_tokens"],
        "cumulative_input_tokens": frozen["trace_summary"]["input_tokens"],
        "cumulative_output_tokens": frozen["trace_summary"]["output_tokens"],
        "cumulative_observed_cost_usd": frozen["trace_summary"]["observed_cost_usd"],
        "cumulative_hard_cap_usd": cap, "automatic_retries": 0,
    }
    write_json(OUT / "ledger.json", ledger, overwrite=False)
    started = time.perf_counter()
    for query_id in remaining_ids:
        pending = [qid for qid in remaining_ids if qid not in ledger["completed_new_query_ids"]]
        if projection(ledger, pending, frozen["plans"], reserve) > cap:
            raise ClaudeContractError("projected cumulative exposure exceeds hard cap")
        ledger["new_attempt_n"] += 1
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
        ledger["new_input_tokens"] += usage["input_tokens"]
        ledger["new_output_tokens"] += usage["output_tokens"]
        ledger["cumulative_input_tokens"] += usage["input_tokens"]
        ledger["cumulative_output_tokens"] += usage["output_tokens"]
        ledger["cumulative_observed_cost_usd"] = round(observed_cost_usd(ledger["cumulative_input_tokens"], ledger["cumulative_output_tokens"]), 6)
        if ledger["cumulative_observed_cost_usd"] + reserve > cap:
            ledger["status"] = "failed_cost_cap"
            write_json(OUT / "ledger.json", ledger, overwrite=True)
            return 77
        write_json(OUT / "raw" / f"{query_id}.json", validated["raw_response"], overwrite=False)
        write_json(OUT / "rankings" / f"{query_id}.json", {
            "query_id": query_id, "ranking": validated["ranking"], "usage": usage,
            "request_sha256": frozen["plans"][query_id]["request_sha256"],
        }, overwrite=False)
        ledger["completed_new_query_ids"].append(query_id)
        ledger["status"] = "running"
        write_json(OUT / "ledger.json", ledger, overwrite=True)

    ranking_rows = {**frozen["trace_rankings"]}
    ranking_rows.update({qid: obj(OUT / "rankings" / f"{qid}.json") for qid in remaining_ids})
    runs = []
    for query_id in sorted(ranking_rows):
        candidate_map = {row["chunk_id"]: row for row in frozen["bm25"][query_id]["results"][:10]}
        results = []
        for scored in ranking_rows[query_id]["ranking"]:
            result = dict(candidate_map[scored["chunk_id"]])
            result.update({"rank": scored["rank"], "score": scored["score"], "retriever": "prompt_rag_top10"})
            results.append(result)
        runs.append({
            "query_id": query_id, "query_text": frozen["qa"][query_id]["question"],
            "retriever": "prompt_rag_top10", "top_k": 10,
            "total_latency_ms": 0.0, "results": results,
            "config_snapshot": {"variant": "phase8_cost_adapted", "candidate_depth": 10, "trace_reused": query_id in trace_ids},
        })
    run_path = OUT / "retrieval/prompt_rag_top10_run.jsonl"
    save_jsonl(runs, run_path)
    evaluator = RetrievalEvaluator(QRELS, CATEGORIES, qa_dataset_path=QA, chunks_path=CHUNKS)
    bundles = evaluator.evaluate_run_file(run_path, retriever_name="prompt_rag_top10")
    metrics_path = OUT / "metrics/prompt_rag_top10_metrics.csv"
    evaluator.save_metrics_csv(bundles, metrics_path)
    ledger["status"] = "complete"
    ledger["latency_seconds_new_95"] = round(time.perf_counter() - started, 6)
    write_json(OUT / "ledger.json", ledger, overwrite=True)
    artifacts = sorted(path for path in OUT.rglob("*") if path.is_file())
    summary = {
        "status": "full_complete", "coverage_n": 100, "trace_reuse_n": 5,
        "new_request_n": 95, "valid_n": 100, "failure_n": 0, "retry_n": 0,
        "new_input_tokens": ledger["new_input_tokens"], "new_output_tokens": ledger["new_output_tokens"],
        "cumulative_input_tokens": ledger["cumulative_input_tokens"],
        "cumulative_output_tokens": ledger["cumulative_output_tokens"],
        "cumulative_observed_cost_usd": ledger["cumulative_observed_cost_usd"],
        "cumulative_hard_cap_usd": cap, "metrics": aggregate_metrics(metrics_path),
        "generation_calls": 0,
        "artifacts": {str(path.relative_to(ROOT)): sha(path) for path in artifacts},
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(OUT / "full_summary.json", summary, overwrite=False)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
