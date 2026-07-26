"""Validity tests for corrected corpus-only entity Graph V3 candidate."""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import pytest

from src.retrievers.entity_graph_v3 import (
    EntityMatcher,
    build_entity_registry,
    build_graph,
    canonicalize_organization_entities,
    apply_corpus_backed_scheme_aliases,
    normalize_text,
    organization_key,
    rank_query,
)
from src.utils.atomic_io import stable_json
from src.utils.hashing import sha256_file, sha256_text


ROOT = Path(__file__).parents[1]


def config() -> dict:
    return json.loads((ROOT / "configs/entity_graph_v3_candidate.json").read_text(encoding="utf-8"))


def document(text: str, *, title: str = "Useful Scheme", ministry: str = "Ministry of Useful Affairs", department: str = "Useful Department") -> dict:
    return {
        "document_id": "doc-1",
        "source_id": "source-1",
        "title": title,
        "ministry": ministry,
        "department": department,
        "text": text,
    }


def chunk(chunk_id: str, text: str, *, document_id: str = "doc-1") -> dict:
    return {"chunk_id": chunk_id, "document_id": document_id, "text": text}


def source(**overrides: object) -> dict:
    row = {
        "source_id": "source-1",
        "document_id": "doc-1",
        "scheme_short_title": "US",
        "implementing_agency": "",
        "target_beneficiaries": [],
    }
    row.update(overrides)
    return row


def registry_record(
    entity_id: str,
    label: str,
    *,
    aliases: list[str] | None = None,
    entity_type: str = "scheme",
    df: int = 1,
    trusted: list[str] | None = None,
) -> dict:
    return {
        "entity_id": entity_id,
        "canonical_label": label,
        "normalized_label": normalize_text(label),
        "entity_type": entity_type,
        "aliases": aliases or [],
        "source_document_ids": ["doc-1"],
        "source_field": ["test"],
        "extraction_rule": ["test"],
        "corpus_evidence": [{"document_id": "doc-1", "source_field": "test", "extraction_rule": "test", "excerpt": label}],
        "document_frequency": df,
        "status": "accepted",
        "rejection_reason": "",
        "registry_version": "entity-registry-v3-candidate",
        "trusted_metadata_document_ids": trusted or [],
    }


def edge(edge_id: str, source_node: str, target_node: str, edge_type: str = "MENTIONED_IN") -> dict:
    return {"edge_id": edge_id, "source": source_node, "target": target_node, "edge_type": edge_type}


def build_small_registry(text: str, **source_overrides: object) -> tuple[list[dict], dict]:
    doc = document(text)
    return build_entity_registry(
        chunks=[chunk("chunk-1", text)],
        documents=[doc],
        source_metadata=[source(**source_overrides)],
        config=config(),
    )


def test_banned_stopwords_and_observed_invalid_seeds_are_rejected() -> None:
    seeds = "AND AS IN OF IT ID IV VI NA PM"
    registry, audit = build_small_registry(f"Useful Scheme. {seeds}")
    accepted = {row["normalized_label"] for row in registry if row["status"] == "accepted"}
    for seed in seeds.casefold().split():
        assert seed not in accepted
    assert audit["banned_token_audit"]["passed"] is True
    assert audit["banned_token_audit"]["surviving_accepted"] == []


def test_roman_numeral_rejected() -> None:
    registry, _ = build_small_registry("Useful Scheme. XII")
    row = next(row for row in registry if row["normalized_label"] == "xii")
    assert row["status"] == "rejected"
    assert row["rejection_reason"] == "roman_numeral"


def test_generic_unpaired_acronym_rejected() -> None:
    registry, _ = build_small_registry("Useful Scheme. XYZ appears without a long form.")
    row = next(row for row in registry if row["normalized_label"] == "xyz")
    assert row["status"] == "rejected"
    assert row["rejection_reason"] == "unpaired_uppercase_token"


def test_corpus_backed_acronym_accepted() -> None:
    registry, _ = build_small_registry("National Health Authority (NHA) administers Useful Scheme.")
    row = next(row for row in registry if "NHA" in row["aliases"])
    assert row["status"] == "accepted"
    assert row["canonical_label"] == "National Health Authority"


