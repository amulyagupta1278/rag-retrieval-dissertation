#!/usr/bin/env python3
"""Freeze cost-safe R4 generation V2 recovery; no API calls."""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/phase8_r4_improvements"
V1 = BASE / "generation_r4_freeze"
TRACE_V1 = BASE / "generation_r4_trace"
FULL_V1 = BASE / "generation_r4_full"
OUT = BASE / "generation_r4_v2_freeze"
FAILED_ID = "P8R4G0fb0ef5d959c"
MAX_OUTPUT = 1024
REMAINING_CAP = 1.223905


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def obj(path: Path) -> dict:
    return json.loads(path.read_text())


def stable(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value: object) -> str:
    return hashlib.sha256(stable(value).encode()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable(value) + "\n")


def main() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("V2 generation freeze exists; refusing overwrite")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", "20a51d0", "HEAD"], cwd=ROOT)
    if result.returncode:
        raise SystemExit("approved recovery base missing")
    plans = {r["blinded_request_id"]: r for r in load(V1 / "request_plan.jsonl")}
    payloads = {r["blinded_request_id"]: r for r in load(V1 / "request_payloads.jsonl")}
    trace_ledger, full_ledger = obj(TRACE_V1 / "ledger.json"), obj(FULL_V1 / "ledger.json")
    completed = set(trace_ledger["completed_blinded_request_ids"]) | set(full_ledger["completed_blinded_request_ids"])
    if len(completed) != 10 or FAILED_ID in completed or full_ledger["failure"]["blinded_request_id"] != FAILED_ID:
        raise SystemExit("V1 completion/failure state differs")
    reusable, recovery_plans, recovery_payloads = [], [], []
    for blind in sorted(plans):
        plan, payload = plans[blind], payloads[blind]
        if blind in completed:
            source = TRACE_V1 if blind in set(trace_ledger["completed_blinded_request_ids"]) else FULL_V1
            valid_path = source / "validated" / f"{blind}.json"
            if digest(payload["request"]) != plan["request_sha256"] or not valid_path.is_file():
                raise SystemExit(f"V1 reuse hash/evidence differs: {blind}")
            reusable.append({"blinded_request_id": blind, "request_sha256": plan["request_sha256"], "validated_path": str(valid_path.relative_to(ROOT)), "validated_sha256": sha(valid_path), "reuse_policy": "byte-identical V1 request hash and frozen valid record"})
            continue
        request = json.loads(json.dumps(payload["request"]))
        request["max_tokens"] = MAX_OUTPUT
        request_hash = digest(request)
        recovery_plans.append({**plan, "v1_request_sha256": plan["request_sha256"], "request_sha256": request_hash, "max_output_tokens": MAX_OUTPUT, "status": "v2_dispatch_required"})
        recovery_payloads.append({"blinded_request_id": blind, "request_sha256": request_hash, "request": request})
    if len(reusable) != 10 or len(recovery_plans) != 90:
        raise SystemExit("V2 reuse/recovery counts differ")
    by_id = {r["blinded_request_id"]: r for r in recovery_plans}
    failed = by_id[FAILED_ID]
    systems = sorted({r["system_id"] for r in recovery_plans})
    categories = sorted({r["category"] for r in recovery_plans})
    remaining_systems = [s for s in systems if s != failed["system_id"]]
    remaining_categories = [c for c in categories if c != failed["category"]]
    trace = None
    for assignment in itertools.permutations(remaining_categories):
        chosen = [failed]
        for system, category in zip(remaining_systems, assignment):
            options = [r for r in recovery_plans if r["system_id"] == system and r["category"] == category]
            if not options:
                break
            chosen.append(max(options, key=lambda r: (r["planned_input_token_envelope"], r["blinded_request_id"])))
        if len(chosen) == 5:
            trace = chosen; break
    if trace is None:
        raise SystemExit("cannot construct five-system/five-category V2 trace")
    input_envelope = sum(r["planned_input_token_envelope"] for r in recovery_plans)
    worst = input_envelope / 1e6 + len(recovery_plans) * MAX_OUTPUT * 5 / 1e6
    reserve = max(r["planned_input_token_envelope"] for r in recovery_plans) / 1e6 + MAX_OUTPUT * 5 / 1e6
    hard = round(worst + reserve, 6)
    if hard > REMAINING_CAP:
        raise SystemExit(f"V2 exposure {hard} exceeds remaining cap {REMAINING_CAP}")
    OUT.mkdir(parents=True)
    (OUT / "recovery_request_plan.jsonl").write_text("".join(stable(r) + "\n" for r in sorted(recovery_plans, key=lambda x: x["blinded_request_id"])))
    (OUT / "recovery_request_payloads.jsonl").write_text("".join(stable(r) + "\n" for r in sorted(recovery_payloads, key=lambda x: x["blinded_request_id"])))
    (OUT / "reused_v1_records.jsonl").write_text("".join(stable(r) + "\n" for r in reusable))
    config = {
        "schema_version": 2, "status": "frozen_pending_execution_approval", "approved_design_base_commit": "20a51d0",
        "reused_v1_valid_n": 10, "v2_dispatch_n": 90, "v2_trace_request_ids": [r["blinded_request_id"] for r in trace],
        "v2_trace_includes_v1_failed_request": FAILED_ID, "model": "claude-haiku-4-5-20251001", "temperature": 0,
        "max_output_tokens": MAX_OUTPUT, "zero_retries": True, "fallback": None, "replacement": None,
        "input_token_envelope": input_envelope, "v2_worst_case_usd": round(worst, 6),
        "ambiguous_dispatch_reserve_usd": round(reserve, 6), "v2_hard_cap_usd": hard,
        "remaining_cumulative_r4_cap_usd": REMAINING_CAP, "prior_cumulative_r4_cost_usd": 2.476095,
        "absolute_total_r4_cap_usd": 3.70, "human_validation_complete": False,
        "output_paths": {"trace": "runs/phase8_r4_improvements/generation_r4_v2_trace", "full": "runs/phase8_r4_improvements/generation_r4_v2_full"},
    }
    dump(OUT / "execution_config.json", config)
    artifacts = {str(p.relative_to(ROOT)): sha(p) for p in sorted(OUT.glob("*")) if p.name != "freeze_manifest.json"}
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in [V1 / "request_plan.jsonl", V1 / "request_payloads.jsonl", TRACE_V1 / "ledger.json", FULL_V1 / "ledger.json", ROOT / "audits/phase8_r4/generation_v1_failure_checkpoint.json"]}
    dump(OUT / "freeze_manifest.json", {"artifacts": artifacts, "inputs": inputs})
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
