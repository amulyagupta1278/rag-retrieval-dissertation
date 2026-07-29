#!/usr/bin/env python3
"""Freeze 50-request semantic-contract V3 recovery; no API calls."""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase7_v2_freeze import conservative_input_token_envelope, request_sha256  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
V2 = BASE / "generation_r4_v2_freeze"
CORRECTION = BASE / "generation_r4_v2_correction_freeze"
TRACE2 = BASE / "generation_r4_v2_corrected_trace"
FULL2 = BASE / "generation_r4_v2_corrected_full"
OUT = BASE / "generation_r4_v3_freeze"
PROMPT_V1 = ROOT / "prompts/phase7_answer_generation_v1.txt"
PROMPT_V3 = ROOT / "prompts/phase8_r4_answer_generation_v3.txt"
FAILED_ID = "P8R4G8323a17b91e8"
REMAINING_CAP = 1.056900


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def obj(path: Path) -> dict:
    return json.loads(path.read_text())


def stable(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(stable(value) + "\n")


def main() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("V3 freeze exists; refusing overwrite")
    if subprocess.run(["git", "merge-base", "--is-ancestor", "e7891df", "HEAD"], cwd=ROOT).returncode:
        raise SystemExit("approved V3 design base missing")
    plans = {r["blinded_request_id"]: r for r in load(V2 / "recovery_request_plan.jsonl")}
    payloads = {r["blinded_request_id"]: r for r in load(V2 / "recovery_request_payloads.jsonl")}
    reused = load(V2 / "reused_v1_records.jsonl")
    correction_reuse = obj(CORRECTION / "reuse_record.json")
    trace_ledger, full_ledger = obj(TRACE2 / "ledger.json"), obj(FULL2 / "ledger.json")
    new_valid = set(trace_ledger["completed_blinded_request_ids"]) | set(full_ledger["completed_blinded_request_ids"])
    if len(reused) != 10 or len(new_valid) != 39 or FAILED_ID in new_valid or full_ledger["failure"]["blinded_request_id"] != FAILED_ID:
        raise SystemExit("V3 source completion state differs")
    reuse_rows = [{**r, "source": "v1_valid"} for r in reused]
    reuse_rows.append({**correction_reuse, "source": "v2_offline_revalidated"})
    trace_valid = set(trace_ledger["completed_blinded_request_ids"])
    for blind in sorted(new_valid):
        source = TRACE2 if blind in trace_valid else FULL2
        path = source / "validated" / f"{blind}.json"
        reuse_rows.append({"blinded_request_id": blind, "source": "v2_corrected_valid", "request_sha256": plans[blind]["request_sha256"], "validated_path": str(path.relative_to(ROOT)), "validated_sha256": sha(path)})
    if len(reuse_rows) != 50 or len({r["blinded_request_id"] for r in reuse_rows}) != 50:
        raise SystemExit("V3 reusable set differs")
    reusable_ids = {r["blinded_request_id"] for r in reuse_rows}
    unresolved = sorted(set(plans) - reusable_ids)
    if len(unresolved) != 50 or FAILED_ID not in unresolved:
        raise SystemExit("V3 unresolved set differs")
    prompt_v1, prompt_v3 = PROMPT_V1.read_text(), PROMPT_V3.read_text()
    recovery_plans, recovery_payloads = [], []
    for blind in unresolved:
        old = payloads[blind]["request"]
        if old.get("system") != prompt_v1:
            raise SystemExit(f"V1 prompt binding differs: {blind}")
        request = json.loads(json.dumps(old)); request["system"] = prompt_v3
        request_hash = request_sha256(request)
        recovery_plans.append({**plans[blind], "v2_request_sha256": plans[blind]["request_sha256"], "request_sha256": request_hash, "planned_input_token_envelope": conservative_input_token_envelope(request), "prompt_version": "phase8_r4_v3_semantic_contract", "status": "v3_dispatch_required"})
        recovery_payloads.append({"blinded_request_id": blind, "request_sha256": request_hash, "request": request})
    by_id = {r["blinded_request_id"]: r for r in recovery_plans}; failed = by_id[FAILED_ID]
    systems = sorted({r["system_id"] for r in recovery_plans}); categories = sorted({r["category"] for r in recovery_plans})
    remaining_systems = [s for s in systems if s != failed["system_id"]]; remaining_categories = [c for c in categories if c != failed["category"]]
    trace = None
    for assignment in itertools.permutations(remaining_categories):
        chosen = [failed]
        for system, category in zip(remaining_systems, assignment):
            options = [r for r in recovery_plans if r["system_id"] == system and r["category"] == category]
            if not options: break
            chosen.append(max(options, key=lambda r: (r["planned_input_token_envelope"], r["blinded_request_id"])))
        if len(chosen) == 5: trace = chosen; break
    if trace is None:
        raise SystemExit("V3 trace coverage impossible")
    input_envelope = sum(r["planned_input_token_envelope"] for r in recovery_plans)
    worst = input_envelope / 1e6 + 50 * 1024 * 5 / 1e6
    reserve = max(r["planned_input_token_envelope"] for r in recovery_plans) / 1e6 + 1024 * 5 / 1e6
    hard = round(worst + reserve, 6)
    if hard > REMAINING_CAP:
        raise SystemExit(f"V3 exposure {hard} exceeds remaining cap")
    OUT.mkdir(parents=True)
    (OUT / "reuse_50_records.jsonl").write_text("".join(stable(r) + "\n" for r in sorted(reuse_rows, key=lambda x: x["blinded_request_id"])))
    (OUT / "request_plan.jsonl").write_text("".join(stable(r) + "\n" for r in sorted(recovery_plans, key=lambda x: x["blinded_request_id"])))
    (OUT / "request_payloads.jsonl").write_text("".join(stable(r) + "\n" for r in sorted(recovery_payloads, key=lambda x: x["blinded_request_id"])))
    config = {
        "schema_version": 4, "status": "frozen_pending_execution_approval", "approved_design_base_commit": "e7891df",
        "reused_valid_n": 50, "v3_dispatch_n": 50, "v3_trace_request_ids": [r["blinded_request_id"] for r in trace],
        "v3_trace_includes_failed_request": FAILED_ID, "v3_full_after_trace_n": 45,
        "model": "claude-haiku-4-5-20251001", "temperature": 0, "max_output_tokens": 1024,
        "only_request_change": "system prompt adds concise-answer and one-to-one factual-claim coverage requirements",
        "zero_retries": True, "fallback": None, "replacement": None,
        "input_token_envelope": input_envelope, "v3_worst_case_usd": round(worst, 6), "ambiguous_dispatch_reserve_usd": round(reserve, 6),
        "v3_hard_cap_usd": hard, "remaining_cumulative_cap_usd": REMAINING_CAP, "prior_cumulative_r4_cost_usd": 2.643100,
        "absolute_r4_cap_usd": 3.70, "human_validation_complete": False,
        "output_paths": {"trace": "runs/phase8_r4_improvements/generation_r4_v3_trace", "full": "runs/phase8_r4_improvements/generation_r4_v3_full"},
    }
    dump(OUT / "execution_config.json", config)
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in [V2 / "recovery_request_plan.jsonl", V2 / "recovery_request_payloads.jsonl", TRACE2 / "ledger.json", FULL2 / "ledger.json", PROMPT_V1, PROMPT_V3, ROOT / "audits/phase8_r4/generation_v2_corrected_semantic_failure_checkpoint.json"]}
    artifacts = {str(p.relative_to(ROOT)): sha(p) for p in sorted(OUT.glob("*")) if p.name != "freeze_manifest.json"}
    dump(OUT / "freeze_manifest.json", {"inputs": inputs, "artifacts": artifacts})
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