def test_banned_acronym_alias_rejects_controlled_entity() -> None:
    registry, audit = build_small_registry("Information Technology (IT) is discussed.")
    row = next(row for row in registry if row["normalized_label"] == "information technology")
    assert row["status"] == "rejected"
    assert row["rejection_reason"] == "banned_alias"
    assert audit["banned_token_audit"]["surviving_accepted"] == []


def test_official_phrase_with_internal_of_and_preserved() -> None:
    doc = document("Official text.", ministry="Ministry of Skill Development and Entrepreneurship")
    registry, _ = build_entity_registry(chunks=[chunk("chunk-1", "Official text.")], documents=[doc], source_metadata=[source()], config=config())
    row = next(row for row in registry if row["normalized_label"] == "ministry of skill development and entrepreneurship")
    assert row["status"] == "accepted"


def test_normalization_collision_has_one_winner_and_audited_loser() -> None:
    doc = document("Ministry of Useful Affairs.")
    registry, audit = build_entity_registry(
        chunks=[chunk("chunk-1", doc["text"])], documents=[doc],
        source_metadata=[source(implementing_agency="Ministry-of-Useful Affairs")], config=config(),
    )
    normalized = "ministry of useful affairs"
    rows = [row for row in registry if row["normalized_label"] == normalized]
    assert sum(row["status"] == "accepted" for row in rows) == 1
    assert rows[[row["status"] for row in rows].index("accepted")]["entity_type"] == "ministry"
    assert audit["normalization_collisions"]


@pytest.mark.parametrize("query", ["income", "initiative", "insurance"])
def test_in_does_not_match_inside_larger_token(query: str) -> None:
    matcher = EntityMatcher([registry_record("entity-in", "in")])
    assert matcher.match(query) == []


def test_us_does_not_match_various() -> None:
    matcher = EntityMatcher([registry_record("entity-us", "us")])
    assert matcher.match("various") == []


def test_pm_does_not_match_pmay() -> None:
    matcher = EntityMatcher([registry_record("entity-pm", "pm")])
    assert matcher.match("PMAY") == []


def test_punctuation_separated_official_alias_matches() -> None:
    matcher = EntityMatcher([registry_record("entity-nha", "National Health Authority")])
    matches = matcher.match("Does National—Health, Authority administer it?")
    assert [match.entity_id for match in matches] == ["entity-nha"]


def test_longest_alias_wins_when_aliases_overlap() -> None:
    matcher = EntityMatcher([
        registry_record("entity-long", "Pradhan Mantri Awas Yojana"),
        registry_record("entity-short", "Awas Yojana"),
    ])
    assert [match.entity_id for match in matcher.match("Pradhan Mantri Awas Yojana")] == ["entity-long"]


def test_alias_and_canonical_form_do_not_double_count_seed() -> None:
    matcher = EntityMatcher([registry_record("entity-apy", "Atal Pension Yojana", aliases=["APY"])])
    matches = matcher.match("Atal Pension Yojana, APY")
    assert [match.entity_id for match in matches] == ["entity-apy"]


def test_same_alias_prefers_unique_higher_priority_entity() -> None:
    matcher = EntityMatcher([
        registry_record("entity-controlled", "Long Form", aliases=["ABC"], entity_type="controlled_acronym"),
        registry_record("entity-scheme", "Official Scheme", aliases=["ABC"], entity_type="scheme"),
    ])
    assert [match.entity_id for match in matcher.match("ABC")] == ["entity-scheme"]


def test_mention_edges_require_exact_token_sequence() -> None:
    registry = [registry_record("entity-in", "in")]
    _, edges, chunk_entities, _ = build_graph(chunks=[chunk("c-income", "income insurance"), chunk("c-in", "apply in person")], registry=registry)
    assert chunk_entities["c-income"] == []
    assert chunk_entities["c-in"] == ["entity-in"]
    mentions = [row for row in edges if row["edge_type"] == "MENTIONED_IN"]
    assert len(mentions) == 1 and mentions[0]["target"] == "chunk:c-in"


def test_cooccurrence_is_same_chunk_only_not_document_wide() -> None:
    registry = [registry_record("entity-a", "Alpha Agency"), registry_record("entity-b", "Beta Board")]
    _, edges, _, _ = build_graph(
        chunks=[chunk("c-1", "Alpha Agency acts."), chunk("c-2", "Beta Board acts.")], registry=registry,
    )
    assert not [row for row in edges if row["edge_type"] == "CO_OCCURS_WITH"]


