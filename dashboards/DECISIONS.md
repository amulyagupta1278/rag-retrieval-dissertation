# Dashboard decisions

1. Freeze evidence commit `7bc5bda9c6fc01964bab0247145699fe14e35175` because it
   contains both seed-42 Phase 6 retrieval evidence and frozen Phase 7 H5 results.
2. Read every study input from exact Git tree using `git show`; do not merge later-branch
   non-dashboard files into dashboard PR.
3. Generate one `dashboard_payload.json` in Gate 1. Both screens render it and perform no
   independent metric calculation.
4. Use `final_pooled` owner-adjudicated qrels as primary basis. Reconcile known-gold only as
   secondary robustness check; never mix bases.
5. Block seed-123 invalid statistics and qrels before Git access.
6. Preserve real H5 aggregate only: MRR@10–faithfulness and complete-evidence-recall–completeness
   Spearman statistics with frozen CIs and 26 human/144 offline-AI label disclosure. No scatter.
7. Treat FAISS as dense-vector baseline. “Vector-free” applies only to BM25, Graph, Hybrid, and
   Prompt-RAG reranking.
8. Use difficulty `1 − systems hitting@5 / 5`; Screen 2 places harder items to right.
9. Use exact tied maxima for category and query co-leaders. Never choose first system in a tie.
10. Map 3D field only to observed values: x=difficulty, y=mean MRR@10, z=category band.
11. Use 10,000 whole-query bootstrap samples, seed 42, for derived descriptive CIs.
12. Vendor and inline exact GSAP 3.12.5 and Three.js r128 bytes. Core and enhancements run offline.
13. Keep Screen 1 as citable record and Screen 2 as exhibit only. No router or universal winner claim.
