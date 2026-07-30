#!/usr/bin/env python3
"""Build and evaluate normalized-cosine FAISS on Phase 8 R4 chunks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_phase8_r4_improvements import aggregate  # noqa: E402
from src.retrievers.faiss_retriever import FAISSRetriever  # noqa: E402


RUN = ROOT / "runs/phase8_r4_improvements"
CHUNKS = RUN / "corpus/chunks_section_aware_450w.jsonl"
QA = RUN / "benchmark/qa_dev_test.jsonl"
SYNTHESIS = RUN / "benchmark/synthesis_candidates_20.jsonl"
CROSSWALK = RUN / "corpus/gold_chunk_crosswalk.jsonl"
OUT = RUN / "retrieval/faiss_cosine"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> int:
    if OUT.exists():
        raise RuntimeError("R4 FAISS output exists; refuse overwrite")
    chunks, qa, synth, crosswalk = rows(CHUNKS), rows(QA), rows(SYNTHESIS), rows(CROSSWALK)
    mapped: dict[str, set[str]] = {}
    for row in crosswalk:
        mapped.setdefault(row["query_id"], set()).add(row["new_chunk_id"])
    synthesis_gold = {
        row["question_id"]: set().union(*(mapped[qid] for qid in row["component_query_ids"]))
        for row in synth
    }
    retriever = FAISSRetriever(
        index_dir=OUT / "index",
        chunks_path=CHUNKS,
        model_name=MODEL,
        model_revision=REVISION,
        similarity_metric="cosine",
        normalize_embeddings=True,
    )
    retriever.build_index(chunks)
    rankings, run_rows = {}, []
    for row in [*qa, *synth]:
        query_id, question = row["question_id"], row["question"]
        results = retriever.retrieve(question, top_k=50)
        rankings[query_id] = [result.chunk_id for result in results]
        run_rows.append({
            "query_id": query_id,
            "query_text": question,
            "retriever": "faiss_cosine_section_aware_r4",
            "top_k": 50,
            "results": [
                {
                    "chunk_id": result.chunk_id,
                    "doc_id": result.doc_id,
                    "score": result.score,
                    "rank": result.rank,
                    "latency_ms": result.latency_ms,
                    "retriever": result.retriever,
                }
                for result in results
            ],
            "config_snapshot": {"model": MODEL, "revision": REVISION, "similarity": "cosine", "normalize_embeddings": True},
        })
    dev = sorted(row["question_id"] for row in qa if row["split"] == "dev")
    test = sorted(row["question_id"] for row in qa if row["split"] == "test")
    synth_ids = sorted(synthesis_gold)
    metrics = {
        "status": "offline_automatic_candidate_pending_human_validation",
        "dev": aggregate(rankings, mapped, dev),
        "test": aggregate(rankings, mapped, test),
        "synthesis_candidate_metrics": aggregate(rankings, synthesis_gold, synth_ids),
        "model": MODEL,
        "revision": REVISION,
        "similarity": "cosine",
        "normalize_embeddings": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "faiss_run.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in run_rows))
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
