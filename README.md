# RAG Retrieval Dissertation

**Comparative Analysis of Vector-Free Retrieval Strategies for RAG: Hybrid Search and Graph-Based Approaches**

| | |
|---|---|
| **Student** | Amulya Gupta |
| **BITS ID** | 2024AB05200 |
| **Program** | M.Tech. Artificial Intelligence and Machine Learning |
| **Course** | AIMLC ZG628T — Dissertation |
| **Organisation** | HCLTech, Noida |

## Current status

Default branch `origin/main` now contains five-system pilot evidence after merge commit `6049994`
(2026-07-28): BM25, FAISS-windowed-max, Entity Graph v3.2, Hybrid RRF, and Prompt-RAG Claude.
Rule-based router has code scaffolding but no canonical run or score.

Machine-readable canonical discovery starts at `runs/CANONICAL_EVIDENCE.json`. Unversioned
`runs/retrieval/` and `runs/metrics/` contain preserved 100-query automated diagnostic artifacts
for three systems; they are not canonical V2 pilot directories and must not be used as system
inventory. Consolidated five-system rankings, metrics, statistics, and benchmark inputs are under
`runs/canonical_v2_pilot/`; every file remains byte-identical to its frozen source.

- Phase 6 retrieval evaluation is complete on 34 owner-approved questions and final pooled
  human-owner relevance judgments.
- Phase 7 generated and evaluated all 170 planned answers: 34 questions × 5 retrieval systems.
  Twenty-six blinded answers retain human-owner scores; 144 carry disclosed offline AI scores.
  Mechanical validation, owner-audit agreement, and exploratory H5 analysis are frozen.
- Phase 8 has a committed automated 100-question exploratory retrieval run, but benchmark remains
  pending human validation. Its results are diagnostic, not final dissertation evidence.

The title focuses on vector-free alternatives, but the experiment also includes FAISS as a
dense-vector baseline. It does **not** claim that every compared system is vector-free.

## Project in 60 seconds

1. Twenty-two government-scheme source documents were cleaned and divided into 140 retrieval
   chunks.
2. A frozen benchmark contains 34 questions across six query categories.
3. BM25, FAISS, Entity Graph, BM25–Graph Hybrid RRF, and an LLM reranker rank the same chunks.
4. Human-owner pooled judgments grade each candidate chunk as directly relevant, contextual, or
   nonrelevant.
5. Retrieval is evaluated with rank, coverage, evidence-completeness, and efficiency metrics.
6. Phase 7 gives each system's top-three chunks to the same answer generator, isolating how
   retrieval differences affect generated answers.

This is a comparative retrieval study, not a general-purpose chatbot. No composite score or
universal winner is used.

## Research objective

Evaluate how sparse, dense, graph-based, fused, and LLM-reranked retrieval behave on the same
corpus, questions, and relevance judgments. Results are reported by metric and query category so
that one system's strength cannot hide another system's weakness.

## Canonical Hypotheses (H1–H5)

- **H1**: BM25 performs competitively with FAISS on exact-match and terminology-sensitive queries.
- **H2**: FAISS outperforms BM25 on paraphrased/semantic queries where query vocabulary differs from source text.
- **H3**: Entity-Co-occurrence Graph Retrieval outperforms BM25 and FAISS on entity-relation and multi-hop queries.
- **H4**: Hybrid BM25 + Entity-Co-occurrence Graph retrieval achieves the highest aggregate MRR across mixed query types, at the cost of higher latency.
- **H5**: Retrieval quality (MRR) does not translate monotonically into generation faithfulness; retrieval and generation require separate evaluation.

## Retrieval strategies and evidence status