def test_trusted_metadata_link_is_anchored_not_document_wide() -> None:
    registry = [registry_record("entity-meta", "Metadata Name", trusted=["doc-1"])]
    _, _, chunk_entities, _ = build_graph(
        chunks=[chunk("c-1", "first chunk"), chunk("c-2", "second chunk")], registry=registry,
    )
    assert chunk_entities == {"c-1": ["entity-meta"], "c-2": []}


def test_cooccurrence_edge_exact_and_not_symmetrically_duplicated() -> None:
    registry = [registry_record("entity-a", "Alpha Agency"), registry_record("entity-b", "Beta Board")]
    _, edges, _, _ = build_graph(chunks=[chunk("c-1", "Alpha Agency works with Beta Board.")], registry=registry)
    cooccurs = [row for row in edges if row["edge_type"] == "CO_OCCURS_WITH"]
    assert len(cooccurs) == 1
    assert cooccurs[0]["source"] < cooccurs[0]["target"]
    assert cooccurs[0]["supporting_chunk_ids"] == ["c-1"]


def test_rejected_entity_creates_no_node_or_edge() -> None:
    rejected = registry_record("entity-bad", "Bad")
    rejected["status"] = "rejected"
    rejected["rejection_reason"] = "test"
    nodes, edges, _, _ = build_graph(chunks=[chunk("c-1", "Bad")], registry=[rejected])
    assert [node for node in nodes if node["node_type"] == "entity"] == []
    assert edges == []


def test_graph_serialization_reload_equality_and_deterministic_hash() -> None:
    registry = [registry_record("entity-a", "Alpha Agency"), registry_record("entity-b", "Beta Board")]
    first = build_graph(chunks=[chunk("c-1", "Alpha Agency and Beta Board")], registry=registry)
    second = build_graph(chunks=[chunk("c-1", "Alpha Agency and Beta Board")], registry=list(reversed(registry)))
    assert first[:3] == second[:3]
    encoded = stable_json(first[:3])
    assert json.loads(encoded) == json.loads(stable_json(second[:3]))
    assert sha256_text(encoded) == sha256_text(stable_json(second[:3]))


def scorer(records: list[dict], edges: list[dict], query: str, n_chunks: int = 10):
    return rank_query(query=query, matcher=EntityMatcher(records), edges=edges, n_chunks=n_chunks)


def test_hand_computed_one_hop_score() -> None:
    record = registry_record("seed", "Alpha", df=1)
    ranking, _ = scorer([record], [edge("m", "entity:seed", "chunk:c1")], "Alpha")
    weight = math.log(11 / 2) + 1
    assert ranking == [{"chunk_id": "c1", "rank": 1, "score": pytest.approx(weight * 0.5)}]


def test_hand_computed_two_hop_score() -> None:
    records = [registry_record("seed", "Alpha", df=1), registry_record("bridge", "Bridge")]
    edges = [edge("c", "entity:seed", "entity:bridge", "CO_OCCURS_WITH"), edge("m", "entity:bridge", "chunk:c1")]
    ranking, trace = scorer(records, edges, "Alpha")
    weight = math.log(11 / 2) + 1
    assert ranking[0]["score"] == pytest.approx(weight * 0.25)
    assert trace["contributions"]["c1"][0]["distance"] == 2
    assert trace["contributions"]["c1"][0]["path"] == ["entity:seed", "entity:bridge", "chunk:c1"]


def test_paths_deeper_than_two_are_excluded() -> None:
    records = [registry_record("seed", "Alpha")]
    edges = [
        edge("1", "entity:seed", "entity:b1", "CO_OCCURS_WITH"),
        edge("2", "entity:b1", "entity:b2", "CO_OCCURS_WITH"),
        edge("3", "entity:b2", "chunk:c1"),
    ]
    ranking, _ = scorer(records, edges, "Alpha")
    assert ranking == []


def test_seed_visited_maps_are_independent() -> None:
    records = [registry_record("s1", "Alpha"), registry_record("s2", "Beta")]
    edges = [
        edge("1", "entity:s1", "entity:bridge", "CO_OCCURS_WITH"),
        edge("2", "entity:s2", "entity:bridge", "CO_OCCURS_WITH"),
        edge("3", "entity:bridge", "chunk:c1"),
    ]
    ranking, trace = scorer(records, edges, "Alpha Beta")
    assert ranking and len(trace["contributions"]["c1"]) == 2


