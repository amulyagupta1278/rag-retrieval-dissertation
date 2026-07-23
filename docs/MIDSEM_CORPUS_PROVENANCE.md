# Mid-Semester Corpus and Benchmark Provenance

Scope: Git-level verification at commit `df1b37384738641691a5f993bbab3032f6394f62`. Historical files remain unchanged. Raw evidence is under `audits/phase0/midsem_provenance/`.

## Five raw snapshots

All five files first entered history together in commit `123932df629cd7e6379721b449baacd44557d5a1` on 2026-06-21. The same commit added `chunks_v1.jsonl`, the six-category QA generator, the 28-record QA file, and qrels.

| Raw file | Recorded scheme/source | Recorded URL | SHA-256 |
|---|---|---|---|
| `data/raw/snapshot_v1/wiki_pradhan_mantri_awas_yojana.txt` | Pradhan Mantri Awas Yojana | `https://en.wikipedia.org/wiki/Pradhan_Mantri_Awas_Yojana` | `a2f8c6fab2d31b7812ec970bce1d48eaee618ee61c70654a7ca511cb7deec5fd` |
| `data/raw/snapshot_v1/wiki_mgnrega.txt` | MGNREGA | `https://en.wikipedia.org/wiki/Mahatma_Gandhi_National_Rural_Employment_Guarantee_Act` | `614558df4c57b9b361ccb2685c11a654da5caefe44e76a101d7ef6f893fc5180` |
| `data/raw/snapshot_v1/wiki_pmjdy.txt` | PMJDY | `https://en.wikipedia.org/wiki/Pradhan_Mantri_Jan_Dhan_Yojana` | `2395d18d8d7da63aac38da8c0e0d3a29e14d9a058167eedbf8de05f4bf0753de` |
| `data/raw/snapshot_v1/wiki_pmmy.txt` | PMMY/Mudra Yojana | `https://en.wikipedia.org/wiki/Pradhan_Mantri_Mudra_Yojana` | `1b4bdbf81e9d8647e1f512c53701599ee3f1f18610970b57e255c01a7c9593dd` |
| `data/raw/snapshot_v1/wiki_pmfby.txt` | PMFBY/Fasal Bima Yojana | `https://en.wikipedia.org/wiki/Pradhan_Mantri_Fasal_Bima_Yojana` | `04ec7100179ecc405efbef7332e20f78f1e6e59dcd4c33405e81c1fe19e800f5` |

Recorded URLs come from `data/metadata/sources.csv`, SHA-256 `d0a1998bb28d2fb878326a4d2e434c8f9e71ecd2991f7dbf2fdc5f1b50cc857c`. Git proves committed content and recorded metadata; it does not independently prove the files were fetched from those URLs. The PMMY snapshot begins with general Narendra Modi premiership text, and PMFBY contains substantial navigation/political boilerplate. Source relevance and extraction quality are therefore limited.

## Raw snapshot to chunks

No separate cleaned-document artifact is committed for this pilot. The verified relationship is:

`five raw TXT snapshots → whitespace-word Chunker → data/chunks/chunks_v1.jsonl`

Running committed `src/ingestion/chunker.py` with `chunk_size=300`, `chunk_overlap=60`, `min_chunk_length=50`, and sentence-boundary respect directly on each raw file reproduces all ten committed chunk IDs and texts exactly. Chunk file SHA-256: `46209d833055a2d0668660b11661adbfdc6722c97a87eae844913539cde18532`.

The chunker calls `text.split()` and documents `chunk_size` and `chunk_overlap` as words. “300-token window / 60-token overlap” therefore means whitespace-delimited words, not model/subword tokens. No model tokenizer participates.

Sentence-boundary extension may advance a first chunk beyond 300 words while the next start remains fixed at word 240. Final short chunks may contain fewer than 60 words. Actual measurements:

| Document | Chunk 0 words | Chunk 1 words | Exact suffix/prefix overlap |
|---|---:|---:|---:|
| PMAY | 300 | 111 | 60 words |
| MGNREGA | 302 | 131 | 62 words |
| PMJDY | 317 | 131 | 77 words |
| PMMY | 289 | 49 | 49 words |
| PMFBY | 306 | 83 | 66 words |

**Slide assessment:** Ten chunks and nominal 300/60 configuration are VERIFIED. Calling units model “tokens,” implying every chunk is exactly 300 units, or implying every overlap is exactly 60 is CONTRADICTED. A separately persisted cleaning stage is UNVERIFIED.

## Historical QA benchmark

`data/queries/qa_dataset_v1.jsonl`, SHA-256 `f98776865ff6632b24035b8e76551d96f5b89e3e9acadaaf953d7543d34f862b`, contains 28 records:

| IDs | Category | Count |
|---|---|---:|
| `q_0001`–`q_0009` | exact lookup | 9 |
| `q_0010`–`q_0013` | terminology | 4 |
| `q_0014`–`q_0015` | paraphrase | 2 |
| `q_0016`–`q_0017` | entity relation | 2 |
| `q_0018`–`q_0022` | multi-hop | 5 |
| `q_0023`–`q_0028` | synthesis | 6 |

Expected slide counts 9/4/2/2/6/5 are VERIFIED. Exact question text and gold IDs are preserved in `audits/phase0/midsem_provenance/qa_records.tsv`.

Historical `scripts/generate_qa_dataset.py`, SHA-256 `20ba1f32491bdb7bfae983558efd87eb62237b85b52f185ccc4a5dbcd1818dd7`, explicitly defines six categories including synthesis. Current `src/benchmark/qa_generator.py` is a different, older five-category pipeline that excludes synthesis. Both coexist because the historical benchmark and its dedicated generator were added later in `123932df` without replacing the baseline generator.

### Authorship determination

- **VERIFIED:** Every historical question follows templates or fixed question lists present in `scripts/generate_qa_dataset.py`.
- **VERIFIED:** Re-executing candidate generation produces 28 items with identical category counts and 78 qrels.
- **VERIFIED:** Exact re-execution is nondeterministic because terminology/entity templates use Python `hash()` without a fixed `PYTHONHASHSEED`; a probe changed `q_0010` while retaining counts.
- **INFERRED:** Questions are template-generated.
- **UNVERIFIED:** Git cannot distinguish untouched generator output from generator output manually edited before the single introducing commit. “Manually constructed” is not established.

## Qrels

`data/qrels/qrels.tsv`, SHA-256 `f1de481174345987cd4c40019993eb5c166bb8465e833e7695580547d6ec777b`, contains:

- 28 query IDs.
- 78 judgments.
- 45 judgments with relevance 2.
- 33 judgments with relevance 1.
- Zero judgments referencing unknown historical chunks.
- Exact query-set equality with the 28 QA records.

Generator logic assigns relevance 2 to `gold_evidence_ids` and relevance 1 to other chunks from the same source document. These are programmatic judgments, not independently documented human relevance annotations.

## Conclusions

- **VERIFIED:** Five committed raw snapshots, recorded Wikipedia URLs, ten reproducible word-based chunks, 28 six-category QA records, and 78 resolving qrels exist.
- **VERIFIED:** Chunk text/IDs reproduce exactly from raw snapshots and committed chunker/configuration.
- **VERIFIED:** Binary and graded qrels are mechanically available; annotation quality is not thereby validated.
- **CONTRADICTED:** “300 tokens” as model tokens and uniform 60-token overlap.
- **UNVERIFIED:** Independent URL authenticity, a separate cleaning artifact, manual QA authorship/review, and human qrel validation.