| System | Retrieval strategy | Frozen implementation | Evidence status |
|---|---|---|---|
| **BM25** | Sparse lexical retrieval. Scores query/chunk term overlap with inverse-document-frequency and length normalization. | `k1=1.5`, `b=0.75`; deterministic ascending chunk-ID tie-break. | Canonical run available on `main`. |
| **FAISS-windowed-max** | Dense semantic retrieval. Embeds token-aware windows, compares normalized query/window vectors with cosine similarity, then uses each chunk's maximum window score. | `sentence-transformers/all-MiniLM-L6-v2`, pinned revision, 254 content tokens, 32-token overlap, normalized embeddings, `IndexFlatIP`, exact search. | Canonical run available on `main`. |
| **Entity Graph v3.2** | Vector-free graph retrieval. Matches corpus-backed entity aliases, traverses chunk/entity co-occurrence paths, then ranks matching chunks. | Exact normalized alias matching, maximum two-hop path, no lexical fallback, deterministic ranking. | Canonical run available on `main`. |
| **Hybrid RRF** | Rank fusion of BM25 and Entity Graph. For each chunk, sums `1 / (60 + rank)` across available component rankings. | Equal weights, `RRF k=60`, component depth 50, output depth 50, no extra index. | Canonical run on `main`; original evidence commit `70de0fd` (2026-07-26). |
| **Prompt-RAG Claude** | LLM relevance reranker over frozen BM25 top-50; cannot retrieve chunks absent from candidate set. | `claude-haiku-4-5-20251001`; one query plus 50 candidates; integer relevance 0–3; score descending then chunk-ID tie-break; no fallback. | Canonical run on `main`; original evidence commit `88c54c9` (2026-07-27). |
| **Rule router** | Intended query-dependent retriever selection. | No frozen experiment configuration or completed canonical ranking run. | **Pending: no result may be displayed.** |

### Important terminology

`Prompt-RAG` in this repository is a **retrieval reranker**, not answer generation. It cannot
retrieve outside the BM25 top-50 candidate set; its measured candidate-recall ceiling is 0.9490.

Hybrid ranking evidence is stored at
`runs/v2/phase4_hybrid/rankings/hybrid_top50.jsonl` (SHA-256
`6570030a1c12edb38ff5c4e33b5dedb5d2fa83a05aa9a01ecd768bcf4edce249`). Prompt-RAG ranking
evidence is stored at
`runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/complete_primary_rankings.jsonl` (SHA-256
`e665aa4dc80b468a0fc2af06173ab0e6963786a578653c9a9083e6ffa6b1e04f`). Five-system pooled
metrics were calculated in commit `dcc5219` (2026-07-28). All three artifacts are now available
on `origin/main` through merge commit `6049994`.

Phase 7 is separate answer generation. It uses the same Claude model and each retrieval system's
top-three chunks to generate cited answers under one frozen prompt and schema.

The graph implementation is **Entity-Co-occurrence Graph Retrieval**, not Microsoft GraphRAG. It
does not use LLM relationship extraction, community summaries, or GraphRAG global/local search.

## Canonical pilot benchmark

| Property | Frozen value |
|---|---:|
| Source documents represented in chunks | 22 |
| Retrieval chunks | 140 |
| Questions | 34 |
| Query categories | 6 |
| Blinded pooled query/chunk pairs | 755 |
| Final grade 0 labels | 572 |
| Final grade 1 labels | 89 |
| Final grade 2 labels | 94 |

Category distribution:

| Category | Questions | Purpose |
|---|---:|---|
| `exact_lookup` | 6 | Direct fact retrieval |
| `terminology` | 6 | Acronyms and scheme-specific terms |
| `paraphrase` | 6 | Semantic match despite changed wording |
| `entity_relation` | 6 | Relationship between named entities |
| `multi_hop` | 6 | Evidence distributed across multiple chunks |
| `synthesis` | 4 | Answer requiring at least three evidence chunks |

Benchmark status: AI-assisted and owner-approved. It must not be described as independently
human-authored or independently human-annotated. Relevance labels were completed by the human
owner, including a deterministic seed-42 second pass over 114 rows and owner adjudication of 14
disagreements. No AI-selected final grades were used.

Canonical pilot artifacts:

