#!/usr/bin/env python3
"""Evaluate five frozen R4 systems; locked test remains separate from development."""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/phase8_r4_improvements"
OUT = BASE / "evaluation_r4"
SYSTEMS = {
    "bm25": BASE / "retrieval/bm25_section_aware_run.jsonl",
    "faiss_cosine": BASE / "retrieval/faiss_cosine/faiss_run.jsonl",
    "graph_v4": BASE / "retrieval/graph_hybrid_v4/graph_run.jsonl",
    "hybrid_r4": BASE / "retrieval/graph_hybrid_v4/hybrid_weighted_run.jsonl",
    "prompt_rag_claude": BASE / "prompt_rag_r4_v2_full/prompt_rag_run.jsonl",
}


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric(ids: list[str], gold: set[str], k: int = 10) -> dict[str, float]:
    top = ids[:k]
    hits = [1 if cid in gold else 0 for cid in top]
    first = next((i for i, value in enumerate(hits, 1) if value), None)
    dcg = sum(value / math.log2(i + 1) for i, value in enumerate(hits, 1))
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return {
        "mrr@10": 0.0 if first is None else 1 / first,
        "recall@10": len(set(top) & gold) / len(gold) if gold else 0.0,
        "precision@10": sum(hits) / k,
        "ndcg@10": dcg / ideal if ideal else 0.0,
        "hit@10": float(any(hits)),
    }


def means(rows: list[dict]) -> dict[str, float]:
    keys = rows[0]["metrics"]
    return {key: statistics.fmean(row["metrics"][key] for row in rows) for key in keys}


def latency(run_rows: list[dict], system: str) -> dict:
    if system == "prompt_rag_claude":
        values = [row["latency_seconds"] * 1000 for row in run_rows if isinstance(row.get("latency_seconds"), (int, float))]
        return {"status": "measured", "unit": "ms", "n": len(values), "mean": statistics.fmean(values), "median": statistics.median(values), "p95": sorted(values)[math.ceil(.95 * len(values)) - 1]}
    if system == "graph_v4":
        values = [sum(float(x["latency_ms"]) for x in row["results"][:1]) for row in run_rows if row.get("results") and float(row["results"][0].get("latency_ms", 0)) > 0]
        if values:
            return {"status": "measured", "unit": "ms", "n": len(values), "mean": statistics.fmean(values), "median": statistics.median(values), "p95": sorted(values)[math.ceil(.95 * len(values)) - 1]}
    return {"status": "unavailable", "reason": "No trustworthy measured query latency; stored zeros are not interpreted as zero latency."}


def permutation(left: list[float], right: list[float], seed: int = 42, n: int = 10000) -> dict:
    diffs = [a - b for a, b in zip(left, right)]
    observed = statistics.fmean(diffs)
    rng = random.Random(seed)
    null = [statistics.fmean(d if rng.getrandbits(1) else -d for d in diffs) for _ in range(n)]
    p = (1 + sum(abs(x) >= abs(observed) for x in null)) / (n + 1)
    boot = [statistics.fmean(rng.choice(diffs) for _ in diffs) for _ in range(n)]
    boot.sort()
    return {"difference": observed, "ci95": [boot[249], boot[9749]], "paired_randomization_p_two_sided": p, "n": len(diffs)}


def main() -> None:
    if OUT.exists():
        raise SystemExit("R4 evaluation output exists; refusing overwrite")
    qa = load(BASE / "benchmark/qa_dev_test.jsonl")
    cross = load(BASE / "corpus/gold_chunk_crosswalk.jsonl")
    gold: dict[str, set[str]] = defaultdict(set)
    for row in cross:
        gold[row["query_id"]].add(row["new_chunk_id"])
    qmeta = {row["question_id"]: row for row in qa}
    evaluated, summaries = {}, {}
    for system, path in SYSTEMS.items():
        run = load(path)
        ranking = {row["query_id"]: [x["chunk_id"] for x in row["results"]] for row in run}
        rows = [{"query_id": qid, "split": qmeta[qid]["split"], "category": qmeta[qid]["category"], "metrics": metric(ranking[qid], gold[qid])} for qid in sorted(qmeta)]
        evaluated[system] = rows
        summaries[system] = {
            "development": means([r for r in rows if r["split"] == "dev"]),
            "locked_test": means([r for r in rows if r["split"] == "test"]),
            "all_100_descriptive": means(rows),
            "locked_test_by_category": {cat: means([r for r in rows if r["split"] == "test" and r["category"] == cat]) for cat in sorted({r["category"] for r in rows})},
            "latency": latency(run, system),
        }
    comparisons = []
    test_ids = sorted(qid for qid, row in qmeta.items() if row["split"] == "test")
    by_system = {system: {r["query_id"]: r for r in rows} for system, rows in evaluated.items()}
    for left, right in combinations(SYSTEMS, 2):
        result = permutation([by_system[left][q]["metrics"]["ndcg@10"] for q in test_ids], [by_system[right][q]["metrics"]["ndcg@10"] for q in test_ids])
        comparisons.append({"left": left, "right": right, "metric": "ndcg@10", **result})
    ordered = sorted(enumerate(comparisons), key=lambda x: x[1]["paired_randomization_p_two_sided"])
    running = 0.0
    for rank, (index, row) in enumerate(ordered, 1):
        adjusted = min(1.0, row["paired_randomization_p_two_sided"] * (len(ordered) - rank + 1))
        running = max(running, adjusted)
        comparisons[index]["holm_adjusted_p"] = running
    OUT.mkdir(parents=True)
    (OUT / "metrics.json").write_text(json.dumps({"status": "automated_candidate_pending_human_validation", "primary_scope": "40-query locked test", "qrel_status": "automatic crosswalk pending human validation", "systems": summaries}, indent=2, sort_keys=True) + "\n")
    (OUT / "per_query.json").write_text(json.dumps(evaluated, indent=2, sort_keys=True) + "\n")
    (OUT / "exploratory_statistics.json").write_text(json.dumps({"status": "exploratory_not_preregistered", "method": "10,000 paired sign-flip randomizations and paired bootstrap percentile CI; seed 42; Holm across 10 pairwise nDCG@10 comparisons", "no_hypothesis_support_claimed": True, "comparisons": comparisons}, indent=2, sort_keys=True) + "\n")
    manifest = {str(p.relative_to(ROOT)): sha(p) for p in sorted(OUT.glob("*.json"))}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