def test_three_seed_chunk_outranks_one_seed_chunk() -> None:
    records = [registry_record(f"s{index}", label) for index, label in enumerate(("Alpha", "Beta", "Gamma"), 1)]
    edges = [
        edge("a", "entity:s1", "chunk:one"),
        edge("b", "entity:s1", "chunk:three"),
        edge("c", "entity:s2", "chunk:three"),
        edge("d", "entity:s3", "chunk:three"),
    ]
    ranking, _ = scorer(records, edges, "Alpha Beta Gamma")
    assert [row["chunk_id"] for row in ranking[:2]] == ["three", "one"]


def test_same_seed_path_is_not_double_counted_and_cycle_terminates() -> None:
    records = [registry_record("seed", "Alpha")]
    edges = [
        edge("1", "entity:seed", "entity:bridge", "CO_OCCURS_WITH"),
        edge("1-duplicate", "entity:seed", "entity:bridge", "CO_OCCURS_WITH"),
        edge("2", "entity:bridge", "entity:seed", "CO_OCCURS_WITH"),
        edge("3", "entity:bridge", "chunk:c1"),
    ]
    ranking, trace = scorer(records, edges, "Alpha")
    assert len(trace["contributions"]["c1"]) == 1
    assert len(ranking) == 1


def test_deterministic_chunk_id_tie() -> None:
    records = [registry_record("seed", "Alpha")]
    edges = [edge("1", "entity:seed", "chunk:z"), edge("2", "entity:seed", "chunk:a")]
    ranking, _ = scorer(records, edges, "Alpha")
    assert [row["chunk_id"] for row in ranking] == ["a", "z"]


def test_no_seed_returns_empty_without_zero_padding() -> None:
    records = [registry_record("seed", "Alpha")]
    ranking, trace = scorer(records, [edge("1", "entity:seed", "chunk:c1")], "unrelated words")
    assert ranking == []
    assert trace == {"status": "no_valid_seed", "matched_seeds": [], "contributions": {}}


def test_builder_api_has_no_benchmark_inputs() -> None:
    parameters = set(inspect.signature(build_entity_registry).parameters)
    assert parameters == {"chunks", "documents", "source_metadata", "config"}
    assert not parameters & {"qa", "qrels", "questions", "gold_chunks", "graph_path", "categories", "rankings"}


def test_modifying_qa_and_qrels_changes_no_graph_artifact_or_registry() -> None:
    docs = [document("National Health Authority (NHA) administers Useful Scheme.")]
    chunks = [chunk("c-1", docs[0]["text"])]
    qa = [{"question_id": "q1", "graph_path": {"seed_entity": "LEAK"}}]
    qrels = [{"query_id": "q1", "chunk_id": "gold-secret", "relevance": 2}]
    first_registry, _ = build_entity_registry(chunks=chunks, documents=docs, source_metadata=[source()], config=config())
    first_graph = build_graph(chunks=chunks, registry=first_registry)[:3]
    qa[0]["graph_path"]["seed_entity"] = "DIFFERENT LEAK"
    qrels[0]["chunk_id"] = "different-gold-secret"
    second_registry, _ = build_entity_registry(chunks=chunks, documents=docs, source_metadata=[source()], config=config())
    second_graph = build_graph(chunks=chunks, registry=second_registry)[:3]
    assert stable_json(first_registry) == stable_json(second_registry)
    assert stable_json(first_graph) == stable_json(second_graph)


def test_graph_configuration_has_no_gold_ids_or_benchmark_metadata() -> None:
    text = (ROOT / "configs/entity_graph_v3_candidate.json").read_text(encoding="utf-8")
    assert "pilot-v2-doc-" not in text
    assert "graph_path" not in text
    assert "reference_answer" not in text
    assert "qrels" not in text


def test_registry_provenance_has_no_graph_path_after_build() -> None:
    registry, _ = build_small_registry("National Health Authority (NHA) administers Useful Scheme.")
    serialized = stable_json(registry)
    assert "graph_path" not in serialized
    assert "reference_answer" not in serialized
    assert "gold" not in serialized