- Corpus chunks: `data/v2/pilot/chunks/chunks.jsonl`
- R5 questions: `data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl`
- Final pooled qrels: `runs/v2/phase6_seed42_final/qrels/phase6_final_pooled_qrels.tsv`
- Balanced metrics: `runs/v2/phase6_seed42_final/metrics/balanced_metrics.json`
- Corrected canonical status: `docs/PHASE6_SEED42_FINAL_CANONICAL_STATUS.md`

Frozen SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| 140 chunks | `70c1e3b8b0380809adea000654333a5921132ab7608ff328a9fa7934e8f43aa6` |
| 34 R5 questions | `0abd328ff639a05e80559202a018df0bd50aaf875f8d6b7753af925cc8a89c4b` |
| Final pooled qrels | `c167689e5f0a1e7412d17baab56c6789e1612bb08121255fc0c153fecd1e077f` |

## Phase-by-phase retrieval evidence

Scores from different rows below are not interchangeable. Phase 0 uses a 28-question historical
benchmark. Phases 2–5 use 34 R5 questions with incomplete direct-support qrels. Phase 6 uses final
pooled human-owner judgments for those same 34 questions. Phase 8 uses a different 100-question
automated benchmark pending human review. A higher number after judgment expansion does not by
itself mean a system improved.

### Phase 0 — historical forensic recomputation

These 28-query values reproduce committed historical artifacts. They are forensic findings, not
final inferential evidence.

| Historical system | MRR@10 | Recall@10 | Binary nDCG@10 | Graded nDCG@10 |
|---|---:|---:|---:|---:|
| BM25 | 0.8304 | 1.0000 | 0.8683 | 0.8405 |
| FAISS | 0.7958 | 0.8571 | 0.7742 | 0.7096 |
| Graph artifact | 0.6095 | 0.6875 | 0.5909 | 0.5760 |

Source: `audits/phase0/recomputed_metrics.json`. Phase 1 then created 22-document, 140-chunk,
34-question pilot benchmark; Phase 1 did not run retrievers and therefore has no retrieval score.

### Phases 2–5 — frozen 34-query known-gold diagnostics

Known-gold qrels identify benchmark authors' direct evidence but are not exhaustive relevance
judgments. Phase 5 froze Prompt-RAG rankings without calculating relevance metrics; its diagnostic
scores were calculated later in Phase 6 against same known-gold qrels.

| Phase | System introduced | MRR@10 | Recall@10 | Graded nDCG@10 | Complete Evidence Recall@10 | Branch status |
|---|---|---:|---:|---:|---:|---|
| 2A | BM25 | 0.8480 | 0.9706 | 0.8711 | 0.9706 | Main-canonical baseline |
| 2A | FAISS-windowed-max | 0.6578 | 0.9461 | 0.7097 | 0.9118 | Main-canonical baseline |
| 3G | Entity Graph v3.2 | 0.6422 | 0.6618 | 0.6118 | 0.6176 | Main-canonical baseline |
| 4 | Hybrid RRF | 0.8824 | 0.9706 | 0.8839 | 0.9706 | Main-canonical after merge `6049994` |
| 5D/6 | Prompt-RAG Claude | 0.9632 | 1.0000 | 0.9577 | 1.0000 | Main-canonical after merge `6049994` |

Graph seeded 24 of 34 queries (70.59%); all six paraphrase and all four synthesis queries had no
graph seed. Prompt-RAG's BM25 top-50 candidate recall ceiling was 0.9490, so reranking could not
recover evidence outside that candidate set.

### Operational measurements from Phases 2–5

Local retriever latency used frozen warm-index protocols. Prompt-RAG latency came from external
provider calls and is not directly comparable with local warm-cache latency.

