#!/usr/bin/env python3
"""Run approved R4 generation V2 trace and conditional remaining 85 calls."""

from __future__ import annotations

import copy
import hashlib
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase7_v2_freeze import SDK_VERSION, observed_cost_usd, validate_provider_response  # noqa: E402
from src.utils.atomic_io import write_json  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
FREEZE = BASE / "generation_r4_v2_freeze"
TRACE = BASE / "generation_r4_v2_trace"
FULL = BASE / "generation_r4_v2_full"
APPROVAL = ROOT / "audits/phase8_r4/generation_v2_execution_approval.json"
MAX_OUTPUT = 1024


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def obj(path: Path) -> dict:
    return json.loads(path.read_text())


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def preflight() -> dict:
    config, manifest, approval = obj(FREEZE / "execution_config.json"), obj(FREEZE / "freeze_manifest.json"), obj(APPROVAL)
    if config["status"] != "frozen_pending_execution_approval" or approval["status"] != "owner_approved":
        raise RuntimeError("V2 approval state differs")
    if approval["execution_config_sha256"] != sha(FREEZE / "execution_config.json") or approval["freeze_manifest_sha256"] != sha(FREEZE / "freeze_manifest.json"):
        raise RuntimeError("V2 approved hashes differ")
    if config["v2_hard_cap_usd"] != .988461 or config["prior_cumulative_r4_cost_usd"] + config["v2_hard_cap_usd"] > 3.70:
        raise RuntimeError("V2 cost contract differs")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", approval["approved_commit"], "HEAD"], cwd=ROOT)
    if result.returncode:
        raise RuntimeError("approved V2 commit missing")
    for section in ("inputs", "artifacts"):
        for rel, expected in manifest[section].items():
            if sha(ROOT / rel) != expected:
                raise RuntimeError(f"V2 frozen hash differs: {rel}")
    plans = {r["blinded_request_id"]: r for r in rows(FREEZE / "recovery_request_plan.jsonl")}
    payloads = {r["blinded_request_id"]: r for r in rows(FREEZE / "recovery_request_payloads.jsonl")}
    reused = rows(FREEZE / "reused_v1_records.jsonl")
    if len(plans) != 90 or set(plans) != set(payloads) or len(reused) != 10:
        raise RuntimeError("V2 coverage differs")
    for blind, payload in payloads.items():
        if digest(payload["request"]) != plans[blind]["request_sha256"] or payload["request"]["max_tokens"] != MAX_OUTPUT:
            raise RuntimeError(f"V2 request differs: {blind}")
    for row in reused:
        if sha(ROOT / row["validated_path"]) != row["validated_sha256"]:
            raise RuntimeError(f"V1 reusable record differs: {row['blinded_request_id']}")
    if any(path.exists() and any(path.rglob("*")) for path in (TRACE, FULL)):
        raise RuntimeError("V2 outputs exist; refusing rerun")
    return {"config": config, "plans": plans, "payloads": payloads, "reused": reused}


def projection(ledger: dict, ids: list[str], plans: dict, reserve: float) -> float:
    return observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]) + reserve + sum(plans[x]["planned_input_token_envelope"] for x in ids) / 1e6 + len(ids) * MAX_OUTPUT * 5 / 1e6


def make_sender():
    env = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    if not env.get("ANTHROPIC_API_KEY") or anthropic.__version__ != SDK_VERSION:
        raise RuntimeError("credential or Anthropic SDK differs")
    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"], max_retries=0, timeout=120.0)
    return lambda request: client.messages.create(**copy.deepcopy(request))


