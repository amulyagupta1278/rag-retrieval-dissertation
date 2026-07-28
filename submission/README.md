# Submission assets

This directory contains current presentation-facing outputs for frozen Phase 1–7 pilot.

## Files

- `FINAL_DISSERTATION_REPORT_DRAFT.md` — technical dissertation draft grounded in frozen pilot evidence.
- `dashboard/index.html` — standalone interactive retrieval and H5 results dashboard.
- `presentation/RAG_Dissertation_Defense_Amulya_Gupta.pptx` — visually verified 10-slide defense deck.

## Canonical research freeze

- Branch: `codex/dissertation-rebuild-v2`
- Pilot tag: `pilot-v2-phase7-final-20260729`
- Pilot freeze commit: `40aad1ad5de128a376cf25584d8a7f9d6aa36914`
- Submission-assets source commit: `dc60257`

Submission assets summarize evidence; they do not replace canonical artifacts under `data/`,
`runs/`, `audits/`, or `releases/`.

## Regeneration

Run `python scripts/build_submission_assets.py` to rebuild report draft and dashboard from frozen
Phase 6 and Phase 7 JSON artifacts. PowerPoint deck is committed as reviewed binary output; its
temporary render/layout QA files are intentionally excluded.