| System | Mean latency | Median | p95 | Build/index evidence | Measurement note |
|---|---:|---:|---:|---|---|
| BM25 | 0.760 ms | 0.748 ms | 1.065 ms | 0.085 s build; 494,370-byte state/provenance | Warm persisted index, 680 samples |
| FAISS-windowed-max | 13.242 ms | 12.707 ms | 15.601 ms | 3.947 s build; 613,089-byte index | Warm loaded model/index, 680 samples |
| Entity Graph v3.2 | 0.559 ms | 0.614 ms | 0.789 ms | 13.407 s build; 732,942-byte graph/registry/config footprint | Warm persisted graph |
| Hybrid RRF | 0.931 ms | 0.948 ms | 1.247 ms | No additional index | Sequential BM25 + Graph + fusion; warm cache, 680 samples |
| Prompt-RAG Claude | 18.086–26.055 s | 14.485–24.607 s | 30.106–34.329 s | No additional local index | Separate trace/recovery API segments; observed Phase 5 cumulative cost `$1.980933` |

Hybrid latency is warm-cache operational latency, not cold-start latency. Prompt-RAG range reports
two preserved execution segments rather than combining unlike samples into one statistic.

## Final pilot retrieval results

Final pooled metrics use 34 questions and human-owner pooled relevance judgments. Values below
are macro means across queries. Five-system table is supported by committed artifacts now present
on `origin/main`.

| System | MRR@10 | Recall@10 | Graded nDCG@10 | Complete Evidence Recall@10 |
|---|---:|---:|---:|---:|
| BM25 | 0.9412 | 0.8008 | 0.8235 | 0.4118 |
| FAISS-windowed-max | 0.8279 | 0.7001 | 0.6883 | 0.2941 |
| Entity Graph v3.2 | 0.6765 | 0.6103 | 0.6214 | 0.4118 |
| Hybrid RRF | 0.9559 | 0.8449 | 0.8783 | 0.5000 |
| Prompt-RAG Claude | 0.9779 | 0.8355 | 0.8907 | 0.5882 |

Prompt-RAG has highest MRR@10, graded nDCG@10, and Complete Evidence Recall@10 in this pilot;
Hybrid has highest Recall@10. These observations do not establish a universal winner. Category
slices are small (`N=4` or `N=6`) and all inferential conclusions remain exploratory.

### Preregistered pilot hypothesis outcomes

| Hypothesis | Frozen pilot outcome | Reason |
|---|---|---|
| **H1:** BM25 equivalent to FAISS on exact lookup + terminology | Inconclusive | Paired MRR@10 interval was not wholly inside preregistered ±0.05 equivalence margin. |
| **H2:** FAISS outperforms BM25 on paraphrase | Not supported | No balanced metric passed effect, confidence-interval, and Holm-adjusted randomization criteria. |
| **H3:** Graph outperforms BM25 and FAISS on entity relation and multi-hop | Not supported | No emphasized metric passed all preregistered criteria across required comparisons. |
| **H4:** Hybrid has highest aggregate MRR | Not supported | Hybrid passed only Graph comparison, not every frozen comparator. |
| **H5:** Retrieval quality does not translate monotonically into generation faithfulness | Exploratory result consistent with separation | MRR@10–faithfulness Spearman rho was -0.0333; no confirmatory threshold was preregistered. |

Detailed effects, intervals, tests, correction rules, and category results are stored in
`runs/v2/phase6_seed42_final/statistics/` and
`runs/v2/phase6_seed42_final/metrics/`.

### Phase 7 — generation-quality panel

Phase 7 generated 170 cited answers: 34 queries × 5 retrieval systems. Scores use a 0–2 scale
where higher is better, except unsupported-claim severity where lower is better. Twenty-six
records retain blinded human-owner scores; 144 use disclosed offline MiniLM-plus-5-NN scores.
Therefore this is an exploratory mixed-source evaluation, not a 170-answer human evaluation.

