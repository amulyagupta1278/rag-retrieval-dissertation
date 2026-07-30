#!/usr/bin/env python3
"""Freeze Phase 8 Prompt-RAG request hashes and conservative trace budget."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.prompt_rag_claude_v2 import (  # noqa: E402
    INPUT_USD_PER_MILLION,
    MAX_OUTPUT_TOKENS,
    MODEL,
    OUTPUT_USD_PER_MILLION,
    build_request,
    request_sha256,
)
from src.utils.atomic_io import stable_json  # noqa: E402
from src.utils.io_utils import load_jsonl  # noqa: E402


QA = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qa_dataset.jsonl"
CHUNKS = ROOT / "releases/v3_clean/data/chunks/chunks_v3_clean.jsonl"
BM25 = ROOT / "runs/phase8_exploratory_five_system/bm25_top50/retrieval/bm25_run.jsonl"
PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
OUT = ROOT / "runs/phase8_exploratory_five_system/prompt_rag_freeze"
AUDIT = ROOT / "audits/phase8_exploratory/prompt_rag_trace_freeze.json"
TRACE_N = 5
TRACE_HARD_CAP_USD = 0.62
FULL_HARD_CAP_USD = 9.61


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(request: dict) -> int:
    return math.ceil(len(stable_json(request).encode("utf-8")) / 2) + 256


def main() -> int:
    qa = {row["question_id"]: row for row in load_jsonl(QA)}
    chunks = {row["chunk_id"]: row for row in load_jsonl(CHUNKS)}
    runs = sorted(load_jsonl(BM25), key=lambda row: row["query_id"])
    if len(runs) != 100 or {row["query_id"] for row in runs} != set(qa):
        raise RuntimeError("BM25 top-50 does not cover 100 Phase 8 questions")
    prompt = PROMPT.read_text(encoding="utf-8")
    plans = []
    for row in runs:
        candidates = row["results"][:50]
        if len(candidates) != 50 or len({value["chunk_id"] for value in candidates}) != 50:
            raise RuntimeError(f"{row['query_id']} lacks 50 unique BM25 candidates")
        request = build_request(
            query={"query_id": row["query_id"], "question": qa[row["query_id"]]["question"]},
            candidates=[
                {"chunk_id": value["chunk_id"], "text": chunks[value["chunk_id"]]["text"]}
                for value in candidates
            ],
            system_instruction=prompt,
        )
        plans.append({
            "query_id": row["query_id"],
            "candidate_chunk_ids": [value["chunk_id"] for value in candidates],
            "request_sha256": request_sha256(request),
            "input_token_envelope": envelope(request),
        })
    # Trace largest requests first: strongest pre-execution cost/truncation stress test.
    trace_ids = [
        row["query_id"]
        for row in sorted(plans, key=lambda row: (-row["input_token_envelope"], row["query_id"]))[:TRACE_N]
    ]
    total_input = sum(row["input_token_envelope"] for row in plans)
    max_input = max(row["input_token_envelope"] for row in plans)
    full_worst = (
        total_input * INPUT_USD_PER_MILLION / 1_000_000
        + len(plans) * MAX_OUTPUT_TOKENS * OUTPUT_USD_PER_MILLION / 1_000_000
    )
    reserve = (
        max_input * INPUT_USD_PER_MILLION / 1_000_000
        + MAX_OUTPUT_TOKENS * OUTPUT_USD_PER_MILLION / 1_000_000
    )
    trace_input = sum(row["input_token_envelope"] for row in plans if row["query_id"] in trace_ids)
    trace_worst = (
        trace_input * INPUT_USD_PER_MILLION / 1_000_000
        + TRACE_N * MAX_OUTPUT_TOKENS * OUTPUT_USD_PER_MILLION / 1_000_000
        + reserve
    )
    if full_worst + reserve > FULL_HARD_CAP_USD or trace_worst > TRACE_HARD_CAP_USD:
        raise RuntimeError("proposed Prompt-RAG cap insufficient")

    OUT.mkdir(parents=True, exist_ok=True)
    plan_path = OUT / "request_plan.jsonl"
    plan_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in plans), encoding="utf-8"
    )
    config = {
        "status": "offline_frozen_pending_owner_trace_approval",
        "benchmark_status": "exploratory_automated_only_pending_human_validation",
        "model": MODEL,
        "request_n": len(plans),
        "candidate_n": 50,
        "trace_n": TRACE_N,
        "trace_query_ids": trace_ids,
        "temperature": 0,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "automatic_retries": 0,
        "fallback": None,
        "ranking": "score descending then chunk ID ascending",
        "input_token_envelope": total_input,
        "maximum_output_tokens": len(plans) * MAX_OUTPUT_TOKENS,
        "full_worst_case_usd": round(full_worst, 6),
        "ambiguous_dispatch_reserve_usd": round(reserve, 6),
        "full_hard_cap_usd": FULL_HARD_CAP_USD,
        "trace_worst_case_including_reserve_usd": round(trace_worst, 6),
        "trace_hard_cap_usd": TRACE_HARD_CAP_USD,
        "pricing": {
            "input_usd_per_million": INPUT_USD_PER_MILLION,
            "output_usd_per_million": OUTPUT_USD_PER_MILLION,
            "lineage": "Phase 7 official Anthropic pricing verification dated 2026-07-28",
        },
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in (QA, CHUNKS, BM25, PROMPT)},
        "request_plan_sha256": sha256(plan_path),
    }
    config_path = OUT / "execution_config.json"
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit = {
        **config,
        "execution_authorized": False,
        "live_api_calls": 0,
        "execution_config_sha256": sha256(config_path),
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
