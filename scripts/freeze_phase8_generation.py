#!/usr/bin/env python3
"""Freeze Phase 8 five-system answer-generation panel without API calls."""

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
from src.generation.phase7_v2_freeze import (  # noqa: E402
    MAX_OUTPUT_TOKENS,
    MODEL,
    TEMPERATURE,
    build_request,
    conservative_input_token_envelope,
    maximum_cost_usd,
    request_sha256,
)
from src.generation.phase7_freeze import response_schema  # noqa: E402
from src.utils.atomic_io import stable_json  # noqa: E402
from src.utils.io_utils import load_jsonl  # noqa: E402


BASE_COMMIT = "811c9a0b507f6ac154bb08542dd9ca37988c8e3f"
BASE = ROOT / "runs/phase8_exploratory_five_system"
OUT = BASE / "generation_freeze_v1"
AUDIT = ROOT / "audits/phase8_exploratory/generation_freeze_v1.json"
PROTOCOL = ROOT / "docs/PHASE8_GENERATION_PROTOCOL_V1.md"
QA = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qa_dataset.jsonl"
CHUNKS = ROOT / "releases/v3_clean/data/chunks/chunks_v3_clean.jsonl"
PROMPT = ROOT / "prompts/phase7_answer_generation_v1.txt"
CONTEXT_DEPTH = 3
SAMPLE_SEED = 42
QUERY_N = 20
SYSTEM_N = 5
REQUEST_N = 100
TRACE_N = 5
TRACE_CAP_USD = 0.10
FULL_CAP_USD = 1.25
SYSTEM_PATHS = {
    "bm25": BASE / "bm25_top50/retrieval/bm25_run.jsonl",
    "faiss_windowed_max": ROOT / "runs/phase8_exploratory_automated_r3/results/retrieval/faiss_run.jsonl",
    "graph_v3_2": BASE / "graph_top50/retrieval/graphrag_run.jsonl",
    "hybrid_rrf": BASE / "hybrid_rrf/retrieval/hybrid_rrf_run.jsonl",
    "prompt_rag_claude": BASE / "prompt_rag_top10_full/retrieval/prompt_rag_top10_run.jsonl",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def select_queries(qa_rows: list[dict]) -> list[str]:
    by_category: dict[str, list[str]] = defaultdict(list)
    for row in qa_rows:
        by_category[row["category"]].append(row["question_id"])
    if len(by_category) != 5 or set(map(len, by_category.values())) != {20}:
        raise RuntimeError("frozen Phase 8 category contract differs from five categories of 20")
    rng = random.Random(SAMPLE_SEED)
    selected = [qid for category in sorted(by_category) for qid in rng.sample(sorted(by_category[category]), 4)]
    if len(selected) != QUERY_N or len(set(selected)) != QUERY_N:
        raise RuntimeError("generation query sample differs")
    return sorted(selected)


def select_trace(rows: list[dict]) -> list[dict]:
    selected: list[dict] = []
    used_categories: set[str] = set()
    for system in sorted(SYSTEM_PATHS):
        choices = [row for row in rows if row["system_id"] == system and row["category"] not in used_categories]
        choices.sort(key=lambda row: (hashlib.sha256(row["logical_request_id"].encode()).hexdigest(), row["logical_request_id"]))
        chosen = choices[0]
        selected.append(chosen)
        used_categories.add(chosen["category"])
    if len(selected) != TRACE_N or len(used_categories) != 5:
        raise RuntimeError("trace must cover five systems and five available categories")
    return selected


def protocol_text(categories: list[str]) -> str:
    return f"""# Phase 8 Generation Protocol V1

Status: frozen before outputs; execution unauthorized.

## Scope

- Base commit: `{BASE_COMMIT}`
- Sample: 20 deterministic questions, seed 42; four from each available category.
- Frozen Phase 8 benchmark categories: {', '.join(categories)}.
- Limitation: benchmark has no synthesis category. No sixth category was fabricated.
- Systems: BM25, FAISS windowed-max, Graph v3.2, Hybrid RRF, Prompt-RAG Claude.
- Panel: 20 questions x 5 systems = 100 requests.
- Context: first three results from each system's frozen top-10 ranking. Every supplied chunk is therefore inside that system's top 10.

## Fixed generation contract

- Model: `{MODEL}`
- Prompt: `prompts/phase7_answer_generation_v1.txt`
- Temperature: {TEMPERATURE}
- Maximum output: {MAX_OUTPUT_TOKENS} tokens
- Strict JSON schema; inline evidence citations `E01`-`E03`
- Zero retries, fallback, replacement, tools, or external knowledge
- Pre-dispatch ledger and cumulative projected-cost gate
- Trace and full outputs use separate directories

Requests expose question and anonymized evidence only. System identity, ranks, scores, category, qrels, reference answer, and gold evidence remain sealed from model and blinded evaluation package.

## Evaluation rubric

Dimensions remain separate: correctness, faithfulness, completeness, citation accuracy, unsupported-claim severity, and abstention quality. Quality dimensions use 0=poor, 1=partial, 2=good. Unsupported-claim severity uses 0=none, 1=minor, 2=central. No composite score. AI evaluation requires separate disclosure and approval; human validation remains incomplete.

## Cost and stop gates

- Five-request trace cap: ${TRACE_CAP_USD:.2f}
- Cumulative 100-request generation hard cap: ${FULL_CAP_USD:.2f}
- One ambiguous-dispatch reserve included in each projection
- Stop after trace. Remaining 95 requests require separate approval.
"""


def main() -> int:
    qa_rows = load_jsonl(QA)
    qa = {row["question_id"]: row for row in qa_rows}
    chunks = {row["chunk_id"]: row["text"] for row in load_jsonl(CHUNKS)}
    selected = select_queries(qa_rows)
    systems = {
        system: {row["query_id"]: row for row in load_jsonl(path)}
        for system, path in SYSTEM_PATHS.items()
    }
    if any(set(rows) != set(qa) for rows in systems.values()):
        raise RuntimeError("five-system query coverage differs from frozen 100-query benchmark")

    prompt = PROMPT.read_text(encoding="utf-8")
    schema = response_schema()
    sealed: list[dict] = []
    payloads: list[dict] = []
    for query_id in selected:
        for system_id in sorted(systems):
            results = systems[system_id][query_id]["results"]
            if len(results) < 10:
                raise RuntimeError(f"{system_id}/{query_id} lacks frozen top-10")
            top10 = [result["chunk_id"] for result in results[:10]]
            context_ids = top10[:CONTEXT_DEPTH]
            serialized, mapping = serialize_context(qa[query_id]["question"], context_ids, chunks, CONTEXT_DEPTH)
            request = build_request(prompt=prompt, serialized_context=serialized, schema=schema)
            logical_id = f"{query_id}:{system_id}"
            sealed.append({
                "category": qa[query_id]["category"],
                "context_chunk_ids": context_ids,
                "evidence_id_to_chunk_id": mapping,
                "logical_request_id": logical_id,
                "planned_input_token_envelope": conservative_input_token_envelope(request),
                "query_id": query_id,
                "request_sha256": request_sha256(request),
                "system_id": system_id,
                "top10_chunk_ids": top10,
            })
            payloads.append({"logical_request_id": logical_id, "request": request, "request_sha256": request_sha256(request)})

    blinded_order = sorted(sealed, key=lambda row: (hashlib.sha256(("phase8-generation-v1:" + row["logical_request_id"]).encode()).hexdigest(), row["logical_request_id"]))
    blind_by_logical = {row["logical_request_id"]: f"P8G{index:03d}" for index, row in enumerate(blinded_order, 1)}
    for row in sealed:
        row["blinded_request_id"] = blind_by_logical[row["logical_request_id"]]
    for row in payloads:
        row["blinded_request_id"] = blind_by_logical[row.pop("logical_request_id")]
    sealed.sort(key=lambda row: row["blinded_request_id"])
    payloads.sort(key=lambda row: row["blinded_request_id"])
    trace = select_trace(sealed)

    total_input = sum(row["planned_input_token_envelope"] for row in sealed)
    reserve_input = max(row["planned_input_token_envelope"] for row in sealed)
    full_worst = maximum_cost_usd(total_input, REQUEST_N)
    reserve = maximum_cost_usd(reserve_input, 1)
    trace_input = sum(row["planned_input_token_envelope"] for row in trace)
    trace_worst = maximum_cost_usd(trace_input, TRACE_N) + reserve
    if full_worst + reserve > FULL_CAP_USD or trace_worst > TRACE_CAP_USD:
        raise RuntimeError("generation cost envelope exceeds hard cap")

    categories = sorted({row["category"] for row in sealed})
    category_counts = Counter(qa[qid]["category"] for qid in selected)
    cost = {
        "ambiguous_dispatch_reserve_usd": round(reserve, 6),
        "full_hard_cap_usd": FULL_CAP_USD,
        "full_input_token_envelope": total_input,
        "full_request_n": REQUEST_N,
        "full_worst_case_usd": round(full_worst, 6),
        "hard_cap_pass": full_worst + reserve <= FULL_CAP_USD,
        "trace_hard_cap_usd": TRACE_CAP_USD,
        "trace_input_token_envelope": trace_input,
        "trace_request_n": TRACE_N,
        "trace_worst_case_including_reserve_usd": round(trace_worst, 6),
    }
    config = {
        "base_commit": BASE_COMMIT,
        "category_counts": dict(sorted(category_counts.items())),
        "category_limitation": "Frozen Phase 8 benchmark has five categories and no synthesis category.",
        "context_depth": CONTEXT_DEPTH,
        "execution_authorized": False,
        "full_execution_authorized": False,
        "generation": {"max_output_tokens": MAX_OUTPUT_TOKENS, "model": MODEL, "temperature": TEMPERATURE},
        "query_ids": selected,
        "query_n": QUERY_N,
        "request_n": REQUEST_N,
        "retry_n": 0,
        "sample_seed": SAMPLE_SEED,
        "status": "offline_frozen_pending_trace_approval",
        "system_ids": sorted(SYSTEM_PATHS),
        "system_n": SYSTEM_N,
        "trace_request_n": TRACE_N,
    }
    evaluation = {
        "ai_evaluation_authorized": False,
        "dimensions": ["correctness", "faithfulness", "completeness", "citation_accuracy", "unsupported_claim_severity", "abstention_quality"],
        "human_validation_complete": False,
        "no_composite_score": True,
        "quality_scale": {"0": "poor", "1": "partial", "2": "good"},
        "status": "frozen_before_outputs",
        "unsupported_claim_severity_scale": {"0": "none", "1": "minor", "2": "central"},
    }

    write_jsonl(OUT / "sealed/request_plan.jsonl", sealed)
    write_jsonl(OUT / "blinded/request_payloads.jsonl", payloads)
    write_json(OUT / "sealed/trace_plan.json", {"selected": [{k: row[k] for k in ("blinded_request_id", "logical_request_id", "query_id", "system_id", "category", "request_sha256", "planned_input_token_envelope")} for row in trace]})
    write_json(OUT / "response_schema.json", schema)
    write_json(OUT / "execution_config.json", config)
    write_json(OUT / "cost_plan.json", cost)
    write_json(OUT / "evaluation_rubric.json", evaluation)
    PROTOCOL.write_text(protocol_text(categories), encoding="utf-8")

    artifact_paths = sorted(path for path in OUT.rglob("*") if path.is_file() and path.name != "freeze_manifest.json") + [PROTOCOL]
    code_paths = [ROOT / "scripts/freeze_phase8_generation.py", ROOT / "scripts/run_phase8_generation_trace.py"]
    inputs = {str(path.relative_to(ROOT)): sha(path) for path in [QA, CHUNKS, PROMPT, *SYSTEM_PATHS.values()]}
    manifest = {
        "artifacts": {str(path.relative_to(ROOT)): sha(path) for path in artifact_paths},
        "base_commit": BASE_COMMIT,
        "code": {str(path.relative_to(ROOT)): sha(path) for path in code_paths},
        "execution_authorized": False,
        "full_execution_authorized": False,
        "inputs": inputs,
        "live_api_calls_n": 0,
        "status": "phase8_generation_v1_offline_freeze",
    }
    write_json(OUT / "freeze_manifest.json", manifest)
    audit = {
        "artifact_manifest_sha256": sha(OUT / "freeze_manifest.json"),
        "category_counts": dict(sorted(category_counts.items())),
        "category_n": len(categories),
        "cost": cost,
        "execution_config_sha256": sha(OUT / "execution_config.json"),
        "live_api_calls_n": 0,
        "request_payloads_sha256": sha(OUT / "blinded/request_payloads.jsonl"),
        "request_plan_sha256": sha(OUT / "sealed/request_plan.jsonl"),
        "status": "offline_frozen_pending_trace_approval",
        "trace_plan_sha256": sha(OUT / "sealed/trace_plan.json"),
    }
    write_json(AUDIT, audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
