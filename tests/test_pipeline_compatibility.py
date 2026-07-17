"""Schema compatibility tests across benchmark and retrievers."""

import json
from collections import Counter
from src.benchmark.qa_generator import (
    QAGenerator, QAItem, _clean_leaf_text, _validate_item,
    QUERY_CATEGORIES, _terminology_heavy_templates, _multi_hop_template,
    _is_semantic_bridge, _bridge_identity,
)
from src.benchmark.qrels_builder import QRelsBuilder
from src.ingestion.chunker import Chunker
from src.ingestion.metadata_enricher import MetadataEnricher
from src.retrievers.bm25_retriever import BM25Retriever


def enriched_chunks():
    chunker = Chunker(chunk_size=20, chunk_overlap=4, min_chunk_length=1)
    provenance = {
        "document_id": "mord_example", "source": "Ministry of Rural Development",
        "ministry": "Ministry of Rural Development", "scheme_name": "Example Scheme",
        "publication_date": None, "url": "https://rural.gov.in/example",
        "document_type": "operational_guideline", "language": "en", "scope": "central",
    }
    text = "Example Scheme is financial assistance for eligible rural beneficiaries. " * 20
    chunks = chunker.chunk_document("doc_example", text, "/tmp/example.html", "welfare", extra_meta=provenance)
    output = []
    for chunk in chunks:
        item = MetadataEnricher().enrich(chunk.to_dict())
        item.update(provenance)
        output.append(item)
    return output


def test_metadata_addition_preserves_bm25_contract(tmp_path):
    chunks = enriched_chunks()
    retriever = BM25Retriever(index_path=tmp_path / "bm25.pkl")
    retriever.build_index(chunks)
    assert len(retriever._meta) == len(chunks)
    assert {item["chunk_id"] for item in retriever._meta} == {item["chunk_id"] for item in chunks}


def test_qrels_reference_only_generated_chunks():
    chunks = enriched_chunks()
    qa = QAGenerator(seed=42).generate(chunks, max_per_category=3)
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    assert all(evidence in chunk_ids for _, evidence, _ in QRelsBuilder.build_qrels(qa))


def test_qa_generation_is_byte_deterministic():
    chunks = enriched_chunks()
    first = [item.to_dict() for item in QAGenerator(seed=42).generate(chunks, 3)]
    second = [item.to_dict() for item in QAGenerator(seed=42).generate(chunks, 3)]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_split_assignment_is_stratified_and_deterministic():
    items = [
        QAItem(f"q_{category}_{index}", f"Question {index}", category, "easy", "Answer", ["c1"], ["d1"])
        for category in ("exact_match", "terminology_heavy", "paraphrase", "entity_relation", "multi_hop")
        for index in range(20)
    ]
    QAGenerator.assign_stratified_splits(items, dev_ratio=0.2, seed=42)
    assert Counter((item.category, item.split) for item in items) == Counter({
        **{(category, "dev"): 4 for category in QUERY_CATEGORIES},
        **{(category, "test"): 16 for category in QUERY_CATEGORIES},
    })


def test_json_keys_and_markup_are_not_generation_text():
    raw = '{"answer_md":"Real benefit text.","children":[{"text":"Eligible farmers receive support."}],"type":"block_quote"}'
    cleaned = _clean_leaf_text(raw)
    assert "answer_md" not in cleaned
    assert "children" not in cleaned
    assert "block_quote" not in cleaned
    assert "Eligible farmers receive support" in cleaned


def test_acronym_requires_matching_initials():
    bad = _terminology_heavy_templates("ESI - Central welfare office provides benefits.", "c1", "d1", 1)
    good = _terminology_heavy_templates("National Testing Agency (NTA) conducts examinations.", "c1", "d1", 1)
    assert bad == []
    assert good[0].reference_answer == "National Testing Agency"


def test_multi_hop_rejects_unrelated_documents():
    left = {"chunk_id": "c1", "doc_id": "d1", "scheme_name": "One"}
    right = {"chunk_id": "c2", "doc_id": "d2", "scheme_name": "Two"}
    assert _multi_hop_template(
        left, right,
        "Farmers receive crop insurance after verification.",
        "Students submit scholarship applications to colleges.", 1,
    ) is None


def test_validation_gate_rejects_json_artifact_question():
    chunk = {"chunk_id": "c1", "doc_id": "d1"}
    item = QAItem("q1", "What does answer_md [value] mean?", "exact_match", "easy", "Supported answer", ["c1"], ["d1"])
    valid, reason = _validate_item(item, {"c1": "Supported answer appears here."}, {"c1": chunk})
    assert not valid and reason == "question_artifact"


