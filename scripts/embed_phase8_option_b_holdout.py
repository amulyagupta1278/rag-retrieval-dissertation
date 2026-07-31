#!/usr/bin/env python3
"""Encode frozen holdout questions without importing FAISS in this process."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "runs/phase8_option_b_holdout/freeze/qa_holdout_12.jsonl"
OUT = ROOT / "runs/phase8_option_b_holdout/retrieval/faiss_cosine"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    rows = [json.loads(line) for line in QA.read_text(encoding="utf-8").splitlines() if line]
    model = SentenceTransformer(MODEL, revision=REVISION)
    embeddings = np.asarray(
        model.encode([row["question"] for row in rows], normalize_embeddings=True),
        dtype=np.float32,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    np.save(OUT / "query_embeddings.npy", embeddings)
    (OUT / "query_embeddings_manifest.json").write_text(json.dumps({
        "model": MODEL,
        "normalize_embeddings": True,
        "qa_sha256": sha(QA),
        "query_ids": [row["question_id"] for row in rows],
        "revision": REVISION,
        "shape": list(embeddings.shape),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
