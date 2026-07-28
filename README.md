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

This repository contains a controlled pilot comparison of five retrieval systems and a
downstream answer-generation experiment. Work is frozen through Phase 7 evaluation on branch
`codex/dissertation-rebuild-v2`.

- Phase 6 retrieval evaluation is complete on 34 owner-approved questions and final pooled
  human-owner relevance judgments.
- Phase 7 generated and evaluated all 170 planned answers: 34 questions × 5 retrieval systems.
  Twenty-six blinded answers retain human-owner scores; 144 carry disclosed offline AI scores.
  Mechanical validation, owner-audit agreement, and exploratory H5 analysis are frozen.
- Phase 8 final-scale expansion is a separate, unexecuted decision. Pilot results must not be
  described as final population-level evidence.

The title focuses on vector-free alternatives, but the experiment also includes FAISS as a
dense-vector baseline. It does **not** claim that every compared system is vector-free.

## Project in 60 seconds

1. Twenty-two government-scheme source documents were cleaned and divided into 140 retrieval
   chunks.
2. A frozen benchmark contains 34 questions across six query categories.
3. BM25, FAISS, an entity graph, a BM25–graph hybrid, and an LLM reranker rank the same chunks.
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

## Systems compared

| System | What it does | Frozen implementation |
|---|---|---|
| **BM25** | Matches query terms to chunk terms using sparse lexical scoring. | `k1=1.5`, `b=0.75`; deterministic chunk-ID tie-break. |
| **FAISS-windowed-max** | Uses dense semantic similarity. Each chunk is split into token-aware windows; best window becomes chunk score. | `sentence-transformers/all-MiniLM-L6-v2`, pinned revision, 254-content-token windows, 32-token overlap, normalized embeddings, `IndexFlatIP`. |
| **Entity Graph v3.2** | Finds corpus-backed entities in query, then traverses chunk/entity co-occurrence graph. | Exact normalized alias matching, maximum two-hop path, no lexical fallback, deterministic ranking. |
| **Hybrid RRF** | Combines BM25 and Entity Graph rankings using Reciprocal Rank Fusion. | Equal weights, `RRF k=60`, input/output depth 50. |
| **Prompt-RAG Claude** | Reranks frozen BM25 top-50 candidates with an LLM relevance scorer. | `claude-haiku-4-5-20251001`, integer score 0–3 for every candidate, score-descending then chunk-ID tie-break, no fallback. |

### Important terminology

`Prompt-RAG` in this repository is a **retrieval reranker**, not answer generation. It cannot
retrieve outside the BM25 top-50 candidate set; its measured candidate-recall ceiling is 0.9490.

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

## Final pilot retrieval results

Final pooled metrics use 34 questions and human-owner pooled relevance judgments. Values below
are macro means across queries.

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
| 8 | Final-scale corpus/benchmark expansion | Planning only; owner decision required |

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
