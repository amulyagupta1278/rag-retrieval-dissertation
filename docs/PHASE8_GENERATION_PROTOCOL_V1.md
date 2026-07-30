# Phase 8 Generation Protocol V1

Status: frozen before outputs; execution unauthorized.

## Scope

- Base commit: `811c9a0b507f6ac154bb08542dd9ca37988c8e3f`
- Sample: 20 deterministic questions, seed 42; four from each available category.
- Frozen Phase 8 benchmark categories: entity_relation, exact_match, multi_hop, paraphrase, terminology_heavy.
- Limitation: benchmark has no synthesis category. No sixth category was fabricated.
- Systems: BM25, FAISS windowed-max, Graph v3.2, Hybrid RRF, Prompt-RAG Claude.
- Panel: 20 questions x 5 systems = 100 requests.
- Context: first three results from each system's frozen top-10 ranking. Every supplied chunk is therefore inside that system's top 10.

## Fixed generation contract

- Model: `claude-haiku-4-5-20251001`
- Prompt: `prompts/phase7_answer_generation_v1.txt`
- Temperature: 0
- Maximum output: 512 tokens
- Strict JSON schema; inline evidence citations `E01`-`E03`
- Zero retries, fallback, replacement, tools, or external knowledge
- Pre-dispatch ledger and cumulative projected-cost gate
- Trace and full outputs use separate directories

Requests expose question and anonymized evidence only. System identity, ranks, scores, category, qrels, reference answer, and gold evidence remain sealed from model and blinded evaluation package.

## Evaluation rubric

Dimensions remain separate: correctness, faithfulness, completeness, citation accuracy, unsupported-claim severity, and abstention quality. Quality dimensions use 0=poor, 1=partial, 2=good. Unsupported-claim severity uses 0=none, 1=minor, 2=central. No composite score. AI evaluation requires separate disclosure and approval; human validation remains incomplete.

## Cost and stop gates

- Five-request trace cap: $0.10
- Cumulative 100-request generation hard cap: $1.25
- One ambiguous-dispatch reserve included in each projection
- Stop after trace. Remaining 95 requests require separate approval.
