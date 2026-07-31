#!/usr/bin/env python3
"""Freeze, authorize, and execute Prompt-RAG on Phase 8 Option B holdout."""

from __future__ import annotations

import hashlib
import json
import math
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
from src.retrievers.prompt_rag_claude_v1 import make_token_counter  # noqa: E402
from src.retrievers.prompt_rag_phase8_r4_v2 import (  # noqa: E402
    MAX_OUTPUT_TOKENS, build_request, validate_response,
)
from src.utils.atomic_io import stable_json  # noqa: E402

BASE = ROOT / "runs/phase8_option_b_holdout"
FREEZE = BASE / "freeze"
RETRIEVAL = BASE / "retrieval"
PROMPT_FREEZE = BASE / "prompt_rag_freeze"
OUT = BASE / "prompt_rag"
AUDIT = ROOT / "audits/phase8_option_b_holdout"
QA = FREEZE / "qa_holdout_12.jsonl"
QRELS = FREEZE / "qrels_holdout_12.tsv"
CHUNKS = ROOT / "runs/phase8_r4_improvements/corpus/chunks_section_aware_450w.jsonl"
BM25 = RETRIEVAL / "bm25/run.jsonl"
FAISS = RETRIEVAL / "faiss_cosine/run.jsonl"
PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
TRACE_IDS = ["holdout_001", "holdout_008"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in values), encoding="utf-8")


def request_hash(request: dict) -> str:
    return hashlib.sha256(stable_json(request).encode()).hexdigest()


def metric(ranking: list[str], gold: set[str], k: int = 10) -> dict[str, float]:
    top = ranking[:k]
    ranks = [rank for rank, chunk_id in enumerate(top, 1) if chunk_id in gold]
    dcg = sum(1.0 / math.log2(rank + 1) for rank in ranks)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    return {
        "hit@10": float(bool(ranks)),
        "mrr@10": 1.0 / ranks[0] if ranks else 0.0,
        "ndcg@10": dcg / ideal if ideal else 0.0,
        "precision@10": len(ranks) / k,
        "recall@10": len(ranks) / len(gold) if gold else 0.0,
    }


