# Artifact Provenance V2

Status: Phase 0 provenance register. Historical files remain unchanged.

## Mid-semester chain

All rows below refer to commit `df1b37384738641691a5f993bbab3032f6394f62` unless stated otherwise.

| Role | Artifact | SHA-256 | Status |
|---|---|---|---|
| Manifest | `data/metadata/corpus_manifest.json` | `c706ff0ed2bde926e9412c139663b4b9be74817f0d5e00621184e5b755fc4662` | VERIFIED: says 5 documents/10 chunks |
| Default corpus | `data/chunks/chunks.jsonl` | `cf571e0380b9dbca6baf827936c02a2ad7a34fdde580ae334165d91685626f5d` | VERIFIED: one placeholder record; not manifest corpus |
| Historical corpus | `data/chunks/chunks_v1.jsonl` | `46209d833055a2d0668660b11661adbfdc6722c97a87eae844913539cde18532` | VERIFIED: 10 chunks |
| Historical QA | `data/queries/qa_dataset_v1.jsonl` | `f98776865ff6632b24035b8e76551d96f5b89e3e9acadaaf953d7543d34f862b` | VERIFIED: 28 queries |
| Qrels | `data/qrels/qrels.tsv` | `f1de481174345987cd4c40019993eb5c166bb8465e833e7695580547d6ec777b` | VERIFIED: 78 judgments, grades 1/2 |
| BM25 raw run | `runs/retrieval/bm25_run.jsonl` | `3401d18b62d93811c150146fc5a9ac9a6b27c41fea6435da42ada41ae69d570e` | VERIFIED: 28 runs |
| FAISS raw run | `runs/retrieval/faiss_run.jsonl` | `3d9b80fdf30c905840cea7312aba99ca0ca96f15d997a133597a415ed617ac5e` | VERIFIED: 28 runs |
| Graph raw run | `runs/retrieval/graphrag_run.jsonl` | `66d7e084914ed19b6910d73180a1882d45fa089227073384bd32c7d7ca581952` | VERIFIED: 28 runs |
| Reported summary | `runs/metrics/comparison_summary.csv` | `1e43e3aa118e0bf9c66fd9b0f24c0a81c19db4eb52d611eaee1e941b118e01de` | VERIFIED: published aggregate |
| Comparison generator | `scripts/run_full_comparison.py` | `6290ffb08a4929a18be2dc6ba2521a8f684eebd98008c5bb8d6066c9ed05f5fe` | VERIFIED: binary nDCG path |
| Metric implementation | `src/evaluation/metrics.py` | `1e81f1f2db66227413740190499d4aefab028ff516ff507fc0c921a439e8669e` | VERIFIED: binary metrics |

## Provenance chain assessment

`five committed raw Wikipedia snapshots → chunks_v1 → qa_dataset_v1/qrels → retriever indexes → three raw runs → comparison_summary`

- Raw snapshots, chunks, QA, qrels, runs, and summary are committed.
- Exact aggregate values are numerically recomputable from committed runs/qrels.
- Historical source acquisition execution is UNVERIFIED: URLs/metadata exist, but complete request/response evidence and acquisition command are absent.
- Index-to-corpus fingerprints are absent. Index provenance is therefore UNVERIFIED even when run chunk IDs resolve.
- FAISS model version, package versions, platform capture, and exact command are incomplete.
- Historical result is numerically recomputable, not fully reproducible.

## Later reference-only artifacts

| Commit | Artifact | SHA-256 | Classification |
|---|---|---|---|
| `03dc86289e953489612a817ff962db92781e680a` | `src/evaluation/metrics.py` | `d21bc3ffbe7d6fe4dc4cb941e4ed4a32cd414b5a09441750b1e9e503d2df0bf2` | Useful MRR@k concept; later corpus excluded |
| `1bafc63e9e9da159101d7506e08ea9d478d47183` | `src/retrievers/fusion.py` | `f78e67abecb0913990c2dbcd61c091006fd7e5c6b3395e24d3d87bfadda17cf0` | RRF code/tests; no committed output |
| `1bafc63e9e9da159101d7506e08ea9d478d47183` | `src/retrievers/graphrag_retriever.py` | `f7e64e7ae015c70a708a8769c143f075eee957afdf349c60614fb3f22284a72b` | Independent per-seed traversal concept |
| `6876aee7e440c7a2cc38f91e58bba9a80d1df346` | `scripts/run_structured_graph_ablations.py` | `df9e2766c25d8af33918227c7127aa91188f5907f4f0f7dfc3aaf5e1965a3cd0` | Definitions only; commit says unexecuted |
| `c735f80fdde2554256b2b6b9687af77808827471` | `audits/v3_clean_benchmark_r1/audit_summary.json` | `f0be5bdbf255f08f2807ec3c967763a5a3f60ba659cd0aa640e0f21c217eb773` | Pending human review; diagnostic only |

## Phase 0 generated evidence

`scripts/forensics/recompute_midsem_metrics.py` writes only to an explicit output directory. Its input manifest records absolute paths, sizes, SHA-256 values, and Git HEAD before computation. Output hashes cover command, environment, manifest, per-query metrics, aggregate metrics, and findings.
