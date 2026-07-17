# Benchmark Audit Instructions

The audit remains blocked until a reviewer completes all 60 question rows and all pooled judgment rows. Do not change question IDs or chunk IDs.

For `question_audit_60.csv`, set `status=complete`, record the reviewer, complete every boolean review field, and explain every rejection or correction in `rationale`.

For `pooled_top3_judgments.csv`, set `review_status=complete`, reviewer, and relevance (`0`, `1`, or `2`) for every candidate. Explain any judgment that differs from `original_relevance`. Convert the reviewed sheet back to JSONL before running `scripts/finalize_qrels_audit.py`.
