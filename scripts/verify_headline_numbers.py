#!/usr/bin/env python3
"""Recompute every headline figure quoted in the defence deck from the canonical files.

Reads only:
  runs/canonical_v2_pilot/benchmark/questions_r5.jsonl
  runs/canonical_v2_pilot/benchmark/final_pooled_qrels.tsv
  runs/canonical_v2_pilot/retrieval/{system}_top50.jsonl
  runs/canonical_v2_pilot/metrics/system_comparison_table.json

Exits non-zero if any recomputed value disagrees with the value in the deck.

    python scripts/verify_headline_numbers.py
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANON = ROOT / "runs" / "canonical_v2_pilot"

SYSTEMS = {
    "bm25": "BM25",
    "faiss_windowed_max": "FAISS (dense)",
    "graph_v3_2": "Entity Graph",
    "hybrid_rrf": "Hybrid RRF",
    "prompt_rag_claude": "Prompt-RAG",
}

# Values as they appear in defence/RAG_Dissertation_Defence_v2.pptx
DECK_AGGREGATE = {
    "bm25": 0.9412,
    "faiss_windowed_max": 0.8279,
    "graph_v3_2": 0.6765,
    "hybrid_rrf": 0.9559,
    "prompt_rag_claude": 0.9779,
}

DECK_BY_CATEGORY = {  # slide 9: (BM25, FAISS)
    "paraphrase": (0.833, 0.408),
    "exact_lookup": (1.000, 0.867),
    "terminology": (0.917, 0.917),
    "entity_relation": (1.000, 0.917),
    "multi_hop": (1.000, 0.917),
    "synthesis": (0.875, 1.000),
}

TOL = 0.001


def load():
    questions = {}
    with open(CANON / "benchmark" / "questions_r5.jsonl") as fh:
        for line in fh:
            rec = json.loads(line)
            questions[rec["question_id"]] = rec

    qrels: dict[str, dict[str, int]] = collections.defaultdict(dict)
    with open(CANON / "benchmark" / "final_pooled_qrels.tsv") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 4:
                qrels[parts[0]][parts[2]] = int(parts[3])

    rankings: dict[str, dict[str, list]] = {}
    for key in SYSTEMS:
        rankings[key] = {}
        with open(CANON / "retrieval" / f"{key}_top50.jsonl") as fh:
            for line in fh:
                rec = json.loads(line)
                rankings[key][rec["query_id"]] = rec["ranking"]

    return questions, qrels, rankings


def mrr_at_10(qid, key, qrels, rankings) -> float:
    for hit in rankings[key][qid][:10]:
        if qrels[qid].get(hit["chunk_id"], 0) > 0:
            return 1.0 / hit["rank"]
    return 0.0


def check(label, computed, expected, failures):
    ok = abs(computed - expected) <= TOL
    mark = "ok  " if ok else "FAIL"
    print(f"  [{mark}] {label:<44} computed {computed:.4f}   deck {expected:.4f}")
    if not ok:
        failures.append(label)
    return ok


def main() -> int:
    if not CANON.exists():
        print(f"canonical directory not found: {CANON}", file=sys.stderr)
        return 2

    questions, qrels, rankings = load()
    failures: list[str] = []

    n_q = len(questions)
    n_graded = sum(1 for q in qrels.values() for v in q.values() if v > 0)
    print(f"\nCanonical pilot: {n_q} questions, {n_graded} relevance judgements > 0\n")

    check("question count", n_q, 34, failures)
    check("graded relevance judgements", n_graded, 183, failures)

    print("\nAggregate MRR@10")
    for key, label in SYSTEMS.items():
        value = sum(mrr_at_10(q, key, qrels, rankings) for q in questions) / n_q
        check(label, value, DECK_AGGREGATE[key], failures)

    by_cat = collections.defaultdict(list)
    for qid, rec in questions.items():
        by_cat[rec["category"]].append(qid)

    print("\nMRR@10 by category — BM25 vs FAISS")
    for cat, (exp_bm25, exp_faiss) in DECK_BY_CATEGORY.items():
        qids = by_cat.get(cat)
        if not qids:
            print(f"  [FAIL] category missing from benchmark: {cat}")
            failures.append(f"missing category {cat}")
            continue
        got_bm25 = sum(mrr_at_10(q, "bm25", qrels, rankings) for q in qids) / len(qids)
        got_faiss = sum(mrr_at_10(q, "faiss_windowed_max", qrels, rankings) for q in qids) / len(qids)
        check(f"{cat} · BM25 (n={len(qids)})", got_bm25, exp_bm25, failures)
        check(f"{cat} · FAISS (n={len(qids)})", got_faiss, exp_faiss, failures)

    # cross-check against the frozen metrics table written at evaluation time
    print("\nCross-check against frozen system_comparison_table.json")
    table = json.loads((CANON / "metrics" / "system_comparison_table.json").read_text())
    for key, label in SYSTEMS.items():
        frozen = table[key]["final_pooled"]["metrics"]["mrr_at_10"]
        check(f"{label} (frozen table)", frozen, DECK_AGGREGATE[key], failures)

    print()
    if failures:
        print(f"{len(failures)} MISMATCH(ES): " + ", ".join(failures))
        return 1
    print("All headline figures reproduce from the canonical files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
