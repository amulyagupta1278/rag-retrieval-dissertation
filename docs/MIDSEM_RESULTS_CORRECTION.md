# Mid-Semester Results Correction

Status: correction draft. Historical report and artifacts remain unchanged.

## Scope

This document corrects provenance and interpretation without alleging fabrication. “Unsupported by committed artifacts” means evidence is absent; it does not establish intent. “Numerically recomputable” does not mean a complete experiment is fully reproducible.

## Historical benchmark

- **VERIFIED:** The historical corpus manifest reports five documents and ten chunks. Evidence: commit `df1b37384738641691a5f993bbab3032f6394f62`, `data/metadata/corpus_manifest.json`, SHA-256 `c706ff0ed2bde926e9412c139663b4b9be74817f0d5e00621184e5b755fc4662`.
- **VERIFIED:** The ten-chunk historical corpus is `data/chunks/chunks_v1.jsonl`, SHA-256 `46209d833055a2d0668660b11661adbfdc6722c97a87eae844913539cde18532`, at commit `df1b37384738641691a5f993bbab3032f6394f62`.
- **VERIFIED:** The historical QA contains 28 records. Evidence: `data/queries/qa_dataset_v1.jsonl`, SHA-256 `f98776865ff6632b24035b8e76551d96f5b89e3e9acadaaf953d7543d34f862b`, same commit.
- **VERIFIED:** The qrels contain grades 1 and 2. Evidence: `data/qrels/qrels.tsv`, SHA-256 `f1de481174345987cd4c40019993eb5c166bb8465e833e7695580547d6ec777b`, same commit.
- **VERIFIED:** BM25, FAISS, and Graph run files each contain 28 queries. Their SHA-256 values are recorded in `docs/ARTIFACT_PROVENANCE_V2.md`.

These results describe a small pipeline-validation benchmark. They are not final dissertation evidence.

## Default placeholder exposure

- **VERIFIED:** The default path `data/chunks/chunks.jsonl` contains one synthetic demo record referencing `placeholder.txt`; SHA-256 `cf571e0380b9dbca6baf827936c02a2ad7a34fdde580ae334165d91685626f5d` at `df1b37384738641691a5f993bbab3032f6394f62`.
- **VERIFIED:** `experiments/build_dataset.py:67-73` silently writes placeholder data when no source documents load. This default is incompatible with V2’s fail-closed acquisition policy.
- **CONTRADICTED:** The default one-record corpus is not the ten-chunk corpus described by `data/metadata/corpus_manifest.json`.

## nDCG correction

The published `runs/metrics/comparison_summary.csv` has SHA-256 `1e43e3aa118e0bf9c66fd9b0f24c0a81c19db4eb52d611eaee1e941b118e01de` at `df1b37384738641691a5f993bbab3032f6394f62`.

- **VERIFIED:** Historical `src/evaluation/metrics.py:92-108` computes binary nDCG from a set of relevant chunk IDs. It discards qrel grades after testing membership.
- **VERIFIED:** `scripts/run_full_comparison.py:81-89` converts each qrels mapping to `set(qrels[qid].keys())`, then calls that binary implementation. Script SHA-256: `6290ffb08a4929a18be2dc6ba2521a8f684eebd98008c5bb8d6066c9ed05f5fe`.
- **VERIFIED:** Binary recomputation reproduces published nDCG@10 values: BM25 `0.8683438348`, FAISS `0.7741765262`, Graph `0.5908985993`, rounded respectively to `0.8683`, `0.7742`, and `0.5909`.
- **VERIFIED ROOT CAUSE:** Earlier disagreement arose by treating qrel values 1 and 2 as graded gains. Historical code and report used binary relevance. Graded and binary nDCG are different metrics; comparing them as one definition caused the apparent inconsistency.

V2 retains binary nDCG@10 for historical continuity and separately reports graded nDCG@10 using positive qrel values as gains. Supplementary forensic graded values are BM25 `0.8404696965`, FAISS `0.7096199749`, and Graph `0.5760119269`. These values must not be compared with the published binary values as though they were the same metric.

## Later development evidence

- **VERIFIED:** Commit `03dc86289e953489612a817ff962db92781e680a` contains a 1,074-chunk corpus with extensive raw-JSON/schema leakage. Evidence: `data/chunks/chunks.jsonl`, SHA-256 `524896bcab7297e48dc387738fcd99d0047fe79ade1e5e3872d5667d589d26a4`. Treat its results as compromised development evidence.
- **VERIFIED:** Commit `1bafc63e9e9da159101d7506e08ea9d478d47183` contains an 856-chunk cleaned corpus and diagnostic results. Evidence: `data/chunks/chunks.jsonl`, SHA-256 `b14fe2acf00e9d946f01043e8a3264c56965df87d84825ad920330f0b6bebe3d`. Source authenticity is not independently established merely by absence of fallback markers.
- **VERIFIED:** Commit `c735f80fdde2554256b2b6b9687af77808827471`, `audits/v3_clean_benchmark_r1/audit_summary.json`, SHA-256 `f0be5bdbf255f08f2807ec3c967763a5a3f60ba659cd0aa640e0f21c217eb773`, marks review `pending_human_review`. Those results remain diagnostic/development results.
- **VERIFIED:** No explicit synthetic fallback identifiers were found in the committed 856-chunk `data/chunks/chunks.jsonl`, SHA-256 `b14fe2acf00e9d946f01043e8a3264c56965df87d84825ad920330f0b6bebe3d`. This is distinct from independently verifying every external source.

## Unsupported systems

- **VERIFIED:** RRF implementation exists at `1bafc63e9e9da159101d7506e08ea9d478d47183`, `src/retrievers/fusion.py`, SHA-256 `f78e67abecb0913990c2dbcd61c091006fd7e5c6b3395e24d3d87bfadda17cf0`.
- **VERIFIED:** No committed RRF run or RRF metrics artifact was found in reachable history. Any prior RRF metric claim is unsupported by committed artifacts.
- **VERIFIED:** No Prompt-RAG implementation, test, run, Gemini integration, or output artifact was found in reachable history. Prior implementation claims are unsupported by committed artifacts.

## Correct interpretation

Historical metrics are numerically recomputable from committed qrels and run files under binary relevance. Full reproducibility remains unverified because historical commands, environment, input selection, index provenance, and several runner/code interfaces are incomplete or inconsistent. No retrieval hypothesis should be accepted or rejected from Phase 0 alone.