def _cross_item(*, docs=("d1", "d2"), schemes=("Scheme One", "Scheme Two"), bridge="Scheduled Caste"):
    return QAItem(
        "q_0061", f"How are {schemes[0]} and {schemes[1]} related through {bridge}?",
        "entity_relation", "medium", "Scheme One supports Scheduled Caste students. Additionally, Scheme Two supports Scheduled Caste workers.",
        ["c1", "c2"], list(docs), extra_meta={"scheme_names": list(schemes), "bridge_entity": bridge},
    )


def _cross_fixture():
    chunks = [{"chunk_id": "c1", "doc_id": "d1"}, {"chunk_id": "c2", "doc_id": "d2"}]
    clean = {
        "c1": "Scheme One supports Scheduled Caste students.",
        "c2": "Scheme Two supports Scheduled Caste workers.",
    }
    return chunks, clean


def test_cross_scheme_rejects_same_document():
    chunks, clean = _cross_fixture()
    valid, reason = QAGenerator._validate_cross_scheme_item(
        _cross_item(docs=("d1", "d1")), clean, chunks,
    )
    assert not valid and reason == "same_document"


def test_cross_scheme_rejects_same_scheme_across_documents():
    chunks, clean = _cross_fixture()
    valid, reason = QAGenerator._validate_cross_scheme_item(
        _cross_item(schemes=("Scheme One", "Scheme One")), clean, chunks,
    )
    assert not valid and reason == "same_scheme"


def test_cross_scheme_requires_bridge_in_both_parsed_texts():
    chunks, clean = _cross_fixture()
    clean["c2"] = "Scheme Two supports rural workers."
    valid, reason = QAGenerator._validate_cross_scheme_item(_cross_item(), clean, chunks)
    assert not valid and reason == "bridge_missing_from_evidence"


def test_cross_scheme_maps_each_clause_to_assigned_chunk():
    chunks, clean = _cross_fixture()
    item = _cross_item()
    item.reference_answer = "Scheme Two supports Scheduled Caste workers. Additionally, Scheme One supports Scheduled Caste students."
    valid, reason = QAGenerator._validate_cross_scheme_item(item, clean, chunks)
    assert not valid and reason == "answer_clause_not_supported"


def test_schema_noise_and_generic_bridges_are_rejected():
    assert not _is_semantic_bridge("answer_md")
    assert not _is_semantic_bridge("the scheme")
    assert not _is_semantic_bridge("the head of the institute")


def test_full_cross_scheme_gate_is_balanced_and_diverse(tmp_path):
    import networkx as nx
    import pickle

    chunks = []
    graph = nx.Graph()
    for index in range(40):
        bridge = f"Scheduled Caste Group {index}"
        entity = bridge.lower()
        graph.add_node(entity, type="entity", label=entity)
        for side in ("a", "b"):
            chunk_id = f"c{index:02d}{side}"
            scheme = f"Distinct Welfare Scheme {index:02d}{side.upper()}"
            text = f"{scheme} provides independently verified assistance through {bridge} for eligible households across districts."
            chunk = {
                "chunk_id": chunk_id, "doc_id": f"d{index:02d}{side}", "text": text,
                "scheme_name": scheme, "source_path": str(tmp_path / f"{chunk_id}.json"), "chunk_index": 0,
            }
            chunks.append(chunk)
            graph.add_node(chunk_id, type="chunk", label=chunk_id)
            graph.add_edge(entity, chunk_id, relation="contains", weight=1.0)
    graph_path = tmp_path / "graph.gpickle"
    with graph_path.open("wb") as handle:
        pickle.dump({"graph": graph, "chunk_meta": {}}, handle)
    items, _ = QAGenerator(seed=42).generate_cross_scheme(chunks, graph_path)
    assert Counter(item.category for item in items) == {"entity_relation": 20, "multi_hop": 20}
    pairs_by_category = {
        category: {
            tuple(sorted(name.lower() for name in item.extra_meta["scheme_names"]))
            for item in items if item.category == category
        }
        for category in ("entity_relation", "multi_hop")
    }
    assert not pairs_by_category["entity_relation"] & pairs_by_category["multi_hop"]
    bridge_counts = Counter(_bridge_identity(item.extra_meta["bridge_entity"]) for item in items)
    assert max(bridge_counts.values()) <= 2
    for category in pairs_by_category:
        scheme_counts = Counter(
            name.lower()
            for item in items if item.category == category
            for name in item.extra_meta["scheme_names"]
        )
        assert max(scheme_counts.values()) <= 3
