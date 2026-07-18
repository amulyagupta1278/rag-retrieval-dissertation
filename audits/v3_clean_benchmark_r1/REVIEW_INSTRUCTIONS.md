# Benchmark Audit Instructions

Audit remains blocked until primary reviewer completes all 100 question rows and all pooled judgment rows. Do not change question IDs or chunk IDs.

For `question_audit_100.csv`, set `status=complete`, record reviewer, complete every boolean field, and explain every rejection in `rationale`. Replace rejected questions before publication; do not mark invalid questions complete. Second reviewer completes 20 rows marked `second_review_required`.

For `pooled_top5_blind.csv`, assign binary relevance (`0` or `1`). System names and ranks are intentionally absent. Explain judgment changes from original relevance. Run `scripts/finalize_qrels_audit.py`.
