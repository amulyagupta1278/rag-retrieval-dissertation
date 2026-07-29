# Canonical retrieval implementations

All five V2 pilot retrieval strategies have reusable implementation code under this directory.
Machine-readable mapping is `src/retrievers/SYSTEMS.json`.

| System | Core implementation | Frozen execution entrypoint |
|---|---|---|
| BM25 | `bm25_retriever.py` | `scripts/run_phase2a_r5_windowed.py` |
| FAISS-windowed-max | `faiss_retriever.py` | `scripts/run_phase2a_r5_windowed.py` |
| Entity Graph v3.2 | `entity_graph_v3.py` | `scripts/run_phase3_graph_v3_2_retrieval.py` |
| Hybrid RRF | `hybrid_rrf_v1.py` | `scripts/run_phase4_hybrid.py` |
| Prompt-RAG Claude | `prompt_rag_claude_v2.py`, `prompt_rag_contract.py` | `scripts/run_phase5d_v3_transport_recovery.py` |

Execution scripts remain at frozen historical paths because audit manifests hash those paths.
Moving them would break evidence lineage. Consolidated rankings and metrics live in
`runs/canonical_v2_pilot/`; original source artifacts remain authoritative.