def v31_equivalences() -> list[dict]:
    cfg = json.loads((ROOT / "configs/entity_graph_v3_1_frozen.json").read_text(encoding="utf-8"))
    return cfg["organization_canonicalization"]["equivalences"]


def org_record(entity_id: str, label: str, entity_type: str, document_id: str) -> dict:
    row = registry_record(entity_id, label, entity_type=entity_type, trusted=[document_id])
    row["source_document_ids"] = [document_id]
    row["trusted_metadata_document_ids"] = [document_id]
    row["corpus_evidence"] = [{
        "document_id": document_id,
        "source_field": "document.ministry",
        "extraction_rule": "structured_ministry",
        "excerpt": label,
    }]
    return row


def org_documents() -> list[dict]:
    return [
        {"document_id": "doc-a", "text": "Ministry Of Housing & Urban Affairs."},
        {"document_id": "doc-b", "text": "Ministry Of Housing And Urban Affairs."},
        {"document_id": "doc-c", "text": "Department of Financial Service."},
        {"document_id": "doc-d", "text": "Department of Financial Services (DFS)."},
    ]


def test_organization_ampersand_and_variants_merge_to_one_entity() -> None:
    registry, audit = canonicalize_organization_entities(
        registry=[
            org_record("ministry-amp", "Ministry Of Housing & Urban Affairs", "ministry", "doc-a"),
            org_record("agency-and", "Ministry Of Housing And Urban Affairs", "implementing_agency", "doc-b"),
        ],
        documents=org_documents(), equivalences=v31_equivalences(),
    )
    accepted = [row for row in registry if row["status"] == "accepted"]
    assert len(accepted) == 1
    assert accepted[0]["canonical_label"] == "Ministry Of Housing And Urban Affairs"
    assert organization_key("Ministry Of Housing & Urban Affairs") == organization_key("Ministry Of Housing And Urban Affairs")
    assert len(audit["merge_map"]) == 2


def test_service_services_approved_alias_resolves_one_department() -> None:
    registry, _ = canonicalize_organization_entities(
        registry=[
            org_record("department-singular", "Department of Financial Service", "department", "doc-c"),
            org_record("controlled-plural", "Department of Financial Services", "controlled_acronym", "doc-d"),
        ],
        documents=org_documents(), equivalences=v31_equivalences(),
    )
    accepted = [row for row in registry if row["status"] == "accepted"]
    assert len(accepted) == 1
    assert accepted[0]["entity_type"] == "department"
    assert "Department of Financial Service" in accepted[0]["aliases"]


def test_unrelated_similar_organizations_remain_separate() -> None:
    registry, audit = canonicalize_organization_entities(
        registry=[
            org_record("min-finance", "Ministry Of Finance", "ministry", "doc-a"),
            org_record("dep-finance", "Department Of Finance", "department", "doc-b"),
        ],
        documents=org_documents(), equivalences=v31_equivalences(),
    )
    assert sum(row["status"] == "accepted" for row in registry) == 2
    assert audit["merge_map"] == []


def test_organization_merge_preserves_evidence_sources_and_aliases() -> None:
    left = org_record("left", "Ministry Of Housing & Urban Affairs", "ministry", "doc-a")
    right = org_record("right", "Ministry Of Housing And Urban Affairs", "implementing_agency", "doc-b")
    right["aliases"] = ["MoHUA"]
    registry, _ = canonicalize_organization_entities(
        registry=[left, right], documents=org_documents(), equivalences=v31_equivalences(),
    )
    merged = next(row for row in registry if row["status"] == "accepted")
    assert merged["source_document_ids"] == ["doc-a", "doc-b"]
    assert {item["document_id"] for item in merged["corpus_evidence"]} == {"doc-a", "doc-b"}
    assert "MoHUA" in merged["aliases"]


def test_organization_merge_uses_strongest_semantic_type() -> None:
    registry, _ = canonicalize_organization_entities(
        registry=[
            org_record("agency", "Ministry Of Housing And Urban Affairs", "implementing_agency", "doc-b"),
            org_record("ministry", "Ministry Of Housing & Urban Affairs", "ministry", "doc-a"),
        ],
        documents=org_documents(), equivalences=v31_equivalences(),
    )
    assert next(row for row in registry if row["status"] == "accepted")["entity_type"] == "ministry"


