# Phase 9 H5c-v2 Recovery Amendment

Status: **frozen before H5c-v2 execution**.

H5c-v1 stopped after request 6 returned `max_tokens` at its frozen 512-token output limit.
Five valid v1 responses are not reused. H5c-v2 is a fresh 60-request panel with new blinded IDs
and separate outputs. Question selection, evidence conditions, prompt, model, temperature, seed,
primary endpoint, statistical test, support threshold, blinding, and review rules remain unchanged
from `PHASE9_H5C_PREREGISTRATION.md`.

Only planned change: maximum output increases from 512 to 1,024 tokens. Retry count remains zero.
No v2 request may replace, merge with, or overwrite a v1 response. User-approved v2 hard cost cap:
**$0.597256**, including one ambiguous-dispatch reserve. Execution must refuse before dispatch if
projected exposure exceeds this cap.

Original H5 status remains `not_estimable`. H5c-v2 may support H5c only.
