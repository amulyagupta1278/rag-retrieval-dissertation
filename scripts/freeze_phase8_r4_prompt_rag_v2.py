#!/usr/bin/env python3
"""Freeze separate V2 recovery after preserved 512-token V1 trace failure."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.prompt_rag_phase8_r4_v2 import MAX_OUTPUT_TOKENS, build_request  # noqa: E402
from src.utils.atomic_io import stable_json  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
V1 = BASE / "prompt_rag_r4_freeze"
OUT = BASE / "prompt_rag_r4_v2_freeze"
QA = BASE / "benchmark/qa_dev_test.jsonl"
CHUNKS = BASE / "corpus/chunks_section_aware_450w.jsonl"
PROMPT = ROOT / "prompts/prompt_rag_retrieval_v1.txt"


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(value) + "\n", encoding="utf-8")


def main() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("V2 freeze exists; refusing overwrite")
    v1_config = json.loads((V1 / "execution_config.json").read_text())
    v1_plans = load(V1 / "request_plan.jsonl")
    qa = {r["question_id"]: r for r in load(QA)}
    chunks = {r["chunk_id"]: r for r in load(CHUNKS)}
    prompt = PROMPT.read_text()
    plans = []
    for old in v1_plans:
        qid, ids = old["query_id"], old["candidate_chunk_ids"]
        request = build_request(
            query={"query_id": qid, "question": qa[qid]["question"]},
            candidates=[{"chunk_id": cid, "text": " ".join(chunks[cid]["text"].split()[:300])} for cid in ids],
            system_instruction=prompt,
        )
        plans.append({**old, "request_sha256": hashlib.sha256(stable_json(request).encode()).hexdigest()})
    OUT.mkdir(parents=True)
    plan = OUT / "request_plan.jsonl"
    plan.write_text("".join(stable_json(p) + "\n" for p in plans), encoding="utf-8")
    input_envelope = sum(p["input_token_envelope"] for p in plans)
    worst = input_envelope / 1e6 + 100 * MAX_OUTPUT_TOKENS * 5 / 1e6
    reserve = max(p["input_token_envelope"] for p in plans) / 1e6 + MAX_OUTPUT_TOKENS * 5 / 1e6
    retrieval_cap = round(worst + reserve, 6)
    config = {
        **v1_config,
        "schema_version": 2,
        "status": "frozen_pending_owner_approval",
        "recovery_from_failure_commit": "b39421d",
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "output_token_envelope": 100 * MAX_OUTPUT_TOKENS,
        "retrieval_worst_case_usd": round(worst, 6),
        "ambiguous_dispatch_reserve_usd": round(reserve, 6),
        "retrieval_hard_cap_usd": retrieval_cap,
        "request_plan_sha256": sha(plan),
        "output_paths": {"trace": "runs/phase8_r4_improvements/prompt_rag_r4_v2_trace", "full": "runs/phase8_r4_improvements/prompt_rag_r4_v2_full"},
        "v1_policy": "preserved; never rerun, replace, or backfill",
    }
    if retrieval_cap + config["generation_reserved_usd"] > config["total_additional_r4_hard_cap_usd"]:
        raise SystemExit("V2 recovery plus generation reserve exceeds $3.70")
    dump(OUT / "execution_config.json", config)
    dump(OUT / "approval_template.json", {
        "status": "pending_owner_approval",
        "required_statement": f"Approve Phase 8 R4 Prompt-RAG V2 recovery at commit {{COMMIT}}, using unchanged mixed BM25-top-25 plus unseen-FAISS-top-25 union, 300-word deterministic excerpts, claude-haiku-4-5-20251001, temperature 0, 1024 maximum output tokens, zero retries, no fallback or replacement, separate V2 outputs, retrieval hard cap ${retrieval_cap:.6f}, generation reserve $0.750000, and total additional R4 hard cap $3.700000. Preserve failed V1 unchanged; run five-request V2 trace and continue remaining 95 only if every frozen gate passes.",
        "execution_config_sha256": sha(OUT / "execution_config.json"),
        "request_plan_sha256": sha(plan),
    })
    dump(OUT / "freeze_manifest.json", {str(p.relative_to(ROOT)): sha(p) for p in sorted(OUT.glob("*")) if p.name != "freeze_manifest.json"})
    print(json.dumps({"retrieval_hard_cap_usd": retrieval_cap, "combined_reserved_usd": round(retrieval_cap + .75, 6)}, indent=2))


if __name__ == "__main__":
    main()