def test_v31_registry_deterministic_after_merge() -> None:
    rows = [
        org_record("a", "Ministry Of Housing & Urban Affairs", "ministry", "doc-a"),
        org_record("b", "Ministry Of Housing And Urban Affairs", "implementing_agency", "doc-b"),
    ]
    first = canonicalize_organization_entities(registry=rows, documents=org_documents(), equivalences=v31_equivalences())
    second = canonicalize_organization_entities(registry=list(reversed(rows)), documents=list(reversed(org_documents())), equivalences=v31_equivalences())
    assert stable_json(first) == stable_json(second)


def test_v31_graph_hash_deterministic_after_merge() -> None:
    rows = [
        org_record("a", "Ministry Of Housing & Urban Affairs", "ministry", "doc-a"),
        org_record("b", "Ministry Of Housing And Urban Affairs", "implementing_agency", "doc-b"),
    ]
    merged, _ = canonicalize_organization_entities(registry=rows, documents=org_documents(), equivalences=v31_equivalences())
    chunks = [chunk("c-a", "Ministry Of Housing & Urban Affairs", document_id="doc-a"), chunk("c-b", "Other text", document_id="doc-b")]
    first = stable_json(build_graph(chunks=chunks, registry=merged)[:3])
    second = stable_json(build_graph(chunks=list(reversed(chunks)), registry=list(reversed(merged)))[:3])
    assert sha256_text(first) == sha256_text(second)


def test_v31_retrieval_cli_accepts_no_evaluation_or_previous_run_input() -> None:
    from scripts.run_phase3_graph_v3_1_retrieval import APPROVED

    assert set(APPROVED) == {
        "config", "registry", "nodes", "edges", "chunk_entities", "freeze_manifest", "queries", "output",
    }
    assert not set(APPROVED) & {"qrels", "gold", "reference_answers", "categories", "previous_rankings", "metrics"}


