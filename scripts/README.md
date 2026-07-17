# Pipeline Scripts

The current pipeline is catalog-driven, authoritative-source-only, and split into explicit
stages. Obsolete `chunks_v1.jsonl` demo/build entrypoints were removed because they could
silently overwrite released artifacts; the immutable v1 data remains available for the
mid-semester baseline.

## Supported entrypoints

- `download_corpus.py`: acquisition and provenance only. It never cleans, chunks, builds QA,
  or creates indexes.
- `release_pipeline.py`: staged corpus → indexes → benchmark → evaluation → statistics →
  checksum verification → atomic publication.
- `regenerate_qa.py`: graph-backed cross-scheme benchmark layer only.
- `generate_corpus_statistics.py`: versioned corpus/graph statistics.
- `prepare_benchmark_audit.py`, `finalize_question_audit.py`, and
  `finalize_qrels_audit.py`: P1 manual review gates.
- `statistical_evaluation.py` and `benchmark_latency.py`: query-level statistics and the
  cold/steady latency protocol.
- `run_dev_model_selection.py`, `run_structured_graph_ablations.py`,
  `run_rrf_experiment.py`, `run_reranker_experiment.py`, and
  `run_rule_router_experiment.py`: later-phase experiments that fail closed until their
  prerequisite audit/configuration gates pass.

Run the reproducible clean release from the repository root:

```bash
make release-v3-clean
```

The frozen catalog is `data/sources/source_catalog_v2.jsonl`; `v2` here is the source-snapshot
name, not the processed release label. Released processed artifacts live under
`releases/v2_serialized/` and `releases/v3_clean/`.

The graph baseline is **Entity-Co-occurrence Graph Retrieval**, not Microsoft GraphRAG.
`graphrag` remains only as a legacy machine key/path.
