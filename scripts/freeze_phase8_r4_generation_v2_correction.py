#!/usr/bin/env python3
"""Offline-revalidate V2 response and freeze corrected continuation; no API calls."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase8_r4_v2_validation import validate_provider_response  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
V2 = BASE / "generation_r4_v2_freeze"
FAILED = BASE / "generation_r4_v2_trace"
OUT = BASE / "generation_r4_v2_correction_freeze"
BLIND = "P8R4G0fb0ef5d959c"
REMAINING_CAP = 1.217869


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
        raise SystemExit("correction freeze exists; refusing overwrite")
    if subprocess.run(["git", "merge-base", "--is-ancestor", "4680b7c", "HEAD"], cwd=ROOT).returncode:
        raise SystemExit("approved correction base missing")
    plans = {r["blinded_request_id"]: r for r in load(V2 / "recovery_request_plan.jsonl")}
    raw_path = FAILED / "raw" / f"{BLIND}.json"
    raw = obj(raw_path)
    validated = validate_provider_response(raw, available_evidence_ids=list(plans[BLIND]["evidence_id_to_chunk_id"]))
    OUT.mkdir(parents=True)
    revalidated_path = OUT / "offline_revalidated" / f"{BLIND}.json"
    dump(revalidated_path, {"blinded_request_id": BLIND, "validation_contract": "phase8_r4_v2_1024", **validated})
    remaining = [r for r in plans.values() if r["blinded_request_id"] != BLIND]
    original_trace = obj(V2 / "execution_config.json")["v2_trace_request_ids"]
    trace_remaining = [x for x in original_trace if x != BLIND]
    if len(remaining) != 89 or len(trace_remaining) != 4:
        raise SystemExit("corrected continuation counts differ")
    input_envelope = sum(r["planned_input_token_envelope"] for r in remaining)
    worst = input_envelope / 1e6 + len(remaining) * 1024 * 5 / 1e6
    reserve = max(r["planned_input_token_envelope"] for r in remaining) / 1e6 + 1024 * 5 / 1e6
    hard = round(worst + reserve, 6)
    if hard > REMAINING_CAP:
        raise SystemExit("corrected continuation exceeds remaining cap")
    config = {
        "schema_version": 3, "status": "frozen_pending_execution_approval", "approved_correction_base_commit": "4680b7c",
        "offline_revalidated_v2_n": 1, "prior_v1_reused_n": 10, "remaining_dispatch_n": 89,
        "remaining_trace_request_ids": trace_remaining, "remaining_full_after_trace_n": 85,
        "model": "claude-haiku-4-5-20251001", "temperature": 0, "max_output_tokens": 1024,
        "change_from_v2": "validator output-token ceiling only: 512 to 1024", "zero_retries": True, "fallback": None, "replacement": None,
        "input_token_envelope": input_envelope, "continuation_worst_case_usd": round(worst, 6),
        "ambiguous_dispatch_reserve_usd": round(reserve, 6), "continuation_hard_cap_usd": hard,
        "remaining_cumulative_cap_usd": REMAINING_CAP, "prior_cumulative_r4_cost_usd": 2.482131,
        "absolute_r4_cap_usd": 3.70, "human_validation_complete": False,
        "output_paths": {"trace": "runs/phase8_r4_improvements/generation_r4_v2_corrected_trace", "full": "runs/phase8_r4_improvements/generation_r4_v2_corrected_full"},
    }
    dump(OUT / "execution_config.json", config)
    dump(OUT / "reuse_record.json", {"blinded_request_id": BLIND, "request_sha256": plans[BLIND]["request_sha256"], "raw_path": str(raw_path.relative_to(ROOT)), "raw_sha256": sha(raw_path), "validated_path": str(revalidated_path.relative_to(ROOT)), "validated_sha256": sha(revalidated_path), "usage": validated["usage"]})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in [V2 / "execution_config.json", V2 / "recovery_request_plan.jsonl", V2 / "recovery_request_payloads.jsonl", raw_path, FAILED / "ledger.json", ROOT / "audits/phase8_r4/generation_v2_validator_failure_checkpoint.json"]}
    artifacts = {str(p.relative_to(ROOT)): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "freeze_manifest.json"}
    dump(OUT / "freeze_manifest.json", {"inputs": inputs, "artifacts": artifacts})
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
