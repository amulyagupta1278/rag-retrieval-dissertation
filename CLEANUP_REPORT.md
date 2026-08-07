# Cleanup Report — Pre-Viva Repo Handover

Generated during a full repo audit ahead of the viva defence. Covers git state, secrets,
gitignore correctness, reproducibility, size, doc coherence, and tests.

## What changed

**Git state**
- Committed 58 modified + 17 untracked files as 12 logical commits (archived superseded
  drafts, docs status fix, START_HERE, final submission docx/pdf, verification/dashboard
  scripts, refreshed release/run/index outputs, updated qa dataset, defence deck,
  gitignore + recovered release files, missing dependencies, archived stale Phase 7 docs).
- Fast-forwarded `main` to include everything (Phase 8 holdout eval, Phase 8 hypothesis
  verdicts, Phase 9 H5 evidence, plus this cleanup).
- Opened PR #7 (`codex/phase9-cleanup-handover-v2` → `main`) — **this repo requires all
  changes to go through a reviewed PR, even on your own branches; direct pushes to any
  ref are blocked by a repo-wide ruleset.** PR #7 is mergeable but needs your approval
  before `main` on GitHub reflects this work.
- Deleted 7 branches confirmed fully merged into `main`: `backup/pre-rollback-20260719`,
  `codex/corpus-expansion-stress-test`, `codex/dissertation-rebuild-v2`,
  `codex/phase8-exploratory-expansion`, `codex/phase8-r4-improvements`, `test`,
  `codex/phase9-evidence`. Kept `feat/dashboard` (has 3 commits not on `main`).

**Secrets** — none found. `.env` was never committed on any branch, ever. No live API
keys in tracked files.

**.gitignore contradictions** — fixed the rules, not the tracking, per your framing:
- `releases/` and `indexes/baselines/` blanket rules were silently dropping *new* files
  added under those trees after the rule existed. This wasn't cosmetic: 14 files
  (release config JSONs, the v3_clean/v2_serialized bm25 indexes) were missing from git
  even though `releases/v3_clean/manifests/SHA256SUMS` already listed their checksums.
  Verified each recovered file's SHA-256 against the manifest before re-adding, then
  removed the blanket rules and scoped `*.pkl` with explicit negations instead.

**Reproducibility**
- Added `python-dotenv`, `scipy`, `scikit-learn`, `openpyxl` to `requirements.txt` and
  `pyproject.toml` — imported by 5+ scripts (Phase 9 H5 analysis, `.env` loading) but
  never declared; a clean `pip install` would have broken on first run of those scripts.
- Deleted the `node_modules` symlink (pointed to your personal `~/.cache/codex-runtimes/`
  path — broken for anyone else). No `package.json` exists anywhere in the repo, so it
  wasn't reproducible via a package manager either way; it only served one archived
  script (`archive/build_notes/generate_dissertation.js`), already superseded by the
  final committed docx/pdf.
- Makefile targets and all paths in START_HERE.md/README.md were verified to resolve —
  no action needed.

**Size and dead weight**
- Ran `git gc`: `.git` shrank 142MB → 86MB (205 loose objects reclaimed).
- Deleted `tmp/` (22MB, gitignored PDF audit scratch, confirmed unreferenced by any
  script), `defence/lu47m8rj.tmp`, `defence/.~lock.RAG_Dissertation_Defence_v2.pdf#`,
  and `archive/scratch_dirs/` (leftover session scratch, gitignored).

**Coherence**
- Archived 3 stale Phase 7 planning docs (`PHASE7_GENERATION_PROTOCOL_DRAFT.md`,
  `PHASE7_ANSWER_EVALUATION_RUBRIC_DRAFT.md`, `PHASE7_OWNER_DECISIONS_REQUIRED.md`) that
  described a pre-execution blocked state, even though Phase 7 has fully executed
  (170 generation observations, evaluated; evidence at
  `runs/v2/phase7_generation_claude_top3_v2/`). No other doc referenced them by path.
- `README.md` and `START_HERE.md` were checked and don't contradict each other.
- `runs/CANONICAL_EVIDENCE.json` hashes and paths verified to match reality.

## What you still need to decide

- **Approve/merge PR #7** on GitHub — nothing above lands on the default branch until
  you do. Link: `https://github.com/amulyagupta1278/rag-retrieval-dissertation/pull/7`
- If you ever want to rerun `archive/build_notes/generate_dissertation.js`, you'll need
  to `npm install docx` yourself first (no `package.json` exists to pin its version).

## Deliberately not touched

- `runs/canonical_v2_pilot/` — read-only, per your hard rule.
- `audits/` — not modified, per your hard rule. Includes the one known test failure
  below.
- `feat/dashboard` branch — has 3 commits not on `main`, needs separate review before
  deciding to merge or drop.
- The 3 large `runs/phase8_exploratory_five_system/*/retrieval/*.jsonl` files
  (15-16MB each) — kept as-is; they're intentional experiment output and rewriting
  history to move them to LFS would violate the no-history-rewrite rule.
- Duplicate-looking artifacts across `data/`, `indexes/`, `releases/`, and
  `indexes/baselines/serialized_json_baseline/` (`bm25_index.pkl`, `chunks.jsonl`,
  `faiss.index`, `graph.gpickle`, etc.) — these are legitimately different: a frozen
  historical baseline vs. the active v3_clean release vs. working indexes, not
  accidental duplication.

## Known test failure (not fixed, per instruction)

`tests/test_lifecycle_supersessions.py::test_current_phase4_checkpoint_is_explicitly_recorded`
fails: it checks a hardcoded SHA-256 in `audits/lifecycle_supersessions/expected_failures.json`
against a frozen Phase 4 checkpoint. 125 legitimate post-Phase-4 commits changed files
the fixture didn't account for. This is documented drift, not a code regression — but
since `audits/` is off-limits to modify, it's reported here for you to decide (re-freeze
the hash, or accept and leave it). Full suite: 555 passed, 1 failed, 17 xfailed (99.82%).

## Verification run

- `python scripts/verify_headline_numbers.py` → exit 0, all figures match.
- `git status --porcelain` → clean.
