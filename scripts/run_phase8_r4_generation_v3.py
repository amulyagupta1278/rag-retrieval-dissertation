#!/usr/bin/env python3
"""Run approved R4 V3 semantic-contract trace and conditional full recovery."""

from __future__ import annotations

import copy, hashlib, json, statistics, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.generation.phase7_v2_freeze import SDK_VERSION, observed_cost_usd  # noqa: E402
from src.generation.phase8_r4_v2_validation import validate_provider_response  # noqa: E402
from src.utils.atomic_io import write_json  # noqa: E402

BASE = ROOT / "runs/phase8_r4_improvements"
FREEZE = BASE / "generation_r4_v3_freeze"
TRACE = BASE / "generation_r4_v3_trace"
FULL = BASE / "generation_r4_v3_full"
APPROVAL = ROOT / "audits/phase8_r4/generation_v3_execution_approval.json"
MAX_OUTPUT = 1024


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def obj(path): return json.loads(Path(path).read_text())
def rows(path): return [json.loads(x) for x in Path(path).read_text().splitlines() if x]
def digest(value): return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def preflight():
    config, approval, manifest = obj(FREEZE / "execution_config.json"), obj(APPROVAL), obj(FREEZE / "freeze_manifest.json")
    if config["status"] != "frozen_pending_execution_approval" or approval["status"] != "owner_approved": raise RuntimeError("V3 approval differs")
    if approval["execution_config_sha256"] != sha(FREEZE / "execution_config.json") or approval["freeze_manifest_sha256"] != sha(FREEZE / "freeze_manifest.json"): raise RuntimeError("V3 approved hashes differ")
    if approval["request_plan_sha256"] != sha(FREEZE / "request_plan.jsonl") or config["prior_cumulative_r4_cost_usd"] + config["v3_hard_cap_usd"] > 3.70: raise RuntimeError("V3 plan/cap differs")
    if subprocess.run(["git", "merge-base", "--is-ancestor", approval["approved_commit"], "HEAD"], cwd=ROOT).returncode: raise RuntimeError("approved V3 commit missing")
    for section in ("inputs", "artifacts"):
        for rel, expected in manifest[section].items():
            if sha(ROOT / rel) != expected: raise RuntimeError(f"V3 frozen hash differs: {rel}")
    plans = {r["blinded_request_id"]: r for r in rows(FREEZE / "request_plan.jsonl")}
    payloads = {r["blinded_request_id"]: r for r in rows(FREEZE / "request_payloads.jsonl")}
    reused = rows(FREEZE / "reuse_50_records.jsonl")
    if len(plans) != 50 or set(plans) != set(payloads) or len(reused) != 50: raise RuntimeError("V3 coverage differs")
    for row in reused:
        if sha(ROOT / row["validated_path"]) != row["validated_sha256"]: raise RuntimeError(f"V3 reuse differs: {row['blinded_request_id']}")
    for blind, payload in payloads.items():
        if digest(payload["request"]) != plans[blind]["request_sha256"] or payload["request"]["max_tokens"] != MAX_OUTPUT: raise RuntimeError(f"V3 request differs: {blind}")
    if any(p.exists() and any(p.rglob("*")) for p in (TRACE, FULL)): raise RuntimeError("V3 outputs exist; refusing rerun")
    return {"config": config, "plans": plans, "payloads": payloads, "reused": reused}


def projection(ledger, ids, plans, reserve):
    return observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]) + reserve + sum(plans[x]["planned_input_token_envelope"] for x in ids) / 1e6 + len(ids) * MAX_OUTPUT * 5 / 1e6


def make_sender():
    env = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    if not env.get("ANTHROPIC_API_KEY") or anthropic.__version__ != SDK_VERSION: raise RuntimeError("credential or SDK differs")
    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"], max_retries=0, timeout=120.0)
    return lambda request: client.messages.create(**copy.deepcopy(request))


