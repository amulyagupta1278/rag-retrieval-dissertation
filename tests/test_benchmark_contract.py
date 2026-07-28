import json

from src.benchmark.benchmark_contract import validate_question
from src.benchmark.qa_generator import QAItem, QAGenerator


def test_five_folds_are_balanced_and_deterministic():
    items = [
        QAItem(
            f"q_{category}_{index}", "What supported fact appears here?", category,
            "easy", "Supported fact", [f"c_{category}_{index}"], [f"d_{category}_{index}"],
        )
        for category in ("exact_match", "terminology_heavy", "paraphrase", "entity_relation", "multi_hop")
        for index in range(20)
    ]
    QAGenerator.assign_stratified_folds(items, folds=5, seed=42)
    first = {item.question_id: item.fold_id for item in items}
    QAGenerator.assign_stratified_folds(items, folds=5, seed=42)
    assert first == {item.question_id: item.fold_id for item in items}
    for category in {item.category for item in items}:
        assert [item.fold_id for item in items if item.category == category].count(0) == 4
        assert {item.split for item in items} == {"dev"}


def test_question_contract_rejects_schema_leakage_and_bad_definition():
    chunks = {"c1": {"chunk_id": "c1", "doc_id": "d1", "text": "Mission support is available."}}
    item = {
        "question_id": "q1", "question": "What is Mission Support?", "category": "exact_match",
        "reference_answer": "Scheme: Mission Support Ministry: Example", "gold_evidence_ids": ["c1"],
        "source_doc_ids": ["d1"], "extra_meta": {},
    }
    errors = validate_question(item, chunks)
    assert any("schema/JSON leakage" in error for error in errors)


def test_cross_scheme_contract_requires_two_supported_clauses():
    chunks = {
        "c1": {"chunk_id": "c1", "doc_id": "d1", "scheme_name": "Alpha", "text": "Alpha supports rural women through Agency Z."},
        "c2": {"chunk_id": "c2", "doc_id": "d2", "scheme_name": "Beta", "text": "Beta trains rural workers through Agency Z."},
    }
    item = {
        "question_id": "q1", "question": "How do Alpha and Beta connect through Agency Z?",
        "category": "multi_hop", "reference_answer": "Alpha supports rural women through Agency Z. Additionally, Unsupported claim.",
        "gold_evidence_ids": ["c1", "c2"], "source_doc_ids": ["d1", "d2"],
        "extra_meta": {"bridge_entity": "Agency Z", "scheme_names": ["Alpha", "Beta"]},
    }
    assert any("two answer clauses" in error for error in validate_question(item, chunks))