| Retrieval context | Correctness | Faithfulness | Completeness | Citation accuracy | Unsupported severity | Abstentions |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 1.6176 | 2.0000 | 1.5882 | 1.9706 | 0.0294 | 6 |
| FAISS-windowed-max | 1.1765 | 2.0000 | 1.1765 | 2.0000 | 0.0000 | 14 |
| Entity Graph v3.2 | 1.6471 | 1.9706 | 1.0588 | 1.9706 | 0.0294 | 16 |
| Hybrid RRF | 1.5588 | 2.0000 | 1.5294 | 1.9706 | 0.0294 | 7 |
| Prompt-RAG Claude | 1.7647 | 2.0000 | 1.7059 | 2.0000 | 0.0000 | 5 |

Exploratory query-level associations were: MRR@10–faithfulness Spearman rho `-0.0333`,
MRR@10–correctness `0.1753`, graded nDCG@10–correctness `0.2700`, and Complete Evidence
Recall@10–completeness `0.3395`. No confirmatory H5 threshold was preregistered, so these are
descriptive results only. Full disclosure: `docs/PHASE7_FINAL_AI_EVALUATED_STATUS.md`.

### Phase 8 — expanded automated diagnostic

Committed Phase 8 diagnostic uses 130 documents, 856 chunks, and 100 automated questions. Human
benchmark review and owner approval remain incomplete. Values below must not be cited as final
dissertation findings or mixed with 34-query pilot results.

| System | MRR@10 | Recall@10 | Graded nDCG@10 | Precision@10 | Mean retrieval latency |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.5813 | 0.7750 | 0.6017 | 0.1110 | 1.12 ms |
| FAISS-windowed-max | 0.4662 | 0.6100 | 0.4637 | 0.0860 | 22.23 ms |
| Entity Graph | 0.1537 | 0.3050 | 0.1756 | 0.0420 | 51.34 ms |
| Hybrid RRF | 0.4177 | 0.6100 | 0.4209 | 0.0840 | 52.46 ms |
| Prompt-RAG Claude | 0.5866 | 0.7750 | 0.6176 | 0.1110 | Not reported in retrieval CSV |

Phase 8 Prompt-RAG retrieval reranking used 100 valid primary records (95 new plus five exact
trace reuses), zero failures, 846,508 provider input tokens, 11,528 output tokens, and `$0.904148`
observed cost. No Phase 8 answer-generation run is represented by this table. Automated freeze
status: `audits/phase8_exploratory/automated_r3_freeze.json`.

Machine-readable score sources:

- Canonical five-system registry: `runs/CANONICAL_EVIDENCE.json`
- Consolidated canonical view: `runs/canonical_v2_pilot/`
- Phase 0: `audits/phase0/recomputed_metrics.json`
- Phase 2: `runs/v2/phase2a_r5_windowed/metrics/balanced_metrics.json`
- Phase 3: `runs/v2/phase3_graph_v3_2/metrics/balanced_known_gold_metrics.json`
- Phase 4: `runs/v2/phase4_hybrid/metrics/balanced_known_gold_metrics.json`
- Phase 5 operational evidence:
  `runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/operational_summary.json`
- Phase 6: `runs/v2/phase6_seed42_final/metrics/balanced_metrics.json`
- Phase 7: `runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/h5_results.json`
- Phase 8:
  `runs/phase8_exploratory_five_system/*/metrics/` and committed freeze manifests

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Historical forensics, metric correction, protocol | Complete |
| 1 | Corpus and 34-question R5 pilot benchmark | Complete |
| 2 | BM25 and FAISS-windowed-max baselines | Complete |
| 3 | Corrected Entity Graph v3.2 | Complete |
| 4 | BM25 + Graph Hybrid RRF | Complete |
| 5 | BM25 top-50 → Claude Prompt-RAG reranker | Complete |
| 6 | Blind pooled judging, regrade, adjudication, final retrieval metrics | Complete |
| 7 | 170-answer generation and H5 panel | Complete as disclosed AI-evaluated exploratory pilot |
| 8 | Expanded 100-query retrieval diagnostic | Automated exploratory run complete; human validation and owner approval pending |

Failed Gemini and earlier Claude attempts remain archived as audit evidence. They are not selected
or rewritten as successful outputs.

