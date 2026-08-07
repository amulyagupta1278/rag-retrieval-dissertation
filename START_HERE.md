# Start here

Domain-specific retrieval evaluation for government policy RAG.
Amulya Gupta · 2024AB05200 · BITS Pilani WILP.

If you are examining this work, everything you need is in the four files below.
Everything else in this repository is supporting evidence for them.

---

## The four things that matter

| What | Where |
|---|---|
| **The dissertation** | `DISSERTATION_WILP_FINAL_SUBMISSION.pdf` (and `.docx`) |
| **The defence deck** | `defence/RAG_Dissertation_Defence_v2.pptx` |
| **The live evidence demo** | `defence/retrieval_evidence_demo.html` — open in any browser |
| **The canonical results** | `runs/canonical_v2_pilot/` |

`defence/DEFENCE_SCRIPT_AND_QA.md` holds the speaking notes and prepared answers.

---

## What this work claims

On a corpus of 22 Indian government policy documents, BM25 — lexical keyword ranking —
matched or beat dense embedding retrieval on five of six question categories, at roughly
1/17th the latency and with no GPU, embedding model or API cost.

The gap was widest on paraphrase queries, which is the category dense retrieval is
specifically expected to win.

**What it does not claim:** decisive statistical superiority. Paired confidence intervals
cross zero at this sample size. The claim is a consistent directional finding, reproduced on
an independent holdout, with an identified mechanism — plus a reusable benchmark so the
question can be settled at larger n.

---

## Canonical evidence

`runs/canonical_v2_pilot/` is the single authoritative results directory. Nothing outside it
should be cited as confirmatory.

```
benchmark/questions_r5.jsonl          34 owner-approved questions
benchmark/final_pooled_qrels.tsv      183 human relevance judgements, pooled across systems
retrieval/{system}_top50.jsonl        frozen rankings, 5 systems
metrics/system_comparison_table.json  aggregate metrics
metrics/efficiency_snapshot.json      latency, index size, cost
statistics/preregistered_h1_h4_results.json   frozen hypothesis tests
manifest.json                         hashes and provenance
```

Aggregate MRR@10, recomputed directly from the ranking and qrels files:

| System | MRR@10 | Mean latency |
|---|---:|---:|
| Prompt-RAG (LLM rerank) | 0.9779 | ~18 s |
| Hybrid RRF | 0.9559 | 0.93 ms |
| **BM25** | **0.9412** | **0.76 ms** |
| FAISS (dense) | 0.8279 | 13.2 ms |
| Entity Graph | 0.6765 | 0.56 ms |

Verify these numbers yourself:

```bash
python scripts/verify_headline_numbers.py
```

It reads the canonical files and recomputes every figure quoted in the deck.

---

## Evidence tiers — read this before citing anything

Not all results in this repository carry the same weight. The distinction is deliberate.

**Confirmatory.** `runs/canonical_v2_pilot/` — 34 questions, human-graded, blind regrade at
κ = 0.7421, disagreements adjudicated. Cite this.

**Generalisation.** `runs/phase8_option_b_holdout/` — 12 fresh questions on independently
acquired documents, all configurations frozen beforehand. Supports directional claims.

**Exploratory only.** `runs/phase8_r4_*` and the 130-document scale runs — labels are
AI-assigned with no human-labelled overlap. These demonstrate that the pipeline scales.
They are not evidence that the findings hold. Do not cite them as confirmatory.

---

## Repository map

```
defence/       Deck, live demo, script and Q&A prep
runs/          All experimental runs; canonical_v2_pilot/ is authoritative
data/          Corpus, chunks, questions, relevance labels
releases/      Frozen, hash-manifested release bundles (v2_serialized, v3_clean)
audits/        Per-phase audit trail, including preserved failures
docs/          Protocols, preregistrations, phase reports
submission/    Figures, dashboard, human review packages
src/ scripts/  Implementation and tooling
archive/       Superseded drafts and build notes — kept for history, not current
```

---

## A note on the audit trail

`audits/` contains preserved failure records — runs that were abandoned rather than retried,
with the reason recorded. `archive/` holds superseded drafts. Neither is clutter: the
preregistration protocol required that failed executions be preserved rather than silently
replaced, and both directories exist so that claim can be checked.