def build_frozen(client) -> dict:
    if PROMPT_FREEZE.exists() and any(PROMPT_FREEZE.iterdir()):
        config = json.loads((PROMPT_FREEZE / "execution_config.json").read_text(encoding="utf-8"))
        plans = {row["query_id"]: row for row in rows(PROMPT_FREEZE / "request_plan.jsonl")}
        return {"config": config, "plans": plans}
    qa = {row["question_id"]: row for row in rows(QA)}
    chunks = {row["chunk_id"]: row for row in rows(CHUNKS)}
    bm25 = {row["query_id"]: row for row in rows(BM25)}
    faiss = {row["query_id"]: row for row in rows(FAISS)}
    prompt = PROMPT.read_text(encoding="utf-8")
    counter = make_token_counter(client)
    plans = []
    for query_id in sorted(qa):
        left = [row["chunk_id"] for row in bm25[query_id]["results"][:25]]
        candidate_ids = left + [row["chunk_id"] for row in faiss[query_id]["results"][:25] if row["chunk_id"] not in set(left)]
        if not 25 <= len(candidate_ids) <= 50:
            raise ClaudeContractError(f"Prompt-RAG candidate union outside 25..50: {query_id}")
        request = build_request(
            query={"query_id": query_id, "question": qa[query_id]["question"]},
            candidates=[{"chunk_id": chunk_id, "text": " ".join(chunks[chunk_id]["text"].split()[:300])} for chunk_id in candidate_ids],
            system_instruction=prompt,
        )
        exact_tokens = counter(request)
        plans.append({
            "candidate_chunk_ids": candidate_ids,
            "exact_input_tokens": exact_tokens,
            "input_token_envelope": exact_tokens + 8,
            "query_id": query_id,
            "request_sha256": request_hash(request),
        })
    input_envelope = sum(row["input_token_envelope"] for row in plans)
    worst = input_envelope / 1_000_000 + len(plans) * MAX_OUTPUT_TOKENS * 5 / 1_000_000
    reserve = max(row["input_token_envelope"] for row in plans) / 1_000_000 + MAX_OUTPUT_TOKENS * 5 / 1_000_000
    hard_cap = round(worst + reserve, 6)
    PROMPT_FREEZE.mkdir(parents=True)
    write_jsonl(PROMPT_FREEZE / "request_plan.jsonl", plans)
    config = {
        "candidate_rule": "BM25 top25 then unseen FAISS top25, deduplicated by chunk_id",
        "candidate_text_rule": "first 300 whitespace-delimited words",
        "input_token_count_method": "Anthropic messages.count_tokens; envelope adds 8 tokens per request",
        "input_token_envelope": input_envelope,
        "input_price_usd_per_million": 1.0,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "model": "claude-haiku-4-5-20251001",
        "output_price_usd_per_million": 5.0,
        "query_n": len(plans),
        "request_plan_sha256": sha(PROMPT_FREEZE / "request_plan.jsonl"),
        "retrieval_hard_cap_usd": hard_cap,
        "retrieval_worst_case_usd": round(worst, 6),
        "schema_version": 1,
        "status": "owner_approved_by_explicit_2026_08_01_instruction",
        "temperature": 0,
        "trace_query_ids": TRACE_IDS,
        "zero_retries": True,
        "inputs": {str(path.relative_to(ROOT)): sha(path) for path in [QA, QRELS, CHUNKS, BM25, FAISS, PROMPT]},
    }
    write_json(PROMPT_FREEZE / "execution_config.json", config)
    write_json(PROMPT_FREEZE / "freeze_manifest.json", {
        "execution_config_sha256": sha(PROMPT_FREEZE / "execution_config.json"),
        "request_plan_sha256": sha(PROMPT_FREEZE / "request_plan.jsonl"),
    })
    write_json(AUDIT / "prompt_rag_approval.json", {
        "approval_scope": "Phase 8 Option B 12-question Prompt-RAG holdout, exact frozen plan, zero retries",
        "authorization_source": "User instruction on 2026-08-01: fix it then run the next step",
        "execution_config_sha256": sha(PROMPT_FREEZE / "execution_config.json"),
        "hard_cap_usd": hard_cap,
        "request_plan_sha256": sha(PROMPT_FREEZE / "request_plan.jsonl"),
        "status": "owner_approved",
    })
    return {"config": config, "plans": {row["query_id"]: row for row in plans}}


def rebuild_requests(frozen: dict) -> dict[str, dict]:
    config, plans = frozen["config"], frozen["plans"]
    if sha(PROMPT_FREEZE / "execution_config.json") != json.loads((AUDIT / "prompt_rag_approval.json").read_text())["execution_config_sha256"]:
        raise ClaudeContractError("Prompt-RAG approval hash mismatch")
    for rel, expected in config["inputs"].items():
        if sha(ROOT / rel) != expected:
            raise ClaudeContractError(f"Protected Prompt-RAG input changed: {rel}")
    qa = {row["question_id"]: row for row in rows(QA)}
    chunks = {row["chunk_id"]: row for row in rows(CHUNKS)}
    prompt = PROMPT.read_text(encoding="utf-8")
    requests = {}
    for query_id, plan in plans.items():
        request = build_request(
            query={"query_id": query_id, "question": qa[query_id]["question"]},
            candidates=[{"chunk_id": chunk_id, "text": " ".join(chunks[chunk_id]["text"].split()[:300])} for chunk_id in plan["candidate_chunk_ids"]],
            system_instruction=prompt,
        )
        if request_hash(request) != plan["request_sha256"]:
            raise ClaudeContractError(f"Prompt-RAG request hash mismatch: {query_id}")
        requests[query_id] = request
    return requests


def projection(ledger: dict, remaining: list[str], plans: dict, reserve: float) -> float:
    future = sum(plans[query_id]["input_token_envelope"] for query_id in remaining)
    return observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]) + future / 1_000_000 + len(remaining) * MAX_OUTPUT_TOKENS * 5 / 1_000_000 + reserve


