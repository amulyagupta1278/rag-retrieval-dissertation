#!/usr/bin/env python3
"""Run R4 five-request generation trace and conditional remaining panel."""

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

from src.generation.phase7_v2_freeze import (  # noqa: E402
    MAX_OUTPUT_TOKENS, MODEL, SDK_VERSION, observed_cost_usd,
    request_sha256, validate_provider_response,
)
from src.utils.atomic_io import write_json  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
FREEZE = BASE / "generation_r4_freeze"
TRACE = BASE / "generation_r4_trace"
FULL = BASE / "generation_r4_full"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def obj(path: Path) -> dict:
    return json.loads(path.read_text())


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def preflight() -> dict:
    config, manifest = obj(FREEZE / "execution_config.json"), obj(FREEZE / "freeze_manifest.json")
    approval = obj(ROOT / "audits/phase8_r4/prompt_rag_v2_owner_approval.json")
    if config["status"] != "frozen_owner_blanket_approved" or approval["status"] != "owner_approved":
        raise RuntimeError("generation approval differs")
    if config["generation_hard_cap_usd"] + config["retrieval_cost_usd"] > 3.70:
        raise RuntimeError("combined hard cap exceeds owner limit")
    if config["zero_retries"] is not True or config["fallback"] is not None or config["replacement"] is not None:
        raise RuntimeError("failure policy differs")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", config["base_commit"], "HEAD"], cwd=ROOT)
    if result.returncode:
        raise RuntimeError("generation base commit not in history")
    for section in ("inputs", "artifacts"):
        for rel, expected in manifest[section].items():
            if sha(ROOT / rel) != expected:
                raise RuntimeError(f"frozen hash differs: {rel}")
    plans = {r["blinded_request_id"]: r for r in rows(FREEZE / "request_plan.jsonl")}
    payloads = {r["blinded_request_id"]: r for r in rows(FREEZE / "request_payloads.jsonl")}
    if len(plans) != 100 or set(plans) != set(payloads):
        raise RuntimeError("generation plan coverage differs")
    for blind, plan in plans.items():
        request = payloads[blind]["request"]
        if request_sha256(request) != plan["request_sha256"] or request["model"] != MODEL or request["max_tokens"] != MAX_OUTPUT_TOKENS:
            raise RuntimeError(f"generation request differs: {blind}")
    if any(path.exists() and any(path.rglob("*")) for path in (TRACE, FULL)):
        raise RuntimeError("generation outputs exist; refusing rerun")
    return {"config": config, "plans": plans, "payloads": payloads}


def projection(ledger: dict, ids: list[str], plans: dict, reserve: float) -> float:
    return observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]) + reserve + sum(plans[x]["planned_input_token_envelope"] for x in ids) / 1e6 + len(ids) * MAX_OUTPUT_TOKENS * 5 / 1e6


def sender():
    env = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    key = env.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    if anthropic.__version__ != SDK_VERSION:
        raise RuntimeError("Anthropic SDK version differs")
    client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=120.0)
    return lambda request: client.messages.create(**copy.deepcopy(request))


def response_dict(response) -> dict:
    return response.model_dump(mode="json", by_alias=True, exclude_none=True)


def run_batch(send, frozen: dict, ids: list[str], out: Path, ledger: dict) -> bool:
    plans, payloads, config = frozen["plans"], frozen["payloads"], frozen["config"]
    reserve, cap = config["ambiguous_dispatch_reserve_usd"], config["generation_hard_cap_usd"]
    write_json(out / "ledger.json", ledger, overwrite=False)
    for blind in ids:
        remaining = [x for x in ids if x not in ledger["completed_blinded_request_ids"]]
        if projection(ledger, remaining, plans, reserve) > cap:
            ledger.update(status="failed_projected_cost_cap", failed_blinded_request_id=blind)
            write_json(out / "ledger.json", ledger, overwrite=True); return False
        ledger.update(status="attempt_counted_before_dispatch", attempt_n=ledger["attempt_n"] + 1)
        write_json(out / "ledger.json", ledger, overwrite=True)
        started = time.perf_counter()
        try:
            raw = response_dict(send(payloads[blind]["request"]))
        except Exception as exc:
            ledger.update(status="failed_ambiguous_dispatch", failure={"type": type(exc).__name__})
            write_json(out / "ledger.json", ledger, overwrite=True); return False
        latency = time.perf_counter() - started
        write_json(out / "raw" / f"{blind}.json", raw, overwrite=False)
        try:
            valid = validate_provider_response(raw, available_evidence_ids=list(plans[blind]["evidence_id_to_chunk_id"]))
        except Exception as exc:
            ledger.update(status="failed_terminal_validation", failure={"type": type(exc).__name__, "message": str(exc), "blinded_request_id": blind})
            write_json(out / "ledger.json", ledger, overwrite=True); return False
        write_json(out / "validated" / f"{blind}.json", {"blinded_request_id": blind, **valid}, overwrite=False)
        ledger["completed_blinded_request_ids"].append(blind)
        ledger["input_tokens"] += valid["usage"]["input_tokens"]
        ledger["output_tokens"] += valid["usage"]["output_tokens"]
        ledger["observed_cost_usd"] = round(observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6)
        ledger["latencies_seconds"].append(round(latency, 6))
        ledger["status"] = "running"
        write_json(out / "ledger.json", ledger, overwrite=True)
    ledger["status"] = "complete"
    write_json(out / "ledger.json", ledger, overwrite=True)
    return True


def main() -> int:
    frozen, send = preflight(), sender()
    trace_ids = frozen["config"]["trace_request_ids"]
    ledger = {"status": "ready", "attempt_n": 0, "completed_blinded_request_ids": [], "input_tokens": 0, "output_tokens": 0, "observed_cost_usd": 0.0, "retry_n": 0, "latencies_seconds": []}
    if not run_batch(send, frozen, trace_ids, TRACE, ledger):
        return 76
    write_json(TRACE / "summary.json", {"status": "trace_complete", "valid_n": 5, "failure_n": 0, "retry_n": 0, "cost_usd": ledger["observed_cost_usd"]}, overwrite=False)
    remaining = [x for x in sorted(frozen["plans"]) if x not in set(trace_ids)]
    if projection(ledger, remaining, frozen["plans"], frozen["config"]["ambiguous_dispatch_reserve_usd"]) > frozen["config"]["generation_hard_cap_usd"]:
        return 77
    full_ledger = {**ledger, "status": "ready", "reused_trace_request_ids": trace_ids}
    if not run_batch(send, frozen, remaining, FULL, full_ledger):
        return 78
    summary = {"status": "complete", "coverage": "100/100", "trace_reused": 5, "new_full_calls": 95, "retry_n": 0, "failure_n": 0, "input_tokens": full_ledger["input_tokens"], "output_tokens": full_ledger["output_tokens"], "cost_usd": full_ledger["observed_cost_usd"], "mean_latency_seconds": statistics.fmean(full_ledger["latencies_seconds"]), "median_latency_seconds": statistics.median(full_ledger["latencies_seconds"]), "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(FULL / "summary.json", summary, overwrite=False)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
