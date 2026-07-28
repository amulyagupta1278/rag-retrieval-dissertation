#!/usr/bin/env python3
"""Freeze top-10 Prompt-RAG and 100-call generation sampling amendment."""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase7_context import serialize_context  # noqa: E402
from src.retrievers.prompt_rag_claude_v2 import INPUT_USD_PER_MILLION, OUTPUT_USD_PER_MILLION  # noqa: E402
from src.retrievers.prompt_rag_phase8_top10 import (  # noqa: E402
    MAX_OUTPUT_TOKENS as RERANK_MAX_OUTPUT,
    build_request as build_rerank_request,
)
from src.utils.atomic_io import stable_json  # noqa: E402
from src.utils.io_utils import load_jsonl  # noqa: E402


BASE = ROOT / "runs/phase8_exploratory_five_system"
QA = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qa_dataset.jsonl"
CHUNKS = ROOT / "releases/v3_clean/data/chunks/chunks_v3_clean.jsonl"
PROMPT_RAG_PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
GEN_PROMPT = ROOT / "prompts/phase7_answer_generation_v1.txt"
GEN_SCHEMA = ROOT / "runs/v2/phase7_generation_claude_top3_v2/response_schema.json"
OUT = BASE / "cost_safe_amendment"
AUDIT = ROOT / "audits/phase8_exploratory/cost_safe_amendment.json"
MODEL = "claude-haiku-4-5-20251001"
RERANK_TRACE_N = 5
RERANK_TRACE_CAP = 0.15
RERANK_FULL_CAP = 2.25
GEN_MAX_OUTPUT = 512
GEN_HARD_CAP = 1.25


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(request: dict) -> int:
    return math.ceil(len(stable_json(request).encode("utf-8")) / 2) + 256


