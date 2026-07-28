from __future__ import annotations

import pytest

from src.benchmark.v2_validator import validate_benchmark


def fixtures():
    chunks = [{"chunk_id": f"c{i}", "document_id": f"d{i}", "text": f"Evidence quote {i}."} for i in range(40)]
    qa = []
    qrels = []
    categories = ["exact_lookup", "terminology", "paraphrase", "entity_relation", "multi_hop", "synthesis"]
    for i in range(30):
        category = categories[i % len(categories)]
        count = 3 if category == "synthesis" else 2 if category == "multi_hop" else 1
        ids = [f"c{(i+j)%40}" for j in range(count)]
        quotes = [f"Evidence quote {(i+j)%40}." for j in range(count)]
        qa.append({"question_id": f"q{i}", "category": category, "question": f"Question number {i} unique wording?",
                   "reference_answer": " ".join(quotes), "gold_evidence_ids": ids,
                   "source_document_ids": [f"d{(i+j)%40}" for j in range(count)], "supporting_evidence_quotes": quotes})
        qrels.extend({"query_id": f"q{i}", "chunk_id": cid, "relevance": 2} for cid in ids)
    return qa, qrels, chunks


def test_validator_accepts_aligned_draft():
    qa, qrels, chunks = fixtures()
    result = validate_benchmark(qa, qrels, chunks)
    assert result["qa_count"] == 30 and result["unresolved_gold_chunks"] == 0


@pytest.mark.parametrize("mutation,error", [
    (lambda q, r: q[0].update(question=q[1]["question"]), "duplicate questions"),
    (lambda q, r: q[0].update(gold_evidence_ids=["missing"]), "unresolved gold"),
    (lambda q, r: q[0].update(supporting_evidence_quotes=["wrong"]), "quote does not occur"),
    (lambda q, r: r.append(dict(r[0])), "duplicate qrels"),
])
def test_validator_fails_closed(mutation, error):
    qa, qrels, chunks = fixtures()
    mutation(qa, qrels)
    with pytest.raises(ValueError, match=error):
        validate_benchmark(qa, qrels, chunks)
