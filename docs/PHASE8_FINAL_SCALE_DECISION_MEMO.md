# Phase 8 Final-Scale Decision Memo

Status: `owner_decision_required_no_option_selected`

Current pilot contains 22 committed documents, 140 chunks, and 34 questions across
six categories. Category counts are exact lookup 6, terminology 6, paraphrase 6,
entity relation 6, multi-hop 6, and synthesis 4. Two long guideline documents
contribute 65/140 chunks (46.4%), creating a corpus-size imbalance worth disclosing.
Pilot results remain development evidence, not final dissertation evidence.

## Option A — staged corpus ramp

Acquire official sources in preregistered stages near 45, 70, and 100 documents.
Each stage requires source provenance, chunk rebuild, benchmark review, pooled
judging, and complete five-system reruns.

| Dimension | Assessment |
|---|---|
| Acquisition | High: 23, then 48, then 78 additional documents from current 22 |
| QA/qrels | High; every stage needs new evidence-backed questions and pooled review |
| Owner judging | Highest; candidate pools scale with questions and systems |
| Rerun cost | Highest; retrieval and generation repeat at each frozen stage |
| Leakage risk | Medium-high unless future questions are sealed before system work |
| Time risk | High; source/version cleanup and judging dominate schedule |
| Dissertation strength | Broadest corpus evidence if all stages finish correctly |
| Reproducibility | Strong only if every stage is separately hashed and frozen |

Do not treat approximate document targets as automatic inclusion quotas. Every
document still needs official-source, version, and scheme rationale.

## Option B — locked pilot plus independent holdout

Keep current pilot as development set. Create 10–20 new owner-reviewed questions
that are never used for system development, cover all six categories, emphasize
underrepresented schemes, and freeze labels before any system execution. Report
holdout separately; do not merge it silently into pilot results.

| Dimension | Assessment |
|---|---|
| Acquisition | Low-medium; may reuse frozen corpus or add narrowly justified sources |
| QA/qrels | Moderate; 10–20 questions need full evidence and duplicate review |
| Owner judging | Moderate; smaller blind union pool than staged ramp |
| Rerun cost | Moderate; one locked five-system holdout run plus generation if approved |
| Leakage risk | Lowest if questions/labels freeze before execution |
| Time risk | Lower and more predictable near submission |
| Dissertation strength | Stronger independence claim, narrower corpus generalization |
| Reproducibility | Strong with sealed holdout version and one preregistered run |

## Required owner decision

Choose A, B, or a separately specified design. Decision must set document/question
scope, source policy, owner-review workload, schedule, monetary cap, and whether
Phase 7 generation applies to pilot, holdout, or both. This memo makes no choice.

