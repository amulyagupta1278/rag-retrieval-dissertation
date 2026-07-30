# Retrieval directory scope

Files in this directory are preserved 100-query expanded automated diagnostic runs. They contain
BM25, FAISS, and legacy-key `graphrag` outputs only. They are not canonical 34-query V2 pilot
rankings and must not be used to infer how many pilot systems were built.

Canonical five-system pilot registry:

```text
runs/CANONICAL_EVIDENCE.json
```

Consolidated byte-identical view:

```text
runs/canonical_v2_pilot/retrieval/
```

Registry points to frozen BM25, FAISS-windowed-max, Entity Graph v3.2, Hybrid RRF, and Prompt-RAG
Claude rankings with exact SHA-256 hashes. Root files remain unchanged to avoid mixing benchmark
versions or rewriting historical evidence.