def run_batch(send, frozen, ids, out, ledger):
    config, plans, payloads = frozen["config"], frozen["plans"], frozen["payloads"]
    write_json(out / "ledger.json", ledger, overwrite=False)
    for blind in ids:
        remaining = [x for x in ids if x not in ledger["completed_blinded_request_ids"]]
        if projection(ledger, remaining, plans, config["ambiguous_dispatch_reserve_usd"]) > config["v3_hard_cap_usd"]:
            ledger.update(status="failed_projected_cost_cap", failed_blinded_request_id=blind); write_json(out / "ledger.json", ledger, overwrite=True); return False
        ledger.update(status="attempt_counted_before_dispatch", attempt_n=ledger["attempt_n"] + 1); write_json(out / "ledger.json", ledger, overwrite=True)
        started = time.perf_counter()
        try:
            response = send(payloads[blind]["request"]); raw = response.model_dump(mode="json", by_alias=True, exclude_none=True)
        except Exception as exc:
            ledger.update(status="failed_ambiguous_dispatch", failure={"type": type(exc).__name__}); write_json(out / "ledger.json", ledger, overwrite=True); return False
        write_json(out / "raw" / f"{blind}.json", raw, overwrite=False)
        try: valid = validate_provider_response(raw, available_evidence_ids=list(plans[blind]["evidence_id_to_chunk_id"]))
        except Exception as exc:
            ledger.update(status="failed_terminal_validation", failure={"type": type(exc).__name__, "message": str(exc), "blinded_request_id": blind}); write_json(out / "ledger.json", ledger, overwrite=True); return False
        write_json(out / "validated" / f"{blind}.json", {"blinded_request_id": blind, **valid}, overwrite=False)
        ledger["completed_blinded_request_ids"].append(blind); ledger["input_tokens"] += valid["usage"]["input_tokens"]; ledger["output_tokens"] += valid["usage"]["output_tokens"]
        ledger["observed_cost_usd"] = round(observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6); ledger["latencies_seconds"].append(round(time.perf_counter() - started, 6)); ledger["status"] = "running"; write_json(out / "ledger.json", ledger, overwrite=True)
    ledger["status"] = "complete"; write_json(out / "ledger.json", ledger, overwrite=True); return True


def main():
    frozen, send = preflight(), make_sender(); trace_ids = frozen["config"]["v3_trace_request_ids"]
    ledger = {"status": "ready", "attempt_n": 0, "completed_blinded_request_ids": [], "input_tokens": 0, "output_tokens": 0, "observed_cost_usd": 0.0, "retry_n": 0, "latencies_seconds": []}
    if not run_batch(send, frozen, trace_ids, TRACE, ledger): return 76
    write_json(TRACE / "summary.json", {"status": "v3_trace_complete", "valid_n": 5, "retry_n": 0, "cost_usd": ledger["observed_cost_usd"]}, overwrite=False)
    remaining = [x for x in sorted(frozen["plans"]) if x not in set(trace_ids)]
    if projection(ledger, remaining, frozen["plans"], frozen["config"]["ambiguous_dispatch_reserve_usd"]) > frozen["config"]["v3_hard_cap_usd"]: return 77
    full_ledger = {**ledger, "status": "ready", "reused_trace_request_ids": trace_ids}
    if not run_batch(send, frozen, remaining, FULL, full_ledger): return 78
    combined = [{**r, "source": r.get("source", "prior_valid")} for r in frozen["reused"]]
    for blind in sorted(frozen["plans"]):
        source = TRACE if blind in trace_ids else FULL; path = source / "validated" / f"{blind}.json"
        combined.append({"blinded_request_id": blind, "source": "v3_trace" if source == TRACE else "v3_full", "validated_path": str(path.relative_to(ROOT)), "validated_sha256": sha(path), "request_sha256": frozen["plans"][blind]["request_sha256"]})
    combined.sort(key=lambda r: r["blinded_request_id"]); (FULL / "combined_100_record_index.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in combined))
    summary = {"status": "complete", "coverage": "100/100", "prior_reused": 50, "v3_trace_valid": 5, "v3_full_valid": 45, "retry_n": 0, "failure_n": 0, "input_tokens": full_ledger["input_tokens"], "output_tokens": full_ledger["output_tokens"], "v3_cost_usd": full_ledger["observed_cost_usd"], "cumulative_r4_cost_usd": round(2.643100 + full_ledger["observed_cost_usd"], 6), "mean_latency_seconds": statistics.fmean(full_ledger["latencies_seconds"]), "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(FULL / "summary.json", summary, overwrite=False); print(json.dumps(summary, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
