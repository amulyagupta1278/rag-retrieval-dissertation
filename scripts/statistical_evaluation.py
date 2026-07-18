#!/usr/bin/env python3
"""Export query metrics, bootstrap CIs, and paired tests for frozen runs."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Canonical hypothesis definitions: README.md §Canonical Hypotheses (H1–H5).
# Wording must stay verbatim-identical to that section; tests/test_hypotheses_canonical.py enforces it.
CANONICAL_WORDING = {
    "H1": "BM25 performs competitively with FAISS on exact-match and terminology-sensitive queries.",
    "H2": "FAISS outperforms BM25 on paraphrased/semantic queries where query vocabulary differs from source text.",
    "H3": "Entity-Co-occurrence Graph Retrieval outperforms BM25 and FAISS on entity-relation and multi-hop queries.",
}

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.statistics import (
    bootstrap_mean_ci, holm_bonferroni, paired_bootstrap, paired_noninferiority, paired_randomization_test,
    query_level_metrics, save_query_metrics_csv,
)
from src.evaluation.evaluator import RetrievalEvaluator
from src.utils.io_utils import load_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--run", action="append", required=True, help="NAME=path/to/run.jsonl")
    parser.add_argument("--split", choices=("all", "dev", "test", "holdout"), default="all")
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bm25-name", default="bm25")
    parser.add_argument("--faiss-name", default="faiss")
    parser.add_argument("--graph-name", default="graphrag")
    args = parser.parse_args()

    qa = load_jsonl(args.qa)
    selected = {
        item["question_id"] for item in qa
        if args.split == "all" or item.get("split") == args.split
    }
    if not selected:
        raise RuntimeError(f"No QA items selected for split={args.split}")
    category_by_id = {item["question_id"]: item["category"] for item in qa if item["question_id"] in selected}
    split_by_id = {item["question_id"]: item.get("split", "unknown") for item in qa if item["question_id"] in selected}
    qrels = {
        qid: value for qid, value in QRelsBuilder.load_qrels_tsv(args.qrels).items()
        if qid in selected
    }
    systems: dict[str, dict[str, dict[str, float]]] = {}
    for value in args.run:
        if "=" not in value:
            raise ValueError("--run must use NAME=PATH syntax")
        name, path = value.split("=", 1)
        runs = [run for run in load_jsonl(path) if run["query_id"] in selected]
        run_ids = {run["query_id"] for run in runs}
        if run_ids != selected:
            raise RuntimeError(f"{name} run does not exactly cover selected split")
        RetrievalEvaluator(
            args.qrels, qa_dataset_path=args.qa, split=args.split,
            chunks_path=args.chunks,
        ).evaluate_run_file(path, retriever_name=name)
        systems[name] = query_level_metrics(runs, qrels)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    save_query_metrics_csv(systems, output_dir / f"query_metrics_{args.split}.csv", category_by_id, split_by_id)
    metrics = ("mrr_at_5", "mrr_at_10", "recall_at_5", "recall_at_10", "ndcg_at_10")
    report: dict = {
        "split": args.split, "query_count": len(selected), "samples": args.samples,
        "seed": args.seed, "confidence_intervals": {}, "paired_comparisons": {},
    }
    for system, rows in sorted(systems.items()):
        report["confidence_intervals"][system] = {
            metric: bootstrap_mean_ci(rows, metric, samples=args.samples, seed=args.seed)
            for metric in metrics
        }
    for left, right in combinations(sorted(systems), 2):
        report["paired_comparisons"][f"{left}_minus_{right}"] = {
            metric: {
                "bootstrap": paired_bootstrap(
                    systems[left], systems[right], metric, samples=args.samples, seed=args.seed,
                ),
                "randomization": paired_randomization_test(
                    systems[left], systems[right], metric, samples=args.samples, seed=args.seed,
                ),
            }
            for metric in metrics
        }
    required = {args.bm25_name, args.faiss_name, args.graph_name}
    if required <= set(systems):
        def slice_rows(name: str, categories: set[str]) -> dict[str, dict[str, float]]:
            return {
                qid: row for qid, row in systems[name].items()
                if category_by_id[qid] in categories
            }

        def mean(rows: dict[str, dict[str, float]]) -> float:
            return sum(row["ndcg_at_10"] for row in rows.values()) / len(rows)

        h1_categories = {"exact_match", "terminology_heavy"}
        h2_categories = {"paraphrase"}
        h3_categories = {"entity_relation", "multi_hop"}
        names = [args.bm25_name, args.faiss_name, args.graph_name]
        h1_rows = {name: slice_rows(name, h1_categories) for name in names}
        h2_rows = {name: slice_rows(name, h2_categories) for name in names}
        h3_rows = {name: slice_rows(name, h3_categories) for name in names}
        h1_comp = max((args.faiss_name, args.graph_name), key=lambda name: mean(h1_rows[name]))
        h2_comp = max((args.bm25_name, args.graph_name), key=lambda name: mean(h2_rows[name]))
        h3_comp = max((args.bm25_name, args.faiss_name), key=lambda name: mean(h3_rows[name]))
        h1 = paired_noninferiority(
            h1_rows[args.bm25_name], h1_rows[h1_comp], "ndcg_at_10",
            margin=0.03, samples=args.samples, seed=args.seed,
        )
        h2_boot = paired_bootstrap(
            h2_rows[args.faiss_name], h2_rows[h2_comp], "ndcg_at_10",
            samples=args.samples, seed=args.seed,
        )
        h3_boot = paired_bootstrap(
            h3_rows[args.graph_name], h3_rows[h3_comp], "ndcg_at_10",
            samples=args.samples, seed=args.seed,
        )
        h2_random = paired_randomization_test(
            h2_rows[args.faiss_name], h2_rows[h2_comp], "ndcg_at_10",
            samples=args.samples, seed=args.seed,
        )
        h3_random = paired_randomization_test(
            h3_rows[args.graph_name], h3_rows[h3_comp], "ndcg_at_10",
            samples=args.samples, seed=args.seed,
        )
        holm = holm_bonferroni({
            "H2": float(h2_random["p_value"]), "H3": float(h3_random["p_value"]),
        })
        h3_category_deltas = {
            category: mean(slice_rows(args.graph_name, {category})) - mean(slice_rows(h3_comp, {category}))
            for category in h3_categories
        }
        h2_supported = (
            h2_boot["mean_difference"] >= 0.01 and h2_boot["ci95_low"] > 0
            and holm["H2"]["reject_null"]
        )
        h3_supported = (
            h3_boot["mean_difference"] >= 0.01 and h3_boot["ci95_low"] > 0
            and min(h3_category_deltas.values()) >= 0 and holm["H3"]["reject_null"]
        )
        def outcome(supported: bool, delta: float) -> str:
            return "supported" if supported else "mixed_evidence" if delta > 0 else "rejected"
        report["hypothesis_decisions"] = {
            "H1": {
                "wording": CANONICAL_WORDING["H1"],
                "comparator": h1_comp, "test": h1,
                "outcome": "supported" if h1["noninferior"] else "mixed_evidence" if h1["mean_difference"] > -0.03 else "rejected",
            },
            "H2": {
                "wording": CANONICAL_WORDING["H2"],
                "comparator": h2_comp, "bootstrap": h2_boot, "randomization": h2_random,
                "holm": holm["H2"], "outcome": outcome(h2_supported, h2_boot["mean_difference"]),
            },
            "H3": {
                "wording": CANONICAL_WORDING["H3"],
                "comparator": h3_comp, "bootstrap": h3_boot, "randomization": h3_random,
                "category_deltas": h3_category_deltas, "holm": holm["H3"],
                "outcome": outcome(h3_supported, h3_boot["mean_difference"]),
            },
        }
    (output_dir / f"statistical_evaluation_{args.split}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"split": args.split, "queries": len(selected), "systems": sorted(systems)}, indent=2))


if __name__ == "__main__":
    main()
