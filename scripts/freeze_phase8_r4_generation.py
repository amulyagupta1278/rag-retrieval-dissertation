#!/usr/bin/env python3
"""Freeze 100-request R4 answer-generation panel under blanket approval."""

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
    MAX_OUTPUT_TOKENS, MODEL, TEMPERATURE, build_request,
    conservative_input_token_envelope, maximum_cost_usd, request_sha256,
)
from src.utils.atomic_io import stable_json  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
OUT = BASE / "generation_r4_freeze"
QA = BASE / "benchmark/qa_dev_test.jsonl"
CHUNKS = BASE / "corpus/chunks_section_aware_450w.jsonl"
PROMPT = ROOT / "prompts/phase7_answer_generation_v1.txt"
SYSTEMS = {
    "bm25": BASE / "retrieval/bm25_section_aware_run.jsonl",
    "faiss_cosine": BASE / "retrieval/faiss_cosine/faiss_run.jsonl",
    "graph_v4": BASE / "retrieval/graph_hybrid_v4/graph_run.jsonl",
    "hybrid_r4": BASE / "retrieval/graph_hybrid_v4/hybrid_weighted_run.jsonl",
    "prompt_rag_claude": BASE / "prompt_rag_r4_v2_full/prompt_rag_run.jsonl",
}
GEN_CAP = 1.00
TOTAL_CAP = 3.70
RETRIEVAL_COST = 2.430722


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(value) + "\n")


def main() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("generation freeze exists; refusing overwrite")
    qa_rows = load(QA)
    qa = {r["question_id"]: r for r in qa_rows}
    chunks = {r["chunk_id"]: r["text"] for r in load(CHUNKS)}
    runs = {name: {r["query_id"]: r for r in load(path)} for name, path in SYSTEMS.items()}
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in qa_rows:
        grouped[row["category"]].append(row["question_id"])
    rng = random.Random(42)
    selected = sorted(q for category in sorted(grouped) for q in rng.sample(sorted(grouped[category]), 4))
    prompt, schema = PROMPT.read_text(), response_schema()
    plans, payloads = [], []
    for qid in selected:
        for system in sorted(SYSTEMS):
            top10 = [r["chunk_id"] for r in runs[system][qid]["results"][:10]]
            context = top10[:3]
            serialized, mapping = serialize_context(qa[qid]["question"], context, chunks, 3)
            request = build_request(prompt=prompt, serialized_context=serialized, schema=schema)
            logical = f"{qid}:{system}"
            blind = "P8R4G" + hashlib.sha256(("phase8-r4-generation:" + logical).encode()).hexdigest()[:12]
            plans.append({"blinded_request_id": blind, "logical_request_id": logical, "query_id": qid, "system_id": system, "category": qa[qid]["category"], "context_chunk_ids": context, "evidence_id_to_chunk_id": mapping, "top10_chunk_ids": top10, "request_sha256": request_sha256(request), "planned_input_token_envelope": conservative_input_token_envelope(request)})
            payloads.append({"blinded_request_id": blind, "request_sha256": request_sha256(request), "request": request})
    plans.sort(key=lambda r: r["blinded_request_id"])
    payloads.sort(key=lambda r: r["blinded_request_id"])
    trace, used = [], set()
    for system in sorted(SYSTEMS):
        options = [r for r in plans if r["system_id"] == system and r["category"] not in used]
        chosen = sorted(options, key=lambda r: r["blinded_request_id"])[0]
        trace.append(chosen["blinded_request_id"]); used.add(chosen["category"])
    total_input = sum(r["planned_input_token_envelope"] for r in plans)
    reserve_input = max(r["planned_input_token_envelope"] for r in plans)
    worst = maximum_cost_usd(total_input, 100)
    reserve = maximum_cost_usd(reserve_input, 1)
    hard = round(worst + reserve, 6)
    if hard > GEN_CAP or RETRIEVAL_COST + hard > TOTAL_CAP:
        raise SystemExit(f"generation budget exceeds cap: {hard}")
    OUT.mkdir(parents=True)
    (OUT / "request_plan.jsonl").write_text("".join(stable_json(r) + "\n" for r in plans))
    (OUT / "request_payloads.jsonl").write_text("".join(stable_json(r) + "\n" for r in payloads))
    config = {
        "status": "frozen_owner_blanket_approved", "base_commit": "8075829", "query_ids": selected,
        "category_counts": dict(Counter(qa[q]["category"] for q in selected)), "system_ids": sorted(SYSTEMS),
        "request_n": 100, "trace_request_ids": trace, "model": MODEL, "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS, "context_depth": 3, "zero_retries": True,
        "fallback": None, "replacement": None, "retrieval_cost_usd": RETRIEVAL_COST,
        "input_token_envelope": total_input, "generation_worst_case_usd": round(worst, 6),
        "ambiguous_dispatch_reserve_usd": round(reserve, 6), "generation_hard_cap_usd": hard,
        "total_additional_r4_hard_cap_usd": TOTAL_CAP,
        "output_paths": {"trace": "runs/phase8_r4_improvements/generation_r4_trace", "full": "runs/phase8_r4_improvements/generation_r4_full"},
        "human_validation_complete": False, "ai_evaluation_authorized": True,
    }
    dump(OUT / "execution_config.json", config)
    dump(OUT / "response_schema.json", schema)
    dump(OUT / "approval_binding.json", {"approval": "audits/phase8_r4/prompt_rag_v2_owner_approval.json", "scope": "blanket Phase 8 R4 generation/evaluation approval", "approval_sha256": sha(ROOT / "audits/phase8_r4/prompt_rag_v2_owner_approval.json")})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in [QA, CHUNKS, PROMPT, *SYSTEMS.values()]}
    dump(OUT / "freeze_manifest.json", {"inputs": inputs, "artifacts": {str(p.relative_to(ROOT)): sha(p) for p in sorted(OUT.glob("*")) if p.name != "freeze_manifest.json"}})
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