def main() -> int:
    if OUT.exists() and any(OUT.rglob("*")):
        raise ClaudeContractError("Prompt-RAG holdout output exists; refuse rerun")
    env = {key: value for key, value in dotenv_values(ROOT / ".env").items() if value is not None}
    client = create_client_from_environment(environ=env)
    frozen = build_frozen(client)
    requests = rebuild_requests(frozen)
    sender = make_live_sender(client)
    plans, config = frozen["plans"], frozen["config"]
    reserve = max(row["input_token_envelope"] for row in plans.values()) / 1_000_000 + MAX_OUTPUT_TOKENS * 5 / 1_000_000
    ordered = TRACE_IDS + [query_id for query_id in sorted(requests) if query_id not in TRACE_IDS]
    ledger = {"attempt_n": 0, "completed_query_ids": [], "input_tokens": 0, "output_tokens": 0, "observed_cost_usd": 0.0, "status": "ready", "zero_retries": True}
    write_json(OUT / "ledger.json", ledger)
    ranking_rows = []
    for query_id in ordered:
        remaining = [item for item in ordered if item not in ledger["completed_query_ids"]]
        if projection(ledger, remaining, plans, reserve) > config["retrieval_hard_cap_usd"]:
            raise ClaudeContractError("Projected Prompt-RAG cost exceeds frozen hard cap")
        ledger["attempt_n"] += 1
        ledger["status"] = "attempt_counted_before_dispatch"
        write_json(OUT / "ledger.json", ledger)
        started = time.perf_counter()
        try:
            response = sender(requests[query_id])
        except ClaudeProviderError as exc:
            ledger.update(status="failed_terminal_provider", failed_query_id=query_id, provider_status=exc.status_code)
            write_json(OUT / "ledger.json", ledger)
            return 76
        latency = time.perf_counter() - started
        valid = validate_response(response, plans[query_id]["candidate_chunk_ids"])
        usage = valid["usage"]
        ledger["input_tokens"] += usage["input_tokens"]
        ledger["output_tokens"] += usage["output_tokens"]
        ledger["observed_cost_usd"] = round(observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6)
        if ledger["observed_cost_usd"] + reserve > config["retrieval_hard_cap_usd"]:
            raise ClaudeContractError("Observed Prompt-RAG cost exceeds frozen hard cap")
        write_json(OUT / "raw" / f"{query_id}.json", valid["raw_response"])
        row = {
            "latency_seconds": round(latency, 6),
            "query_id": query_id,
            "request_sha256": plans[query_id]["request_sha256"],
            "results": valid["ranking"],
            "retriever": "prompt_rag_claude",
            "top_k": len(valid["ranking"]),
            "usage": usage,
        }
        write_json(OUT / "rankings" / f"{query_id}.json", row)
        ranking_rows.append(row)
        ledger["completed_query_ids"].append(query_id)
        ledger["status"] = "running"
        write_json(OUT / "ledger.json", ledger)
    ledger["status"] = "complete"
    write_json(OUT / "ledger.json", ledger)
    ranking_rows.sort(key=lambda row: row["query_id"])
    write_jsonl(OUT / "run.jsonl", ranking_rows)

    gold: dict[str, set[str]] = {}
    for line in QRELS.read_text(encoding="utf-8").splitlines():
        query_id, _, chunk_id, relevance = line.split("\t")
        if int(relevance) > 0:
            gold.setdefault(query_id, set()).add(chunk_id)
    per_query = [{"query_id": row["query_id"], "system": "prompt_rag_claude", **metric([item["chunk_id"] for item in row["results"]], gold[row["query_id"]])} for row in ranking_rows]
    keys = ["mrr@10", "recall@10", "precision@10", "ndcg@10", "hit@10"]
    aggregate = {key: sum(row[key] for row in per_query) / len(per_query) for key in keys}
    write_json(OUT / "metrics.json", {"metrics": aggregate, "per_query": per_query})
    write_json(OUT / "summary.json", {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "cost_usd": ledger["observed_cost_usd"],
        "coverage": "12/12",
        "input_tokens": ledger["input_tokens"],
        "metrics": aggregate,
        "output_tokens": ledger["output_tokens"],
        "retry_n": 0,
        "status": "complete",
    })
    print(json.dumps(json.loads((OUT / "summary.json").read_text()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
