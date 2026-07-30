#!/usr/bin/env python3
"""Freeze R4 mixed BM25/FAISS Prompt-RAG requests and conservative budget."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values  # noqa: E402
from src.retrievers.prompt_rag_claude_v1 import create_client_from_environment, make_token_counter  # noqa: E402
from src.retrievers.prompt_rag_phase8_r4 import MAX_OUTPUT_TOKENS, build_request  # noqa: E402
from src.utils.atomic_io import stable_json  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
OUT = BASE / "prompt_rag_r4_freeze"
QA = BASE / "benchmark/qa_dev_test.jsonl"
CHUNKS = BASE / "corpus/chunks_section_aware_450w.jsonl"
BM25 = BASE / "retrieval/bm25_section_aware_run.jsonl"
FAISS = BASE / "retrieval/faiss_cosine/faiss_run.jsonl"
PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"
TOTAL_CAP = 3.70
GENERATION_RESERVE = 0.75
EXCERPT_WORDS = 300


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(value) + "\n", encoding="utf-8")


def main() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("freeze output exists; refusing overwrite")
    qa = {r["question_id"]: r for r in load(QA)}
    chunks = {r["chunk_id"]: r for r in load(CHUNKS)}
    bm25 = {r["query_id"]: r for r in load(BM25)}
    faiss = {r["query_id"]: r for r in load(FAISS)}
    prompt = PROMPT.read_text(encoding="utf-8")
    env = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    counter = make_token_counter(create_client_from_environment(environ=env))
    plans = []
    for qid in sorted(qa):
        left = [r["chunk_id"] for r in bm25[qid]["results"][:25]]
        right = [r["chunk_id"] for r in faiss[qid]["results"][:25]]
        ids = left + [cid for cid in right if cid not in set(left)]
        request = build_request(
            query={"query_id": qid, "question": qa[qid]["question"]},
            candidates=[{"chunk_id": cid, "text": " ".join(chunks[cid]["text"].split()[:EXCERPT_WORDS])} for cid in ids],
            system_instruction=prompt,
        )
        encoded = stable_json(request).encode()
        exact_tokens = counter(request)
        plans.append({
            "query_id": qid, "category": qa[qid]["category"], "candidate_n": len(ids),
            "candidate_chunk_ids": ids, "request_sha256": sha_bytes(encoded),
            "exact_input_token_count": exact_tokens,
            "input_token_envelope": exact_tokens + 8,
        })
    categories = sorted({p["category"] for p in plans})
    trace = []
    for category in categories:
        group = [p for p in plans if p["category"] == category]
        trace.append(max(group, key=lambda p: (p["input_token_envelope"], p["query_id"]))["query_id"])
    if len(trace) != 5:
        raise SystemExit(f"expected five primary categories, got {categories}")
    input_envelope = sum(p["input_token_envelope"] for p in plans)
    output_envelope = len(plans) * MAX_OUTPUT_TOKENS
    retrieval_worst = input_envelope / 1_000_000 + output_envelope * 5 / 1_000_000
    ambiguous_reserve = max(p["input_token_envelope"] for p in plans) / 1_000_000 + MAX_OUTPUT_TOKENS * 5 / 1_000_000
    retrieval_cap = round(retrieval_worst + ambiguous_reserve, 6)
    if retrieval_cap + GENERATION_RESERVE > TOTAL_CAP:
        raise SystemExit(f"budget impossible: {retrieval_cap}+{GENERATION_RESERVE}>{TOTAL_CAP}")
    OUT.mkdir(parents=True)
    plan_path = OUT / "request_plan.jsonl"
    plan_path.write_text("".join(stable_json(p) + "\n" for p in plans), encoding="utf-8")
    config = {
        "schema_version": 1, "status": "frozen_owner_approved", "approved_base_commit": "66a2ee35a17aab4a845d45589841349eaf4aa510",
        "model": "claude-haiku-4-5-20251001", "temperature": 0, "max_output_tokens": MAX_OUTPUT_TOKENS,
        "candidate_rule": "BM25 top25 then unseen FAISS top25, deduplicate by chunk_id",
        "candidate_text_rule": "first 300 whitespace-delimited words of each frozen chunk",
        "query_n": 100, "trace_query_ids": trace, "zero_retries": True, "fallback": None, "replacement": None,
        "input_token_count_method": "Anthropic messages.count_tokens; envelope adds 8 tokens per request",
        "exact_input_token_count": sum(p["exact_input_token_count"] for p in plans),
        "input_token_envelope": input_envelope, "output_token_envelope": output_envelope,
        "input_price_usd_per_million": 1.0, "output_price_usd_per_million": 5.0,
        "retrieval_worst_case_usd": round(retrieval_worst, 6), "ambiguous_dispatch_reserve_usd": round(ambiguous_reserve, 6),
        "retrieval_hard_cap_usd": retrieval_cap, "generation_reserved_usd": GENERATION_RESERVE,
        "total_additional_r4_hard_cap_usd": TOTAL_CAP,
        "request_plan_sha256": sha_bytes(plan_path.read_bytes()),
        "inputs": {str(p.relative_to(ROOT)): sha_bytes(p.read_bytes()) for p in (QA, CHUNKS, BM25, FAISS, PROMPT)},
        "output_paths": {"trace": str((BASE / "prompt_rag_r4_trace").relative_to(ROOT)), "full": str((BASE / "prompt_rag_r4_full").relative_to(ROOT))},
    }
    dump(OUT / "execution_config.json", config)
    dump(OUT / "approval_record.json", {
        "status": "owner_approved", "approved_at_local": "2026-07-29T02:06:00+05:30",
        "approval_scope": "full Phase 8 R4 automated completion from commit 66a2ee35; zero retries/fallback/replacement; total additional API cap $3.70",
        "execution_config_sha256": sha_bytes((OUT / "execution_config.json").read_bytes()),
        "request_plan_sha256": config["request_plan_sha256"],
    })
    dump(OUT / "freeze_manifest.json", {str(p.relative_to(ROOT)): sha_bytes(p.read_bytes()) for p in sorted(OUT.glob("*")) if p.name != "freeze_manifest.json"})
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
