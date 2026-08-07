# Final dissertation dashboard data contract

Dashboard presents three retrieval evidence tiers plus Phase 9 generation evidence. It must not
merge tiers into one leaderboard or promote exploratory results to confirmatory claims.

## Evidence hierarchy

1. **R4 main benchmark:** 130 documents, 954 chunks, 100 questions (60 development, 40 locked).
   Dashboard opens on locked-test results. Prompt-RAG appears here because its complete R4 run is
   valid for benchmark comparison.
2. **Independent holdout:** 12 frozen questions and 21 relevance judgements. This is canonical for
   final H1–H4 verdicts. Prompt-RAG is excluded because the zero-retry execution contract was not
   completed.
3. **Legacy pilot:** 22 documents, 140 chunks, 34 questions. Retain only as development provenance;
   never use it as the default leaderboard or final hypothesis evidence.
4. **Phase 9 H5 panel:** 150 answers, 301 scored claims, and 69 abstentions. H5 is **not estimable**
   because faithfulness SD (0.0111) failed the preregistered 0.10 variation gate.

## Final dashboard files

| File | Purpose |
|---|---|
| `../dashboard/index.html` | Standalone responsive interface |
| `../dashboard/data.js` | Browser-ready payload generated only from frozen artifacts |
| `../../scripts/build_final_dashboard_data.py` | Deterministic payload builder |

Rebuild from repository root:

```bash
python scripts/build_final_dashboard_data.py
```

## Required presentation rules

- Label locked test `n=40` and holdout `n=12` at point of use.
- State directional or inconclusive verdicts exactly; do not convert them into confirmations.
- Show Prompt-RAG in R4 and mark it excluded in holdout.
- Do not interpret H5's correlation after its variation gate failed.
- Show abstention as dominant generation failure mode; do not describe it as hallucination.
- Preserve exact FAISS description: normalized 384-dimensional embeddings with `IndexFlatIP`,
  equivalent to exact cosine search.
- Expose source artifact paths and repository commit in evidence view.

Files elsewhere in `submission/dashboard_data/` are historical handoff artifacts. They remain for
provenance but do not override this final contract or `submission/dashboard/data.js`.
