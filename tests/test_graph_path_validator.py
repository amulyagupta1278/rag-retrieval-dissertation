from __future__ import annotations

import copy

import pytest

from src.benchmark.graph_path_validator import GraphPathError, validate_graph_path_item


def valid():
    chunks = {
        "c1": {"chunk_id": "c1", "document_id": "d1", "text": "Scheme Alpha belongs to Ministry Named. Alpha provides banking."},
        "c2": {"chunk_id": "c2", "document_id": "d2", "text": "Scheme Beta belongs to Ministry Named. Beta provides credit."},
    }
    item = {
        "question": "What does Scheme Alpha provide, and which sibling programme provides credit?",
        "reference_answer": "Alpha provides banking. Beta provides credit.",
        "answer_clause_map": [{"clause": "Alpha provides banking.", "evidence_id": "c1"},
                              {"clause": "Beta provides credit.", "evidence_id": "c2"}],
        "graph_path": {"seed_entity": "Scheme Alpha", "seed_aliases": ["Alpha"],
                       "bridge_entity": "Ministry Named", "bridge_aliases": [], "bridge_type": "ministry",
                       "target_entities": ["Scheme Alpha", "Scheme Beta"],
                       "gold_path": [{"node": "Scheme Alpha", "type": "scheme"},
                                     {"node": "Ministry Named", "type": "ministry"},
                                     {"node": "Scheme Beta", "type": "scheme"}],
                       "gold_evidence_ids": ["c1", "c2"], "single_chunk_sufficient": False},
    }
    return item, chunks, {"Scheme Alpha", "Scheme Beta", "Ministry Named"}


def make_target_absent(item, chunks, entities):
    item["graph_path"]["target_entities"][1] = "Ghost Scheme"
    item["graph_path"]["gold_path"][2]["node"] = "Ghost Scheme"


def test_valid_graph_path():
    validate_graph_path_item(*valid())


@pytest.mark.parametrize("mutate,error", [
    (lambda i, c, e: c["c2"].update(text="Scheme Beta has no named ministry. Beta provides credit."), "bridge missing"),
    (lambda i, c, e: i["graph_path"].update(seed_aliases=["unsupported acronym"]), "unsupported seed alias"),
    (lambda i, c, e: c["c2"].update(document_id="d1"), "documents must be distinct"),
    (lambda i, c, e: i.update(question="How do Scheme Alpha and Scheme Beta differ?"), "names both target"),
    (lambda i, c, e: i["graph_path"]["gold_path"][1].update(node="Wrong Ministry"), "disconnected"),
    (lambda i, c, e: i["graph_path"].update(bridge_entity="government"), "generic stop-entity"),
    (lambda i, c, e: i.update(answer_clause_map=i["answer_clause_map"][:1]), "clauses are not mapped"),
    (make_target_absent, "absent from corpus"),
    (lambda i, c, e: c["c1"].update(text=c["c1"]["text"] + " Beta provides credit."), "one chunk alone"),
])
def test_rejections(mutate, error):
    item, chunks, entities = valid()
    mutate(item, chunks, entities)
    with pytest.raises(GraphPathError, match=error):
        validate_graph_path_item(item, chunks, entities)