## Two dataset scopes in this repository

Do not mix results from these scopes:

| Scope | Purpose | Documents | Chunks | Questions | Review status |
|---|---|---:|---:|---:|---|
| `data/v2/pilot/` | Dissertation pilot used for Phases 1–7 | 22 | 140 | 34 | Owner-approved questions; final pooled owner judgments complete |
| `releases/v3_clean/` | Expanded deterministic corpus/release engineering work | 130 | 856 | 100 | Benchmark remains exploratory pending manual audit |

Phase 6 and Phase 7 findings in this README apply only to the 34-question V2 pilot. Expanded
`v3_clean` artifacts must not be used to imply that final-scale evaluation is complete.

## Installation

### Requirements

- Python 3.10 or newer
- Git
- Enough disk space for sentence-transformer and spaCy models
- macOS or Linux recommended; Windows users may need WSL for FAISS compatibility

### Clone correct branch

```bash
git clone https://github.com/amulyagupta1278/rag-retrieval-dissertation.git
cd rag-retrieval-dissertation
git checkout codex/dissertation-rebuild-v2
```

### Create environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell activation:

```powershell
.venv\Scripts\Activate.ps1
```

Install spaCy English model only when rebuilding or running graph components:

```bash
python -m spacy download en_core_web_sm
```

## Offline verification

No API key is needed to inspect frozen artifacts, recalculate offline metrics, or run tests.

```bash
# Full test suite
python -m pytest -q

# Focused canonical Phase 6 checks
python -m pytest -q \
  tests/test_phase6_seed42_final.py \
  tests/test_finalize_phase6_seed42.py \
  tests/test_evaluate_phase6_seed42.py \
  tests/test_phase7_gate.py

# Git whitespace check
git diff --check
```

Inspect final balanced retrieval metrics:

```bash
python -m json.tool \
  runs/v2/phase6_seed42_final/metrics/balanced_metrics.json
```

Check key artifact hashes with a cross-platform Python command:

```bash
python - <<'PY'
from hashlib import sha256
from pathlib import Path

for name in (
    "data/v2/pilot/chunks/chunks.jsonl",
    "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl",
    "runs/v2/phase6_seed42_final/qrels/phase6_final_pooled_qrels.tsv",
):
    path = Path(name)
    print(sha256(path.read_bytes()).hexdigest(), name)
PY
```

## API execution boundary

Frozen Phase 5 and Phase 7 outputs are committed. Re-running paid API experiments is unnecessary
for ordinary verification.

Live Claude execution requires a user's own `ANTHROPIC_API_KEY`, explicit owner approval, and
budget acknowledgement. Never commit credentials. `.env` is ignored by Git. API-based outputs
may not be byte-identical across reruns even with the same named model, so committed requests,
responses, usage records, hashes, and manifests are the primary audit evidence.

Do **not** run these scripts as routine setup:

- `scripts/run_phase5d_prompt_rag_claude.py`
- `scripts/run_phase5d_v2_prompt_rag_claude.py`
- `scripts/run_phase5d_v3_transport_recovery.py`
- `scripts/run_phase7_generation_trace.py`
- `scripts/run_phase7_v2_generation_trace.py`
- `scripts/run_phase7_v2_full_panel.py`

They are controlled experiment runners, not demo commands. Some can incur monetary cost or stop
on frozen lifecycle gates.

## Metrics

Retrieval metrics are reported in aggregate and per category, always with query count:

- MRR@5 and MRR@10
- Recall@5 and Recall@10
- Hit Rate@5 and Hit Rate@10
- Judged-gold Precision@5 and Precision@10
- Binary and graded nDCG@10
- Complete Evidence Recall@5 and Complete Evidence Recall@10
- Mean, median, and p95 latency plus available build/index measurements

Metrics are never averaged into a composite score. Contradictory results remain visible.