def test_r5_retrieval_input_contains_only_id_and_question() -> None:
    rows = [
        json.loads(line)
        for line in (ROOT / "runs/v2/phase3_graph_v3_1/inputs/r5_queries_only.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 34
    assert all(set(row) == {"query_id", "question"} for row in rows)


def test_v31_trace_gate_preserves_invalid_run_before_metrics() -> None:
    decision = json.loads((ROOT / "audits/phase3_graph_v3_1/trace_validity_decision.json").read_text(encoding="utf-8"))
    assert decision["status"] == "invalid_trace_gate_missing_corpus_backed_scheme_alias"
    assert decision["inspected_trace_count"] == 8
    assert decision["valid_trace_count"] == 7
    assert decision["invalid_query_ids"] == ["v2q-029"]
    assert decision["metrics_calculated"] is False
    assert decision["pool_expansion_performed"] is False
    assert decision["retrieval_run_preserved"] is True


def test_v31_invalid_trace_has_exact_corpus_backed_alias_evidence() -> None:
    decision = json.loads((ROOT / "audits/phase3_graph_v3_1/trace_validity_decision.json").read_text(encoding="utf-8"))
    assert decision["failure"]["classification"] == "registry alias-coverage implementation defect; exact token matcher behaved as frozen"
    assert decision["failure"]["corpus_occurrence_chunk_ids"] == [
        "pilot-v2-doc-pmuy-0001-5fd4d0cd2135",
        "pilot-v2-doc-pmuy2-0000-95fa2d4e3b3f",
        "pilot-v2-doc-pmuy2-0002-61d762b2cd43",
    ]
    assert not (ROOT / "runs/v2/phase3_graph_v3_1/metrics").exists()
    assert not (ROOT / "runs/v2/phase3_graph_v3_1/pool").exists()


def v32_registry() -> list[dict]:
    registry = [json.loads(line) for line in (ROOT / "data/v2/pilot/graph/entity_registry_v3_1.jsonl").read_text(encoding="utf-8").splitlines()]
    chunks = [json.loads(line) for line in (ROOT / "data/v2/pilot/chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    documents = [json.loads(line) for line in (ROOT / "data/v2/pilot/extracted/documents.jsonl").read_text(encoding="utf-8").splitlines()]
    cfg = json.loads((ROOT / "configs/entity_graph_v3_2_frozen.json").read_text(encoding="utf-8"))
    updated, _ = apply_corpus_backed_scheme_aliases(
        registry=registry, chunks=chunks, documents=documents,
        additions=cfg["approved_corpus_backed_alias_additions"],
    )
    return updated


@pytest.mark.parametrize("query", ["Ujjwala 2.0", "ujjwala 2.0", "‘Ujjwala 2.0,’"])
def test_v32_ujjwala_numbered_alias_resolves_exactly(query: str) -> None:
    matches = EntityMatcher(v32_registry()).match(query)
    assert len(matches) == 1
    assert matches[0].canonical_label == "Pradhan Mantri Ujjwala Yojana 2.0"
    assert normalize_text(matches[0].matched_alias) == "ujjwala 2 0"


def test_v32_full_canonical_title_resolves() -> None:
    matches = EntityMatcher(v32_registry()).match("Pradhan Mantri Ujjwala Yojana 2.0")
    assert len(matches) == 1
    assert matches[0].canonical_label == "Pradhan Mantri Ujjwala Yojana 2.0"


def test_v32_alias_plus_canonical_title_counts_one_seed() -> None:
    matches = EntityMatcher(v32_registry()).match("Ujjwala 2.0 — Pradhan Mantri Ujjwala Yojana 2.0")
    assert len(matches) == 1
    assert matches[0].canonical_label == "Pradhan Mantri Ujjwala Yojana 2.0"


def test_v32_unrelated_ujjwala_fragment_does_not_resolve_phase_two() -> None:
    matches = EntityMatcher(v32_registry()).match("Ujjwala programme")
    assert not [match for match in matches if match.canonical_label == "Pradhan Mantri Ujjwala Yojana 2.0"]


def test_v32_alias_provenance_is_corpus_only() -> None:
    row = next(row for row in v32_registry() if row["canonical_label"] == "Pradhan Mantri Ujjwala Yojana 2.0")
    provenance = next(item for item in row["alias_provenance"] if item["alias"] == "Ujjwala 2.0")
    assert provenance["evidence_source"] == "frozen chunks only; no benchmark inputs"
    assert provenance["evidence_chunk_ids"]
    assert all(item["chunk_id"].startswith("pilot-v2-") for item in provenance["corpus_evidence"])
    serialized = stable_json(provenance)
    assert not any(term in serialized for term in ("question_id", "qrels", "graph_path", "reference_answer"))


def test_v32_qa_qrels_mutation_cannot_change_alias_registry() -> None:
    before = stable_json(v32_registry())
    qa = {"question": "Ujjwala 2.0", "graph_path": "invented"}
    qrels = {"chunk_id": "invented-gold", "relevance": 2}
    qa["question"] = "changed benchmark wording"
    qrels["chunk_id"] = "changed-gold"
    assert stable_json(v32_registry()) == before


def test_v31_artifacts_remain_byte_identical_during_v32_repair() -> None:
    expected = {
        "configs/entity_graph_v3_1_frozen.json": "e1fa22ff1ebdca486e997afc2e20461b0601f7e05b7c0927e09dee382437c8c0",
        "data/v2/pilot/graph/entity_registry_v3_1.jsonl": "b72094900eba7541bc9adce435635937fbbf024c92bd9f007bc83eff006179f7",
        "runs/v2/phase3_graph_v3_1/index/nodes.jsonl": "aa7fb60c6557c9b7ccc62ffae1d7c8d01345355f7bff7f5f27336408a32715a1",
        "runs/v2/phase3_graph_v3_1/index/edges.jsonl": "5510475786a4e9103869cdfde2cdf163bc53cfec6661965a6865057829a42019",
        "runs/v2/phase3_graph_v3_1/index/chunk_entities.json": "6270904645f77c20c8ecf30d4850a0ab8003f9de7cf132f5aaf6c9c822e43540",
        "runs/v2/phase3_graph_v3_1/traces/graph_v3_1_full_traces.jsonl": "db10ed4725ec7fc955aae703fb224e0284e5cea0c978d3d021d246eef0c11356",
        "audits/phase3_graph_v3_1/trace_validity_decision.json": "03360b1d11b09b70c398f66532e4f49f36065863fb9c78c80d3c82716e5b9181",
    }
    assert {path: sha256_text((ROOT / path).read_text(encoding="utf-8")) for path in expected} == expected


def test_v31_v32_config_diff_has_no_scoring_change() -> None:
    audit = json.loads((ROOT / "audits/phase3_graph_v3_2/configuration_diff_v3_1_to_v3_2.json").read_text(encoding="utf-8"))
    assert audit["status"] == "passed_only_version_and_approved_alias_fields_changed"
    assert audit["scoring_unchanged"] is True
    assert audit["unexpected_changed_roots"] == []


def test_v32_alias_registry_and_graph_rebuild_deterministic() -> None:
    first_registry = v32_registry()
    second_registry = v32_registry()
    assert sha256_text(stable_json(first_registry)) == sha256_text(stable_json(second_registry))
    chunks = [json.loads(line) for line in (ROOT / "data/v2/pilot/chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    first_graph = build_graph(chunks=chunks, registry=first_registry)[:3]
    second_graph = build_graph(chunks=list(reversed(chunks)), registry=list(reversed(second_registry)))[:3]
    assert sha256_text(stable_json(first_graph)) == sha256_text(stable_json(second_graph))


def test_v32_frozen_registry_contains_only_approved_new_aliases() -> None:
    registry = [json.loads(line) for line in (ROOT / "data/v2/pilot/graph/entity_registry_v3_2.jsonl").read_text(encoding="utf-8").splitlines()]
    v31 = [json.loads(line) for line in (ROOT / "data/v2/pilot/graph/entity_registry_v3_1.jsonl").read_text(encoding="utf-8").splitlines()]
    old = {row["entity_id"]: {normalize_text(alias) for alias in row["aliases"]} for row in v31 if row["status"] == "accepted"}
    new = {row["entity_id"]: {normalize_text(alias) for alias in row["aliases"]} for row in registry if row["status"] == "accepted"}
    additions = sorted((entity_id, alias) for entity_id in new for alias in new[entity_id] - old[entity_id])
    assert additions == sorted([
        ("entity-d57cc9ede07d7493", "ab pm jay"),
        ("entity-e75ba4efd13b7922", "pm kisan"),
        ("entity-4d2a6a6876df5e9d", "pmgkay"),
        ("entity-b1b4da1c26e542d9", "pmuy 2 0"),
        ("entity-b1b4da1c26e542d9", "ujjwala 2 0"),
    ])


def test_v32_trace_gate_passes_all_eight_before_metrics() -> None:
    decision_path = ROOT / "audits/phase3_graph_v3_2/trace_validity_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["status"] == "passed_trace_validity_gate"
    assert decision["inspected_trace_count"] == 8
    assert decision["valid_trace_count"] == 8
    assert decision["invalid_query_ids"] == []
    assert decision["metrics_calculated"] is False
    assert decision["pool_expansion_performed"] is False
    evaluation = json.loads((ROOT / "runs/v2/phase3_graph_v3_2/evaluation_manifest.json").read_text(encoding="utf-8"))
    assert evaluation["status"] == "corrected_graph_v3_2_metrics_and_provisional_pool_checkpoint"
    assert evaluation["input_hashes"]["audits/phase3_graph_v3_2/trace_validity_decision.json"] == sha256_file(decision_path)


def test_v32_v2q029_trace_seed_and_provenance_pass() -> None:
    rows = [json.loads(line) for line in (ROOT / "audits/phase3_graph_v3_2/eight_trace_audit.jsonl").read_text(encoding="utf-8").splitlines()]
    row = next(item for item in rows if item["query_id"] == "v2q-029")
    assert row["trace_valid"] is True
    assert row["seed_checks"] == [{
        "canonical_seed": "Pradhan Mantri Ujjwala Yojana 2.0",
        "document_frequency": 2,
        "entity_id": "entity-b1b4da1c26e542d9",
        "entity_type": "scheme",
        "exact_boundary_match": True,
        "matched_alias": "Ujjwala 2.0",
        "matched_query_span": "ujjwala 2 0",
        "meaningful_not_banned_or_generic": True,
        "registry_entity_exists_and_accepted": True,
        "seed_weight": pytest.approx(math.log(141 / 3) + 1),
        "seed_weight_reproduced": True,
    }]
    assert row["checks"]["corpus_backed_alias_provenance_valid"] is True
    assert row["checks"]["same_seed_not_double_counted"] is True
    assert row["checks"]["expected_multi_hop_relationship_corpus_supported"] is True
