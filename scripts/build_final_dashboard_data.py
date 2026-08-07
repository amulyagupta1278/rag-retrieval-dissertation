#!/usr/bin/env python3
"""Build browser-ready dissertation dashboard data from frozen final artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission/dashboard/data.js"


def load(path: str):
    return json.loads((ROOT / path).read_text())


def load_jsonl(path: str):
    return [json.loads(line) for line in (ROOT / path).read_text().splitlines() if line.strip()]


def metrics(row: dict) -> dict:
    return {
        "mrr": row["mrr@10"],
        "ndcg": row["ndcg@10"],
        "recall": row["recall@10"],
        "precision": row["precision@10"],
        "hit": row["hit@10"],
    }


def main() -> None:
    r4 = load("runs/phase8_r4_human_validated/retrieval_evaluation/metrics.json")
    holdout = load("runs/phase8_option_b_holdout/retrieval/metrics.json")
    holdout_stats = load("runs/phase8_option_b_holdout/analysis/descriptive_statistics.json")
    holdout_queries = {r["question_id"]: r for r in load_jsonl("runs/phase8_option_b_holdout/freeze/qa_holdout_12.jsonl")}
    holdout_per_query = load_jsonl("runs/phase8_option_b_holdout/retrieval/per_query.jsonl")
    h5 = load("runs/phase9_h5_followup/analysis/h5_final_results.json")
    h5b = load("runs/phase9_h5_followup/analysis/h5b_abstention_results.json")
    prompt = load("runs/phase8_r4_improvements/prompt_rag_r4_v2_full/summary.json")

    labels = {
        "bm25": "BM25",
        "faiss_cosine": "FAISS cosine",
        "graph_v4": "Entity Graph v4",
        "hybrid_r4": "Weighted hybrid",
        "prompt_rag_claude": "Prompt-RAG",
    }

    locked = []
    locked_categories = {}
    for key, label in labels.items():
        system = r4["systems"][key]
        locked.append({"key": key, "label": label, **metrics(system["locked_test"])})
        locked_categories[key] = {
            category: metrics(values)
            for category, values in system["locked_test_by_category"].items()
        }

    holdout_rows = [
        {"key": key, "label": labels[key], **metrics(values)}
        for key, values in holdout["metrics"].items()
    ]
    holdout_rows.append({
        "key": "prompt_rag_claude",
        "label": labels["prompt_rag_claude"],
        "excluded": True,
        "reason": "Zero-retry protocol violation; excluded from canonical inference",
    })

    query_rows = []
    for row in holdout_per_query:
        q = holdout_queries.get(row["query_id"], {})
        query_rows.append({
            "query_id": row["query_id"],
            "question": q.get("question", q.get("query", "")),
            "category": row["category"],
            "system": row["system"],
            **metrics(row),
        })

    hypotheses = [
        {"id": "H1", "claim": "BM25 competitive with FAISS on exact and terminology queries", "verdict": "Partial support", "status": "inconclusive", "evidence": "Exact-match tie at 1.000; terminology 0.250 vs 0.417", "limitation": "Equivalence interval not contained within ±0.05; n=4."},
        {"id": "H2", "claim": "FAISS outperforms BM25 on paraphrase queries", "verdict": "Not supported", "status": "not-supported", "evidence": "Holdout BM25 0.667 vs FAISS 0.500", "limitation": "Paraphrase construct retained exact document terminology."},
        {"id": "H3", "claim": "Graph retrieval leads entity-relation and multi-hop queries", "verdict": "Strongest directional support", "status": "directional", "evidence": "Graph led both holdout categories: 1.000 and 0.667", "limitation": "Two questions per category; not confirmatory."},
        {"id": "H4", "claim": "Hybrid fusion achieves highest aggregate MRR", "verdict": "Not supported", "status": "not-supported", "evidence": "BM25 0.6667 vs hybrid 0.6597", "limitation": "Canonical hybrid had three components; H4 specified two."},
        {"id": "H5", "claim": "Faithfulness is independent of retrieval quality", "verdict": "Not estimable", "status": "not-estimable", "evidence": "Faithfulness SD 0.0111 vs preregistered 0.10 gate", "limitation": "Severe ceiling effect; only two distinct values."},
    ]

    payload = {
        "meta": {
            "title": "Vector-Free Retrieval Strategies for RAG",
            "student": "Amulya Gupta · 2024AB05200",
            "commit": "22cf0bb6f0433a21557beda5fc297e037c5a844b",
            "generated_from": "Frozen local dissertation artifacts",
        },
        "scope": {
            "pilot": {"documents": 22, "chunks": 140, "questions": 34, "role": "Development provenance"},
            "r4": {"documents": 130, "chunks": 954, "questions": 100, "development": 60, "locked": 40, "role": "Main benchmark"},
            "holdout": {"questions": 12, "judgements": 21, "categories": 6, "role": "Canonical verdict evidence"},
            "h5": {"answers": 150, "claims": 301, "questions": 30, "role": "Faithfulness panel"},
        },
        "systems": labels,
        "locked": {"badge": "LOCKED TEST · n=40", "rows": locked, "categories": locked_categories},
        "holdout": {
            "badge": "CANONICAL HOLDOUT · n=12",
            "rows": holdout_rows,
            "categories": {
                key: {category: metrics(values) for category, values in categories.items()}
                for key, categories in holdout_stats["category_metrics"].items()
            },
            "confidence_intervals": holdout_stats["confidence_intervals"],
            "queries": query_rows,
        },
        "hypotheses": hypotheses,
        "h5": {
            "badge": "PHASE 9 · HUMAN REVIEWED",
            "faithfulness": h5["aggregate_claim_weighted_faithfulness"],
            "sd": h5["faithfulness_sd"],
            "required_sd": 0.10,
            "decision": h5["decision"],
            "answers": 150,
            "claim_bearing": h5["answer_n"],
            "abstentions": h5["excluded_no_verifiable_claims_n"],
            "claims": h5["claim_counts"],
            "rho": h5["spearman_rho"],
            "ci95": h5["ci95"],
            "abstention_by_category": h5b["by_category"],
            "abstention_by_system": h5b["by_system"],
            "h5b_note": h5b["confirmatory_use"],
        },
        "operations": {
            "prompt_rag": {
                "mean_latency_seconds": prompt["mean_latency_seconds"],
                "cost_usd": prompt["cost_usd"],
                "queries": 100,
                "failures": prompt["failure_n"],
                "retries": prompt["retry_n"],
            },
            "holdout_prompt_rag": {"completed_under_contract": 1, "planned": 12, "retries": 0, "canonical": False},
        },
        "architecture": [
            {"id": "corpus", "label": "Corpus", "detail": "130 public-policy documents · 954 section-aware chunks"},
            {"id": "bm25", "label": "BM25", "detail": "k1=1.2 · b=0.75 · exact terminology"},
            {"id": "faiss", "label": "FAISS", "detail": "MiniLM 384-d · normalised IndexFlatIP · exact cosine"},
            {"id": "graph", "label": "Entity Graph v4", "detail": "3,781 nodes · 26,430 edges · two-hop traversal"},
            {"id": "hybrid", "label": "Weighted RRF", "detail": "k=10 · weights 1.00 / 0.25 / 0.10"},
            {"id": "prompt", "label": "Prompt-RAG", "detail": "Claude Haiku 4.5 · 25–50 candidates · temperature 0"},
            {"id": "evaluation", "label": "Evaluation", "detail": "MRR · nDCG · Recall · bootstrap · frozen controls"},
        ],
        "sources": [
            "runs/phase8_r4_human_validated/retrieval_evaluation/metrics.json",
            "runs/phase8_option_b_holdout/retrieval/metrics.json",
            "runs/phase8_option_b_holdout/analysis/descriptive_statistics.json",
            "runs/phase9_h5_followup/analysis/h5_final_results.json",
            "runs/phase9_h5_followup/analysis/h5b_abstention_results.json",
            "docs/PHASE8_FINAL_HYPOTHESIS_VERDICTS.md",
            "docs/PHASE9_H5_FINAL_REPORT.md",
        ],
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    payload["meta"]["payload_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.DASHBOARD_DATA=" + json.dumps(payload, ensure_ascii=False) + ";\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
