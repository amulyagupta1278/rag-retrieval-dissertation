import json

from src.retrievers.structured_graph_retriever import StructuredMetadataGraphRetriever


def _chunks(source_path):
    return [
        {
            "chunk_id": "c1", "doc_id": "d1", "scheme_name": "Alpha Support Scheme",
            "ministry": "Ministry of Rural Development", "source_path": str(source_path),
            "text": "Alpha Support Scheme assists Scheduled Caste students through the Rural Benefits Agency.",
        },
        {
            "chunk_id": "c2", "doc_id": "d2", "scheme_name": "Beta Assistance Programme",
            "ministry": "Ministry of Rural Development", "source_path": str(source_path),
            "text": "Beta Assistance Programme supports Scheduled Caste workers through the Rural Benefits Agency.",
        },
    ]


def test_structured_graph_builds_typed_edges_and_retrieves_schemes(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"implementingAgency": "Rural Benefits Agency", "nodalDepartmentName": "Rural Welfare Department"}), encoding="utf-8")
    retriever = StructuredMetadataGraphRetriever(tmp_path / "index", min_entity_freq=1)
    retriever._extractor.extract = lambda text: ["rural benefits agency"]
    chunks = _chunks(source)
    retriever.build_index(chunks)
    relations = {data["relation"] for _, _, data in retriever.graph.edges(data=True)}
    assert {"chunk-of-document", "describes-scheme", "administered-by", "implemented-by", "targets"} <= relations
    results = retriever.retrieve("How are Alpha Support Scheme and Beta Assistance Programme related?", top_k=2)
    assert {result.chunk_id for result in results} == {"c1", "c2"}


def test_structured_graph_zero_seed_fallback_is_deterministic(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    retriever = StructuredMetadataGraphRetriever(tmp_path / "index", min_entity_freq=1)
    retriever._extractor.extract = lambda text: []
    retriever.build_index(_chunks(source))
    first = [item.chunk_id for item in retriever.retrieve("eligible students", 2)]
    second = [item.chunk_id for item in retriever.retrieve("eligible students", 2)]
    assert first == second
    assert first
