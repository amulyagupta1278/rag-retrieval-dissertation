#!/usr/bin/env python3
"""Search frozen FAISS index using precomputed frozen holdout embeddings."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import faiss
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/phase8_option_b_holdout"
QA = BASE / "freeze/qa_holdout_12.jsonl"
OUT = BASE / "retrieval/faiss_cosine"
R4 = ROOT / "runs/phase8_r4_improvements"
CHUNKS = R4 / "corpus/chunks_section_aware_450w.jsonl"
INDEX = R4 / "retrieval/faiss_cosine/index"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    questions = rows(QA)
    chunks = rows(CHUNKS)
    chunk_by_id = {row["chunk_id"]: row for row in chunks}
    manifest = json.loads((OUT / "query_embeddings_manifest.json").read_text(encoding="utf-8"))
    if manifest["qa_sha256"] != sha(QA) or manifest["query_ids"] != [row["question_id"] for row in questions]:
        raise RuntimeError("FAISS query-embedding manifest mismatch")
    embeddings = np.load(OUT / "query_embeddings.npy")
    config = json.loads((INDEX / "config.json").read_text(encoding="utf-8"))
    if config["provenance"]["chunks_file_sha256"] != sha(CHUNKS):
        raise RuntimeError("FAISS index corpus hash mismatch")
    chunk_ids = json.loads((INDEX / "chunk_ids.json").read_text(encoding="utf-8"))
    if chunk_ids != [row["chunk_id"] for row in chunks]:
        raise RuntimeError("FAISS index chunk order mismatch")
    index = faiss.read_index(str(INDEX / "faiss.index"))
    run = []
    for question_index, question in enumerate(questions):
        started = time.perf_counter()
        distances, indices = index.search(embeddings[question_index : question_index + 1], 50)
        elapsed = time.perf_counter() - started
        results = []
        for rank, (score, index_value) in enumerate(zip(distances[0], indices[0]), 1):
            chunk_id = chunk_ids[int(index_value)]
            results.append({
                "chunk_id": chunk_id,
                "doc_id": chunk_by_id[chunk_id]["doc_id"],
                "latency_ms": elapsed * 1000,
                "rank": rank,
                "retriever": "faiss_cosine",
                "score": float(score),
            })
        run.append({
            "query_id": question["question_id"],
            "query_text": question["question"],
            "retriever": "faiss_cosine",
            "top_k": 50,
            "latency_seconds": elapsed,
            "results": results,
        })
    (OUT / "run.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in run), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