def main() -> int:
    qa_rows = load_jsonl(QA)
    qa = {row["question_id"]: row for row in qa_rows}
    chunks = {row["chunk_id"]: row for row in load_jsonl(CHUNKS)}
    bm25_rows = load_jsonl(BASE / "bm25_top50/retrieval/bm25_run.jsonl")
    bm25 = {row["query_id"]: row for row in bm25_rows}
    prompt = PROMPT_RAG_PROMPT.read_text(encoding="utf-8")

    rerank_plan = []
    for query_id in sorted(qa):
        ids = [row["chunk_id"] for row in bm25[query_id]["results"][:10]]
        request = build_rerank_request(
            query={"query_id": query_id, "question": qa[query_id]["question"]},
            candidates=[{"chunk_id": chunk_id, "text": chunks[chunk_id]["text"]} for chunk_id in ids],
            system_instruction=prompt,
        )
        rerank_plan.append({
            "query_id": query_id, "candidate_chunk_ids": ids,
            "request_sha256": hashlib.sha256(stable_json(request).encode()).hexdigest(),
            "input_token_envelope": envelope(request),
        })
    trace = sorted(rerank_plan, key=lambda row: (-row["input_token_envelope"], row["query_id"]))[:RERANK_TRACE_N]
    rerank_input = sum(row["input_token_envelope"] for row in rerank_plan)
    rerank_reserve = max(row["input_token_envelope"] for row in rerank_plan) / 1e6 + RERANK_MAX_OUTPUT * 5 / 1e6
    rerank_worst = rerank_input / 1e6 + len(rerank_plan) * RERANK_MAX_OUTPUT * 5 / 1e6
    trace_worst = sum(row["input_token_envelope"] for row in trace) / 1e6 + RERANK_TRACE_N * RERANK_MAX_OUTPUT * 5 / 1e6 + rerank_reserve

    by_category: dict[str, list[str]] = defaultdict(list)
    for row in qa_rows:
        by_category[row["category"]].append(row["question_id"])
    rng = random.Random(42)
    selected = sorted(qid for category in sorted(by_category) for qid in rng.sample(sorted(by_category[category]), 4))
    if len(selected) != 20:
        raise RuntimeError("generation sample must contain 20 questions")

    run_paths = {
        "bm25": BASE / "bm25_top50/retrieval/bm25_run.jsonl",
        "faiss": ROOT / "runs/phase8_exploratory_automated_r3/results/retrieval/faiss_run.jsonl",
        "graphrag": BASE / "graph_top50/retrieval/graphrag_run.jsonl",
        "hybrid_rrf": BASE / "hybrid_rrf/retrieval/hybrid_rrf_run.jsonl",
    }
    indexed = {name: {row["query_id"]: row for row in load_jsonl(path)} for name, path in run_paths.items()}
    gen_prompt = GEN_PROMPT.read_text(encoding="utf-8")
    gen_schema = json.loads(GEN_SCHEMA.read_text(encoding="utf-8"))
    generation_plan = []
    for query_id in selected:
        system_ids = {
            name: [result["chunk_id"] for result in rows[query_id]["results"][:3]]
            for name, rows in indexed.items()
        }
        # Prompt-RAG output is unknown. Budget its three largest BM25-top10 chunks.
        top10 = [row["chunk_id"] for row in bm25[query_id]["results"][:10]]
        system_ids["prompt_rag_top10"] = sorted(top10, key=lambda cid: (-len(chunks[cid]["text"].encode()), cid))[:3]
        for system, ids in sorted(system_ids.items()):
            context, _ = serialize_context(qa[query_id]["question"], ids, {cid: row["text"] for cid, row in chunks.items()}, 3)
            request = {
                "max_tokens": GEN_MAX_OUTPUT,
                "messages": [{"content": context, "role": "user"}],
                "model": MODEL,
                "output_config": {"format": {"schema": gen_schema, "type": "json_schema"}},
                "service_tier": "standard_only", "stream": False,
                "system": gen_prompt, "temperature": 0, "tools": [],
            }
            generation_plan.append({
                "query_id": query_id, "system": system,
                "context_chunk_ids": ids,
                "input_token_envelope": envelope(request),
            })
    gen_input = sum(row["input_token_envelope"] for row in generation_plan)
    gen_reserve = max(row["input_token_envelope"] for row in generation_plan) / 1e6 + GEN_MAX_OUTPUT * 5 / 1e6
    gen_worst = gen_input / 1e6 + len(generation_plan) * GEN_MAX_OUTPUT * 5 / 1e6
    if trace_worst > RERANK_TRACE_CAP or rerank_worst + rerank_reserve > RERANK_FULL_CAP or gen_worst + gen_reserve > GEN_HARD_CAP:
        raise RuntimeError("cost-safe hard cap insufficient")

    OUT.mkdir(parents=True, exist_ok=True)
    rerank_path = OUT / "prompt_rag_top10_request_plan.jsonl"
    rerank_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rerank_plan), encoding="utf-8")
    gen_path = OUT / "generation_20x5_plan.jsonl"
    gen_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in generation_plan), encoding="utf-8")
    config = {
        "status": "offline_frozen_pending_owner_prompt_rag_trace_approval",
        "variant": "phase8_cost_adapted_not_pilot_top50_replication",
        "prompt_rag": {
            "candidate_depth": 10, "query_n": 100, "request_n": 100,
            "trace_n": RERANK_TRACE_N, "trace_query_ids": [row["query_id"] for row in trace],
            "input_token_envelope": rerank_input,
            "trace_worst_case_including_reserve_usd": round(trace_worst, 6),
            "trace_hard_cap_usd": RERANK_TRACE_CAP,
            "full_worst_case_usd": round(rerank_worst, 6),
            "ambiguous_dispatch_reserve_usd": round(rerank_reserve, 6),
            "full_hard_cap_usd": RERANK_FULL_CAP,
            "request_plan_sha256": sha(rerank_path),
        },
        "generation": {
            "sample_seed": 42, "sampling": "4 questions per each of 5 categories",
            "query_ids": selected, "query_n": 20, "system_n": 5, "request_n": 100,
            "input_token_envelope": gen_input,
            "worst_case_usd": round(gen_worst, 6),
            "ambiguous_dispatch_reserve_usd": round(gen_reserve, 6),
            "hard_cap_usd": GEN_HARD_CAP,
            "plan_sha256": sha(gen_path),
            "execution_authorized": False,
        },
        "prior_phase8_trace_spend_usd": 0.224985,
        "owner_reported_initial_balance_usd": 5.0,
        "combined_new_hard_caps_usd": RERANK_FULL_CAP + GEN_HARD_CAP,
        "combined_with_prior_trace_usd": RERANK_FULL_CAP + GEN_HARD_CAP + 0.224985,
        "within_owner_reported_balance": RERANK_FULL_CAP + GEN_HARD_CAP + 0.224985 <= 5.0,
        "human_validation_complete": False,
        "inputs": {str(path.relative_to(ROOT)): sha(path) for path in [QA, CHUNKS, PROMPT_RAG_PROMPT, GEN_PROMPT, GEN_SCHEMA, *run_paths.values()]},
    }
    config_path = OUT / "execution_config.json"
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    AUDIT.write_text(json.dumps({**config, "execution_config_sha256": sha(config_path), "live_calls_after_freeze": 0}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(json.loads(AUDIT.read_text()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
