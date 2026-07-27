# Owner Runbook — the remaining 9 failures

**State:** 358 passed, **9 failed**, 0 skipped, 369 collected.
(20 → 9. Thirteen were mine; I fixed all of them.)

Baseline check before you start:

```bash
cd ~/Desktop/rag-retrieval-dissertation
python3 -m pytest tests/ -q | tail -3        # expect: 9 failed, 358 passed
```

| # | Failure | Class | Who | Effort |
|---|---|---|---|---|
| 1 | phase5a::…phase4_checkpoint_are_unchanged | B | you — investigate | 30–60 min |
| 2–7 | six 5D lifecycle assertions | A | you — mechanical | ~20 min total |
| 8–9 | two phase6 package assertions | C | **leave red** | 0 min |

Do **A first** (quick, mechanical), then **C** (nothing to do), then **B** (real judgement).

---

# Class A — six lifecycle assertions (~20 min)

## Why these fail

Each froze a *pre-approval, pre-execution* state. You have since approved, and the runs
executed. I verified the evidence:

```
audits/phase5d_v2/trace_execution_approval.json        status: owner_approved
audits/phase5d_v2_full/full_execution_approval.json    status: owner_approved
audits/phase5d_v3_recovery/live_execution_approval.json status: owner_approved

runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/control/ledger.json
   attempted_generation_request_n      : 26
   actual_input_tokens                 : 771,820
   actual_output_tokens                : 33,817
   cumulative_recorded_observed_cost   : $1.980933
   cumulative_hard_cap_usd             : $2.15      ← stayed under cap
```

**Confirm this is what you intended before proceeding.** If any of those approvals is not
yours, stop — that is a much more serious finding than a failing test.

## The catch

All three files are **content-hash-pinned**. Editing them breaks the pin — that is exactly
the mistake I made. So each edit must be paired with a **corrective manifest**, never an
edit to the historical one. `scripts/owner_freeze_bump.py` does that for you.

## A1. Make the six edits

Six single-line changes. In each case the assertion should now check the *current* state
while recording what it used to assert.

**`tests/test_phase5d_v2_full_amendment.py`**

line 84:
```python
    assert approval["status"] == "pending_owner_approval"
```
→
```python
    # Lifecycle advanced: owner approved the remaining 26-primary full run.
    # Was "pending_owner_approval" at freeze (commit 7d542ec).
    # Evidence: audits/phase5d_v2_full/full_execution_approval.json
    assert approval["status"] == "owner_approved"
```

line 121:
```python
    assert not runner.FULL_ROOT.exists()
```
→
```python
    # Output now exists: the approved full run executed.
    # Assertion inverted from "not exists" at freeze (commit 7d542ec).
    assert runner.FULL_ROOT.exists()
```

**`tests/test_phase5d_v2_prompt_rag_claude.py`**

line 171: same change as above (`pending_owner_approval` → `owner_approved`),
evidence `audits/phase5d_v2/trace_execution_approval.json`, freeze commit `73b9a40`.

line 259: `assert not runner.OUTPUT_ROOT.exists()` → `assert runner.OUTPUT_ROOT.exists()`

**`tests/test_phase5d_v3_transport_recovery.py`**

line 77: `pending_owner_live_approval` → `owner_approved`,
evidence `audits/phase5d_v3_recovery/live_execution_approval.json`, freeze commit `fa05de1`.

line 112: `assert not runner.OUTPUT_ROOT.exists()` → `assert runner.OUTPUT_ROOT.exists()`

### Also check the `pytest.raises` lines

Each approval test has a second assertion two lines below:

```python
with pytest.raises(ClaudeContractError, match="lacks owner approval"):
    runner._validate_approval()
```

Now that approval is granted, `_validate_approval()` should **succeed**. Change to:

```python
# Approval now granted, so validation passes instead of raising.
runner._validate_approval()
```

Run after editing to see which of these still bite:

```bash
python3 -m pytest tests/test_phase5d_v2_full_amendment.py \
                  tests/test_phase5d_v2_prompt_rag_claude.py \
                  tests/test_phase5d_v3_transport_recovery.py -q
```

