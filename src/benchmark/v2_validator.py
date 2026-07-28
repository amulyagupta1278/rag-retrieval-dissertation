"""Fail-closed QA draft and qrels audits."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

from src.contracts._validation import PLACEHOLDER_RE
from src.ingestion.v2_pipeline import FORBIDDEN, LABEL_LINE


def validate_benchmark(
    qa: list[dict[str, Any]], qrels: list[dict[str, Any]], chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    if not 30 <= len(qa) <= 40:
        raise ValueError(f"QA draft must contain 30..40 items; got {len(qa)}")
    chunk_map = {x["chunk_id"]: x for x in chunks}
    if len(chunk_map) != len(chunks):
        raise ValueError("duplicate chunk IDs")
    qids = [x["question_id"] for x in qa]
    if len(qids) != len(set(qids)):
        raise ValueError("duplicate question IDs")
    normalized = [re.sub(r"\W+", " ", x["question"].lower()).strip() for x in qa]
    if len(normalized) != len(set(normalized)):
        raise ValueError("exact duplicate questions")
    near = []
    for left in range(len(qa)):
        for right in range(left + 1, len(qa)):
            score = SequenceMatcher(None, normalized[left], normalized[right]).ratio()
            if score >= 0.88:
                near.append({"left": qids[left], "right": qids[right], "ratio": round(score, 4)})
    for item in qa:
        combined = " ".join((item["question"], item["reference_answer"], *item["supporting_evidence_quotes"]))
        if FORBIDDEN.search(combined) or LABEL_LINE.search(combined) or PLACEHOLDER_RE.search(combined):
            raise ValueError(f"{item['question_id']} contains JSON/schema/placeholder leakage")
        gold = item["gold_evidence_ids"]
        if any(chunk_id not in chunk_map for chunk_id in gold):
            raise ValueError(f"{item['question_id']} has unresolved gold chunk")
        if len(gold) != len(item["supporting_evidence_quotes"]):
            raise ValueError(f"{item['question_id']} evidence quote count mismatch")
        for chunk_id, quote in zip(gold, item["supporting_evidence_quotes"], strict=True):
            if quote not in chunk_map[chunk_id]["text"]:
                raise ValueError(f"{item['question_id']} quote does not occur in {chunk_id}")
            if chunk_map[chunk_id]["document_id"] not in item["source_document_ids"]:
                raise ValueError(f"{item['question_id']} source-document alignment failure")
        if item["reference_answer"] != " ".join(item["supporting_evidence_quotes"]):
            raise ValueError(f"{item['question_id']} answer is not fully extractively supported")
        if item["category"] == "multi_hop" and len(set(item["source_document_ids"])) < 2:
            raise ValueError(f"{item['question_id']} is not cross-document multi-hop")
        if item["category"] == "synthesis" and len(gold) < 3:
            raise ValueError(f"{item['question_id']} synthesis uses fewer than three chunks")
    pairs = [(x["query_id"], x["chunk_id"]) for x in qrels]
    if len(pairs) != len(set(pairs)):
        raise ValueError("duplicate qrels judgments")
    if {x["query_id"] for x in qrels} != set(qids):
        raise ValueError("qrels and QA query sets differ")
    if any(x["chunk_id"] not in chunk_map for x in qrels):
        raise ValueError("qrels contain unknown chunk")
    gold_pairs = {(item["question_id"], chunk_id) for item in qa for chunk_id in item["gold_evidence_ids"]}
    grade2 = {(x["query_id"], x["chunk_id"]) for x in qrels if x["relevance"] == 2}
    if grade2 != gold_pairs:
        raise ValueError("grade-2 qrels must equal explicit gold evidence")
    reuse = Counter(chunk_id for item in qa for chunk_id in item["gold_evidence_ids"])
    return {
        "qa_count": len(qa), "category_counts": dict(sorted(Counter(x["category"] for x in qa).items())),
        "qrels_counts": {str(k): v for k, v in sorted(Counter(x["relevance"] for x in qrels).items())},
        "near_duplicates": near, "gold_chunk_reuse": dict(sorted(reuse.items())),
        "source_document_count": len({doc for item in qa for doc in item["source_document_ids"]}),
        "raw_json_leaks": 0, "schema_label_leaks": 0, "placeholder_answers": 0,
        "unresolved_gold_chunks": 0, "evidence_quote_alignment_failures": 0,
    }
