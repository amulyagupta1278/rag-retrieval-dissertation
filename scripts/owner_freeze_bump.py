#!/usr/bin/env python3
"""Owner tool: record an authorized lifecycle change without erasing freeze evidence.

Problem this solves
-------------------
Several test files are content-hash-pinned by freeze manifests. When the project
lifecycle legitimately advances (owner approves a run; the run executes and writes
output), the test's assertion becomes obsolete. Editing the test then breaks its
pinned hash.

The wrong fix is to overwrite the hash in the historical manifest. That destroys the
evidence of what was frozen and when.

The right fix, and what this script does:
  1. Leave the historical manifest byte-identical.
  2. Write a NEW corrective manifest alongside it, carrying the new hash.
  3. Record the supersession link, the reason, and the evidence in both directions.

Usage
-----
  # 1. Edit the test assertion by hand first, then:
  python scripts/owner_freeze_bump.py \
      --test tests/test_phase5d_v3_transport_recovery.py \
      --historical-manifest audits/phase5d_v3_recovery/freeze_manifest.json \
      --reason "Owner approved live V3 execution; run completed 26/26 within cap." \
      --evidence audits/phase5d_v3_recovery/live_execution_approval.json \
      --evidence runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/control/ledger.json

  # dry run (default is to show, then ask):
  python scripts/owner_freeze_bump.py ... --dry-run

Nothing is written until you confirm. Historical manifests are opened read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip()


def find_pinned_hash(manifest: dict, rel: str) -> tuple[str, list[str]] | tuple[None, None]:
    """Locate rel's pinned digest anywhere in the manifest; return (digest, keypath)."""
    stack: list[tuple[object, list[str]]] = [(manifest, [])]
    while stack:
        node, path = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if k == rel and isinstance(v, str) and len(v) == 64:
                    return v, path + [k]
                stack.append((v, path + [str(k)]))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                stack.append((v, path + [str(i)]))
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", required=True, help="path to the edited, hash-pinned file")
    ap.add_argument("--historical-manifest", required=True, help="manifest that pins it (NOT modified)")
    ap.add_argument("--reason", required=True, help="why the old assertion became obsolete")
    ap.add_argument("--evidence", action="append", default=[], help="repeatable: file proving the change was authorized")
    ap.add_argument("--out", help="corrective manifest path (default: <historical>.corrective.json)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    test_rel = a.test
    test_path = ROOT / test_rel
    hist_path = ROOT / a.historical_manifest

    for p, what in ((test_path, "test file"), (hist_path, "historical manifest")):
        if not p.exists():
            print(f"ERROR: {what} not found: {p}", file=sys.stderr)
            return 2

    historical = json.loads(hist_path.read_text())
    old_hash, keypath = find_pinned_hash(historical, test_rel)
    if old_hash is None:
        print(f"ERROR: {test_rel} is not pinned anywhere in {a.historical_manifest}", file=sys.stderr)
        return 2

    new_hash = sha256_file(test_path)
    if new_hash == old_hash:
        print("Nothing to do: file already matches the historical manifest.")
        return 0

    out_path = Path(a.out) if a.out else hist_path.with_suffix(".corrective.json")
    out_rel = str(out_path.relative_to(ROOT)) if out_path.is_absolute() else str(out_path)

    evidence = {}
    for e in a.evidence:
        ep = ROOT / e
        if not ep.exists():
            print(f"ERROR: evidence file not found: {e}", file=sys.stderr)
            return 2
        evidence[e] = sha256_file(ep)

    corrective = {
        "schema_version": 1,
        "record_type": "corrective_freeze_manifest",
        "supersedes": a.historical_manifest,
        "supersedes_sha256": sha256_file(hist_path),
        "historical_manifest_modified": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit_at_creation": git("rev-parse", "HEAD"),
        "pinned_file": test_rel,
        "manifest_keypath": keypath,
        "historical_sha256": old_hash,
        "corrected_sha256": new_hash,
        "reason_old_assertion_obsolete": a.reason,
        "authorizing_evidence": evidence,
        "note": (
            "The historical manifest is preserved byte-identical and remains the record "
            "of what was frozen at that time. This corrective manifest records the "
            "authorized post-freeze lifecycle change. Readers must consult both."
        ),
    }

    print("=" * 72)
    print(f"pinned file      : {test_rel}")
    print(f"historical hash  : {old_hash}")
    print(f"corrected hash   : {new_hash}")
    print(f"historical mfst  : {a.historical_manifest}  (WILL NOT BE MODIFIED)")
    print(f"corrective mfst  : {out_rel}  (new file)")
    print(f"reason           : {a.reason}")
    print(f"evidence         : {len(evidence)} file(s)")
    for k in evidence:
        print(f"                   - {k}")
    print("=" * 72)

    if a.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    if input("\nWrite corrective manifest? [y/N] ").strip().lower() not in {"y", "yes"}:
        print("Aborted. Nothing written.")
        return 1

    before = sha256_file(hist_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(corrective, indent=2, sort_keys=True) + "\n")
    after = sha256_file(hist_path)

    if before != after:
        print("FATAL: historical manifest changed. This must never happen.", file=sys.stderr)
        return 3

    print(f"\nWrote {out_rel}")
    print(f"Historical manifest verified unchanged ({before[:16]}...).")
    print("\nNext: re-run the affected test, then commit both the edited file and the")
    print("corrective manifest together with a message explaining the lifecycle change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