## A2. Record each bump

Once a file's tests pass, record the authorized hash change. Once per file:

```bash
python3 scripts/owner_freeze_bump.py \
  --test tests/test_phase5d_v3_transport_recovery.py \
  --historical-manifest audits/phase5d_v3_recovery/freeze_manifest.json \
  --reason "Owner approved live V3 execution; run completed 26/26 within the \$2.15 cap. Pre-execution assertions superseded." \
  --evidence audits/phase5d_v3_recovery/live_execution_approval.json \
  --evidence runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/control/ledger.json
```

```bash
python3 scripts/owner_freeze_bump.py \
  --test tests/test_phase5d_v2_full_amendment.py \
  --historical-manifest audits/phase5d_v2_full/freeze_manifest.json \
  --reason "Owner approved the remaining 26-primary full run; output exists. Pre-execution assertions superseded." \
  --evidence audits/phase5d_v2_full/full_execution_approval.json
```

```bash
python3 scripts/owner_freeze_bump.py \
  --test tests/test_phase5d_v2_prompt_rag_claude.py \
  --historical-manifest audits/phase5d_v2/freeze_manifest.json \
  --reason "Owner approved the 24-call trace run; output exists. Pre-execution assertions superseded." \
  --evidence audits/phase5d_v2/trace_execution_approval.json
```

Add `--dry-run` first if you want to preview. The script:

- refuses if the file isn't actually pinned in that manifest;
- writes only a **new** `*.corrective.json`;
- re-hashes the historical manifest afterwards and hard-fails if it changed.

`test_phase5d_v3_recovery_checkpoint.py` is pinned by a manifest under `runs/…` rather than
`audits/…`; if it starts failing, point `--historical-manifest` at
`runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/artifact_manifest.json`.

## A3. Commit

```bash
git add tests/test_phase5d_*.py audits/**/*.corrective.json
git commit -m "test(phase5d): advance lifecycle assertions to approved+executed state

Owner approved trace, full, and V3 recovery runs; all three executed.
Tests asserted the pre-approval/pre-execution state and are superseded.

Historical freeze manifests preserved byte-identical; authorized hash
changes recorded in corrective manifests alongside them."
```

---

# Class C — two Phase 6 tests: **leave failing**

```
test_phase6_blind_judging_package.py::test_package_has_755_unique_blank_rows_and_safe_columns
test_phase6_blind_judging_package.py::test_freeze_manifest_hashes_every_artifact
```

These assert the package holds **blank** grades. It currently holds the invalidated
AI-generated grades. **The failures are correct** — they are the tripwire telling you
Phase 6 has no valid freeze.

In the earlier session I "fixed" these by rewriting them to assert the seed-123 AI state.
That is precisely how a green suite got manufactured over invalid data. Don't repeat it.

They go green on their own once a valid human-graded Phase 6 freeze exists. Until then,
9 failures is the honest number. If you need a green gate for CI, gate on:

```bash
python3 -m pytest tests/ -q --deselect tests/test_phase6_blind_judging_package.py::test_package_has_755_unique_blank_rows_and_safe_columns \
                            --deselect tests/test_phase6_blind_judging_package.py::test_freeze_manifest_hashes_every_artifact
```

…and record *in the CI config* that the deselection is Phase-6-invalidation-scoped and
must be removed at re-freeze. A deselect with a documented protocol reason is allowed;
a silent one is not.

---

# Class B — the Phase 4 tripwire (the real work)

```
test_phase5a_prompt_rag.py::test_hypotheses_and_protected_phase4_checkpoint_are_unchanged
```

**This one was already failing before I touched the repo** — verified: expected
`727c2fe…`, actual at commit `7ee7e2e` was `dc94134e…`.

## What it does

Lists all 532 files tracked at Phase 4 HEAD (`70de0fd`), hashes each at its *current*
content, and combines. It is a blunt "nothing from Phase 4 has changed" alarm.

## The 26 files that differ