Phase 7 answer-quality dimensions are separate: correctness, faithfulness, completeness, citation
accuracy, unsupported claims, and abstention quality. Mechanical validation covers all 170
answers. Twenty-six blinded records were scored by the human owner; 144 were scored by a pinned
offline MiniLM-plus-5-NN procedure trained on those owner records. These results must not be
described as 170 human-reviewed answers. Full disclosure and H5 results are in
`docs/PHASE7_FINAL_AI_EVALUATED_STATUS.md`.

## Repository map

```text
.
├── archive/                 # Preserved failed/obsolete provider routes
├── audits/                  # Integrity, leakage, provenance, freeze, and review evidence
├── configs/                 # Frozen system and experiment configurations
├── data/v2/pilot/           # Canonical 22-document, 140-chunk pilot inputs
├── docs/                    # Protocols, correction notices, and phase decisions
├── experiments/             # Baseline ingestion/retrieval entry points
├── indexes/                 # Persisted BM25, FAISS, and graph indexes
├── prompts/                 # Frozen Prompt-RAG and generation prompts
├── releases/                # Historical and expanded deterministic releases
├── runs/v2/                 # Frozen rankings, metrics, statistics, and generation evidence
├── scripts/                 # Auditable phase runners and validators
├── submission/              # Current report draft, dashboard, and defense deck
├── src/                     # Ingestion, retrieval, evaluation, generation, and utilities
└── tests/                   # Offline contract, integrity, and regression tests
```

## Submission assets

Current submission-facing files are grouped under `submission/`:

- Dissertation report draft: `submission/FINAL_DISSERTATION_REPORT_DRAFT.md`
- Interactive results dashboard: `submission/dashboard/index.html`
- Defense presentation: `submission/presentation/RAG_Dissertation_Defense_Amulya_Gupta.pptx`

Historical mid-semester reports remain at repository root because frozen audits and conversion
scripts reference their exact paths. They are provenance records, not current submission files.

## Reproducibility statement

Another researcher with repository access can clone the results branch, install dependencies,
run offline tests, verify hashes, inspect frozen rankings/responses, and recalculate metrics.

Limits:

- `requirements.txt` constrains most packages by minimum version rather than providing a complete
  platform-specific lockfile.
- FAISS, spaCy, and embedding-model installation may vary by operating system.
- Live provider responses are rerunnable under a frozen contract but are not guaranteed
  byte-identical.
- Pilot findings use 34 questions and cannot be generalized as final-scale evidence.

Therefore, strongest accurate claim is: **committed pilot artifacts are auditable and
numerically reproducible; live API generation is protocol-reproducible, not guaranteed
bit-for-bit reproducible.**

## Viva quick answers

**What did you build?**

A controlled pipeline comparing sparse, dense, graph, fused, and LLM-reranked retrieval, followed
by a shared answer-generation experiment.

**How is comparison fair?**

Every system uses the same 140 chunks, 34 questions, chunk IDs, pooled owner judgments, metric
definitions, and frozen configurations. No retriever receives hidden gold evidence.

**Is Prompt-RAG a generator?**

No. Phase 5 Prompt-RAG reranks BM25's top 50. Phase 7 performs answer generation separately.

**Why not declare one best system?**

Systems lead on different metrics and categories. Protocol forbids composite scores and universal
winner claims.

**Are findings final?**

No. They are exploratory pilot evidence. Expanded final-scale evaluation remains Phase 8 work.

**Can another person run it without your API key?**

Yes for offline tests, hash verification, rankings, metrics, and committed outputs. New live
Claude calls require their own key and budget.

## Research-integrity notes

- Historical files and failed runs remain preserved rather than rewritten.
- Correction documents distinguish numerically recomputable results from fully reproducible
  claims.
- Human-owner labels are identified as such; AI assistance is disclosed.
- Unjudged chunks are not silently treated as independently verified nonrelevance.
- Negative, weak, and inconclusive hypothesis outcomes remain reported.
- Exact paths, hashes, configs, and lifecycle approvals are stored under `audits/` and `runs/v2/`.