def run_batch(send, frozen: dict, ids: list[str], out: Path, ledger: dict) -> bool:
    config, plans, payloads = frozen["config"], frozen["plans"], frozen["payloads"]
    write_json(out / "ledger.json", ledger, overwrite=False)
    for blind in ids:
        remaining = [x for x in ids if x not in ledger["completed_blinded_request_ids"]]
        if projection(ledger, remaining, plans, config["ambiguous_dispatch_reserve_usd"]) > config["v2_hard_cap_usd"]:
            ledger.update(status="failed_projected_cost_cap", failed_blinded_request_id=blind); write_json(out / "ledger.json", ledger, overwrite=True); return False
        ledger.update(status="attempt_counted_before_dispatch", attempt_n=ledger["attempt_n"] + 1); write_json(out / "ledger.json", ledger, overwrite=True)
        started = time.perf_counter()
        try:
            response = send(payloads[blind]["request"])
            raw = response.model_dump(mode="json", by_alias=True, exclude_none=True)
        except Exception as exc:
            ledger.update(status="failed_ambiguous_dispatch", failure={"type": type(exc).__name__}); write_json(out / "ledger.json", ledger, overwrite=True); return False
        write_json(out / "raw" / f"{blind}.json", raw, overwrite=False)
        try:
            valid = validate_provider_response(raw, available_evidence_ids=list(plans[blind]["evidence_id_to_chunk_id"]))
        except Exception as exc:
            ledger.update(status="failed_terminal_validation", failure={"type": type(exc).__name__, "message": str(exc), "blinded_request_id": blind}); write_json(out / "ledger.json", ledger, overwrite=True); return False
        write_json(out / "validated" / f"{blind}.json", {"blinded_request_id": blind, **valid}, overwrite=False)
        ledger["completed_blinded_request_ids"].append(blind)
        ledger["input_tokens"] += valid["usage"]["input_tokens"]; ledger["output_tokens"] += valid["usage"]["output_tokens"]
        ledger["observed_cost_usd"] = round(observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6)
        ledger["latencies_seconds"].append(round(time.perf_counter() - started, 6)); ledger["status"] = "running"
        write_json(out / "ledger.json", ledger, overwrite=True)
    ledger["status"] = "complete"; write_json(out / "ledger.json", ledger, overwrite=True); return True


def main() -> int:
    frozen, send = preflight(), make_sender()
    trace_ids = frozen["config"]["v2_trace_request_ids"]
    ledger = {"status": "ready", "attempt_n": 0, "completed_blinded_request_ids": [], "input_tokens": 0, "output_tokens": 0, "observed_cost_usd": 0.0, "retry_n": 0, "latencies_seconds": []}
    if not run_batch(send, frozen, trace_ids, TRACE, ledger): return 76
    write_json(TRACE / "summary.json", {"status": "trace_complete", "valid_n": 5, "failure_n": 0, "retry_n": 0, "cost_usd": ledger["observed_cost_usd"]}, overwrite=False)
    remaining = [x for x in sorted(frozen["plans"]) if x not in set(trace_ids)]
    if projection(ledger, remaining, frozen["plans"], frozen["config"]["ambiguous_dispatch_reserve_usd"]) > frozen["config"]["v2_hard_cap_usd"]: return 77
    full_ledger = {**ledger, "status": "ready", "reused_trace_request_ids": trace_ids}
    if not run_batch(send, frozen, remaining, FULL, full_ledger): return 78
    combined = [{**r, "source": "v1_reused"} for r in frozen["reused"]]
    for blind in sorted(frozen["plans"]):
        source = TRACE if blind in trace_ids else FULL
        path = source / "validated" / f"{blind}.json"
        combined.append({"blinded_request_id": blind, "source": "v2_trace" if source == TRACE else "v2_full", "validated_path": str(path.relative_to(ROOT)), "validated_sha256": sha(path), "request_sha256": frozen["plans"][blind]["request_sha256"]})
    combined.sort(key=lambda r: r["blinded_request_id"])
    (FULL / "combined_100_record_index.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in combined))
    summary = {"status": "complete", "coverage": "100/100", "v1_reused": 10, "v2_trace_valid": 5, "v2_full_valid": 85, "retry_n": 0, "failure_n": 0, "input_tokens": full_ledger["input_tokens"], "output_tokens": full_ledger["output_tokens"], "v2_cost_usd": full_ledger["observed_cost_usd"], "cumulative_r4_cost_usd": round(2.476095 + full_ledger["observed_cost_usd"], 6), "mean_latency_seconds": statistics.fmean(full_ledger["latencies_seconds"]), "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(FULL / "summary.json", summary, overwrite=False); print(json.dumps(summary, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