```bash
python3 - <<'EOF'
import subprocess, hashlib
from pathlib import Path
PH4='70de0fd17f825ca04527c7ff50f91a2e5959a084'
raw=subprocess.check_output(['git','ls-tree','-r','--name-only','-z',PH4])
for rel in sorted(p.decode() for p in raw.split(b'\0') if p):
    blob=subprocess.run(['git','show',f'{PH4}:{rel}'],capture_output=True).stdout
    f=Path(rel)
    cur=hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else None
    if cur!=hashlib.sha256(blob).hexdigest():
        log=subprocess.run(['git','log','--format=%h %ad %s','--date=short','-3','--',rel],
                           capture_output=True,text=True).stdout.strip().splitlines()
        print(f"\n{'MISSING' if cur is None else 'MODIFIED'}  {rel}")
        for l in log: print("      ", l[:88])
EOF
```

Grouped:

- **artifacts** — `runs/v2/phase4_hybrid/evaluation_manifest.json`,
  `runs/v2/phase4_hybrid/evaluation_hashes.json`,
  `runs/v2/phase4_hybrid/latency/live_summary.json`,
  `runs/v2/phase4_hybrid/statistics/paired_bootstrap_hybrid_vs_constituents.json`,
  `runs/v2/phase2a_v2/statistics/h1_exact_terminology.json`,
  `audits/phase2a/hashes.jsonl`, `audits/phase4_hybrid/latency_disclosure_correction.json`
- **scripts** — 7 files including `evaluate_phase4_hybrid.py`, `run_phase2a_r5_windowed.py`
- **tests** — 7 files
- **config** — `.gitignore`, `pyproject.toml`, `requirements.txt`
- **source** — `src/retrievers/__init__.py` *(mine — the lazy FAISS import; see below)*

## What to do

For each, decide **authorized or not**. The `latency_disclosure_correction` filename
suggests the Phase 4 hybrid changes came from a documented correction — likely
authorized. The test comment already says the constant was bumped once before "for
authorized repairs plus Phase 5D Gemini dependency archival," so there is precedent.

Then either:

- **All 26 authorized** → recompute the constant, and in the same commit add a comment
  listing what the new value covers. Recompute with:

  ```bash
  python3 -c "
  import subprocess,hashlib
  from pathlib import Path
  PH4='70de0fd17f825ca04527c7ff50f91a2e5959a084'
  raw=subprocess.check_output(['git','ls-tree','-r','--name-only','-z',PH4])
  paths=sorted(p.decode() for p in raw.split(b'\0') if p)
  m=hashlib.sha256()
  for rel in paths:
      m.update(rel.encode()); m.update(b'\0')
      m.update(hashlib.sha256(Path(rel).read_bytes()).hexdigest().encode()); m.update(b'\n')
  print(len(paths), m.hexdigest())"
  ```

- **Any NOT authorized** → restore that file from `70de0fd` and do **not** bump.

> Do not bump the constant just to go green. That deletes a tripwire covering 532 files.
> If you bump it while an unauthorized change is in the set, the alarm is silenced
> permanently and nothing will ever catch it.

## One decision I need from you

`src/retrievers/__init__.py` is in the 26 because I made the FAISS import lazy (PEP 562).

- **Keep it** — 168 pure-logic tests run without a ~430 MB torch chain. I confirmed the
  suite does **not** even collect without it in this environment, so reverting is not
  currently viable here.
- **Revert it** — requires `sentence-transformers` + `faiss-cpu` + `torch` installed.

Public API is unchanged and the file is not among the 28 hash-pinned files.
My recommendation: keep, and list it explicitly in the Phase 4 bump note.

---

# Finish

```bash
python3 -m pytest tests/ -q | tail -3
```

Expected once A and B are done: **367 passed, 2 failed** — the two Class C tripwires,
red on purpose until Phase 6 is re-frozen from human grades.

Environment note: `anthropic==0.116.0` is pinned in `requirements.txt` and a version-guard
test enforces it. I had installed `0.120.0`, which broke that test; it is pinned back now.
If you see `anthropic version mismatch`, run `pip install "anthropic==0.116.0"`.
