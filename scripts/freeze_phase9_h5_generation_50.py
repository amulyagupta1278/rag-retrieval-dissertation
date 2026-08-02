#!/usr/bin/env python3
"""Freeze 50 additional H5 generation requests; performs no provider calls."""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase7_context import serialize_context  # noqa: E402
from src.generation.phase7_freeze import response_schema  # noqa: E402
from src.generation.phase7_v2_freeze import (  # noqa: E402
    MODEL, TEMPERATURE, build_request,
    conservative_input_token_envelope, request_sha256,
)
from src.utils.atomic_io import stable_json  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
OUT = ROOT / "runs/phase9_h5_followup/generation_freeze"
AUDIT = ROOT / "audits/phase9_h5_followup"
QA = BASE / "benchmark/qa_dev_test.jsonl"
CHUNKS = BASE / "corpus/chunks_section_aware_450w.jsonl"
PROMPT = ROOT / "prompts/phase8_r4_answer_generation_v3.txt"
PRIOR = BASE / "generation_r4_freeze/execution_config.json"
SYSTEMS = {
    "bm25": BASE / "retrieval/bm25_section_aware_run.jsonl",
    "faiss_cosine": BASE / "retrieval/faiss_cosine/faiss_run.jsonl",
    "graph_v4": BASE / "retrieval/graph_hybrid_v4/graph_run.jsonl",
    "hybrid_r4": BASE / "retrieval/graph_hybrid_v4/hybrid_weighted_run.jsonl",
    "prompt_rag_claude": BASE / "prompt_rag_r4_v2_full/prompt_rag_run.jsonl",
}
MAX_OUTPUT_TOKENS = 1024


def maximum_cost_usd(input_tokens: int, request_n: int) -> float:
    return input_tokens / 1_000_000 + request_n * MAX_OUTPUT_TOKENS * 5 / 1_000_000


def load(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(value) + "\n", encoding="utf-8")


def main() -> int:
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError("Phase 9 H5 generation freeze exists; refuse overwrite")
    qa_rows = load(QA)
    qa = {row["question_id"]: row for row in qa_rows}
    prior_ids = set(json.loads(PRIOR.read_text())["query_ids"])
    grouped = defaultdict(list)
    for row in qa_rows:
        if row.get("split") == "test" and row["question_id"] not in prior_ids:
            grouped[row["category"]].append(row["question_id"])
    if sorted(grouped) != ["entity_relation", "exact_match", "multi_hop", "paraphrase", "terminology_heavy"]:
        raise RuntimeError("unexpected locked-test categories")
    rng = random.Random(4209)
    selected = sorted(qid for category in sorted(grouped) for qid in rng.sample(sorted(grouped[category]), 2))
    if len(selected) != 10 or prior_ids.intersection(selected):
        raise RuntimeError("additional question selection invalid")
    chunks = {row["chunk_id"]: row["text"] for row in load(CHUNKS)}
    runs = {system: {row["query_id"]: row for row in load(path)} for system, path in SYSTEMS.items()}
    prompt, schema = PROMPT.read_text(encoding="utf-8"), response_schema()
    plans, payloads = [], []
    for qid in selected:
        for system in sorted(SYSTEMS):
            top10 = [row["chunk_id"] for row in runs[system][qid]["results"][:10]]
            context = top10[:3]
            serialized, mapping = serialize_context(qa[qid]["question"], context, chunks, 3)
            request = build_request(prompt=prompt, serialized_context=serialized, schema=schema)
            request["max_tokens"] = MAX_OUTPUT_TOKENS
            logical = f"{qid}:{system}"
            blind = "P9H5G" + hashlib.sha256(("phase9-h5-generation:" + logical).encode()).hexdigest()[:12]
            plan = {
                "blinded_request_id": blind, "logical_request_id": logical, "query_id": qid,
                "system_id": system, "category": qa[qid]["category"], "context_chunk_ids": context,
                "evidence_id_to_chunk_id": mapping, "top10_chunk_ids": top10,
                "request_sha256": request_sha256(request),
                "planned_input_token_envelope": conservative_input_token_envelope(request),
                "prompt_version": "phase8_r4_v3_semantic_contract",
            }
            plans.append(plan)
            payloads.append({"blinded_request_id": blind, "request_sha256": plan["request_sha256"], "request": request})
    plans.sort(key=lambda row: row["blinded_request_id"])
    payloads.sort(key=lambda row: row["blinded_request_id"])
    input_envelope = sum(row["planned_input_token_envelope"] for row in plans)
    worst = maximum_cost_usd(input_envelope, 50)
    reserve = maximum_cost_usd(max(row["planned_input_token_envelope"] for row in plans), 1)
    hard_cap = round(worst + reserve, 6)
    OUT.mkdir(parents=True)
    (OUT / "request_plan.jsonl").write_text("".join(stable_json(row) + "\n" for row in plans), encoding="utf-8")
    (OUT / "request_payloads.jsonl").write_text("".join(stable_json(row) + "\n" for row in payloads), encoding="utf-8")
    dump(OUT / "response_schema.json", schema)
    config = {
        "status": "frozen_owner_approved", "authorization": "User instruction: Generate missing 50 answers",
        "query_ids": selected, "category_counts": dict(Counter(qa[qid]["category"] for qid in selected)),
        "system_ids": sorted(SYSTEMS), "request_n": 50, "model": MODEL, "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS, "context_depth": 3, "zero_retries": True,
        "fallback": None, "replacement": None, "prompt_version": "phase8_r4_v3_semantic_contract",
        "existing_100_prompt_versions_mixed": True,
        "input_token_envelope": input_envelope, "generation_worst_case_usd": round(worst, 6),
        "ambiguous_dispatch_reserve_usd": round(reserve, 6), "generation_hard_cap_usd": hard_cap,
        "output_path": "runs/phase9_h5_followup/generation_50",
    }
    dump(OUT / "execution_config.json", config)
    inputs = {str(path.relative_to(ROOT)): sha(path) for path in [QA, CHUNKS, PROMPT, PRIOR, *SYSTEMS.values()]}
    artifacts = {str(path.relative_to(ROOT)): sha(path) for path in sorted(OUT.glob("*")) if path.name != "freeze_manifest.json"}
    dump(OUT / "freeze_manifest.json", {"inputs": inputs, "artifacts": artifacts})
    dump(AUDIT / "generation_50_approval.json", {
        "status": "owner_approved", "scope": "50 additional Phase 9 H5 answers; frozen plan; zero retries",
        "authorization": "User instruction: Generate missing 50 answers",
        "execution_config_sha256": sha(OUT / "execution_config.json"),
        "freeze_manifest_sha256": sha(OUT / "freeze_manifest.json"),
        "hard_cap_usd": hard_cap,
    })
    print(json.dumps(config, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
