# Repo cleanup prompt for Claude Code

Copy everything inside the block below into Claude Code, run from the repo root.

---

```
This is my M.Tech dissertation repository (RAG retrieval evaluation on Indian government
policy documents). It has been submitted and I have a viva defence in under a week. An
examiner may clone this repo and look around. I need it clean, coherent and safe to hand over.

Work through the audit below. Show me findings and a plan BEFORE changing anything
destructive.

## Hard rules

- Never `rm` anything without showing me the list and getting explicit confirmation first.
  Prefer `git mv` / `mv` into `archive/` over deletion.
- Never rewrite git history (no rebase, filter-branch, filter-repo, force-push) unless I
  explicitly ask in a later message.
- Never commit or print the contents of `.env`.
- Do not touch `runs/canonical_v2_pilot/` — that is my frozen canonical evidence. Read it,
  never modify it.
- Do not modify anything under `audits/`. It is a deliberate audit trail including
  preserved failure records.
- `scripts/verify_headline_numbers.py` must still exit 0 when you are finished.

## 1. Git state — do this first, it is the biggest risk

- I am on branch `codex/phase9-evidence-final`, not `main`. There are 10 branches including
  `backup/pre-rollback-20260719`, several `codex/*`, `feat/dashboard` and `test`.
- Tell me what is on `main` versus my current branch, and whether the submitted dissertation
  work exists on `main` at all.
- 58 modified and 17 untracked files are uncommitted. Group them by intent and propose
  logical commits with real messages. Do not make one giant "cleanup" commit.
- Recommend which branches are dead and can be deleted locally, and which must be kept.
  List them for my confirmation; do not delete any yet.
- Tell me plainly whether an examiner cloning the default branch would get the correct,
  complete work. If not, that is the top priority to fix.

## 2. Secrets and safety

- `.env` exists at root and is correctly gitignored. Verify it was never committed at any
  point in history (check all branches, not just HEAD).
- If it was ever committed, tell me immediately, tell me which keys are exposed, and tell me
  what to rotate. Do not attempt to scrub history yourself — just report.
- Scan tracked files for hardcoded API keys, tokens, absolute paths containing my username,
  and personal data that should not ship.

## 3. .gitignore contradictions

`.gitignore` lists `releases/` and `*.pkl`, but `git status` shows tracked modified files
under `releases/` and tracked `.pkl` index files. Files tracked before being ignored stay
tracked, which makes the ignore rules misleading.

For each contradiction, tell me which it should be — genuinely part of the deliverable, or
genuinely a build artefact — then make the tracking consistent with that answer. Frozen,
hash-manifested release bundles are probably meant to be tracked; ignore rules should then
be corrected rather than the files untracked.

## 4. Reproducibility for someone who is not me

- `node_modules` is a symlink to a path outside the repo, under my personal cache directory.
  It will break for anyone else. Fix it.
- Verify `requirements.txt` and `pyproject.toml` actually cover what the code imports.
- Confirm `make` targets in `Makefile` still work, or tell me which are broken.
- Check the paths referenced in `START_HERE.md` and `README.md` all resolve. I moved files
  into `archive/` recently, so some may be stale.

## 5. Size and dead weight

Repo is roughly 500MB: `.git` 142MB, `runs/` 184MB, `releases/` 76MB, `data/` 45MB,
`indexes/` 35MB, `tmp/` 22MB.

- Three tracked run files are 15-16MB each under
  `runs/phase8_exploratory_five_system/*/retrieval/*.jsonl`. Advise whether these need to be
  in git and what the alternative is. Report only — do not rewrite history.
- `tmp/` is 22MB and gitignored. Confirm nothing in it is referenced by any script, then
  propose removing it.
- There is a stray `defence/lu47m8rj.tmp`. Find any other stray temp artefacts.
- Find duplicated large artefacts between `data/`, `indexes/` and `releases/`.

## 6. Coherence

- Look for any remaining docs that contradict the current state of the work. I already fixed
  `docs/CURRENT_RESEARCH_STATUS.md`, which wrongly said Phase 6 was incomplete. Check the
  other 30+ files in `docs/` for the same problem and list anything stale.
- `README.md` is 26KB. Check it agrees with `START_HERE.md` and does not duplicate or
  contradict it.
- Confirm `runs/CANONICAL_EVIDENCE.json` still matches reality.

## 7. Tests

`tests/` has 82 files. Run them. Tell me the pass rate and whether failures are real
regressions or stale fixtures from files I moved. Do not fix failing tests yet — report first.

## Definition of done

1. An examiner cloning the default branch gets the correct, complete work.
2. `python scripts/verify_headline_numbers.py` exits 0.
3. No secrets in tracked files or in history.
4. Working tree clean, with a sensible commit history.
5. Every path in `START_HERE.md` resolves.
6. A short `CLEANUP_REPORT.md` listing what changed, what I still need to decide, and
   anything you found but deliberately did not touch.

Start with section 1 and report before making changes.
```

---

## Notes on why each section is here

**Section 1 is the real risk.** You are on `codex/phase9-evidence-final` with 58 uncommitted
changes. If your examiner clones this repo and lands on `main`, there is a live question of
whether they see the submitted work at all. Everything else is cosmetic next to that.

**Section 3** exists because `.gitignore` currently says one thing and git tracking says
another. `releases/` is ignored but tracked. That is the kind of inconsistency that reads as
carelessness to someone assessing rigour — especially in a dissertation whose central claim is
about reproducibility and frozen artefacts.

**Section 5 reports rather than acts.** Removing large files from git history rewrites every
commit hash. Do not let that happen a week before a defence.

**The exclusions matter.** `runs/canonical_v2_pilot/` and `audits/` are protected in the
prompt because they are evidence, not clutter — the preserved failure records in `audits/`
are what back your claim that failed runs were never silently replaced.
