#!/usr/bin/env python3
"""Execute frozen 50-request Phase 9 H5 generation panel with zero retries."""

from __future__ import annotations

import copy
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase7_v2_freeze import SDK_VERSION, observed_cost_usd  # noqa: E402
from src.generation.phase8_r4_v2_validation import validate_provider_response  # noqa: E402
from src.utils.atomic_io import write_json  # noqa: E402

FREEZE = ROOT / "runs/phase9_h5_followup/generation_freeze"
OUT = ROOT / "runs/phase9_h5_followup/generation_50"
APPROVAL = ROOT / "audits/phase9_h5_followup/generation_50_approval.json"


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def obj(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def verify() -> dict:
    config, approval, manifest = obj(FREEZE / "execution_config.json"), obj(APPROVAL), obj(FREEZE / "freeze_manifest.json")
    if config["status"] != "frozen_owner_approved" or approval["status"] != "owner_approved":
        raise RuntimeError("approval missing")
    if sha(FREEZE / "execution_config.json") != approval["execution_config_sha256"] or sha(FREEZE / "freeze_manifest.json") != approval["freeze_manifest_sha256"]:
        raise RuntimeError("approval hash mismatch")
    for section in ("inputs", "artifacts"):
        for rel, expected in manifest[section].items():
            if sha(ROOT / rel) != expected:
                raise RuntimeError(f"frozen hash differs: {rel}")
    plans = {row["blinded_request_id"]: row for row in rows(FREEZE / "request_plan.jsonl")}
    payloads = {row["blinded_request_id"]: row for row in rows(FREEZE / "request_payloads.jsonl")}
    if len(plans) != 50 or set(plans) != set(payloads):
        raise RuntimeError("frozen request coverage differs")
    if OUT.exists() and any(OUT.rglob("*")):
        raise RuntimeError("generation output exists; refuse rerun")
    return {"config": config, "plans": plans, "payloads": payloads}


def projected(ledger, remaining, plans, reserve):
    return observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]) + reserve + sum(plans[item]["planned_input_token_envelope"] for item in remaining) / 1e6 + len(remaining) * 1024 * 5 / 1e6


def main() -> int:
    frozen = verify()
    env = {key: value for key, value in dotenv_values(ROOT / ".env").items() if value is not None}
    if not env.get("ANTHROPIC_API_KEY") or anthropic.__version__ != SDK_VERSION:
        raise RuntimeError("credential or Anthropic SDK differs")
    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"], max_retries=0, timeout=120.0)
    config, plans, payloads = frozen["config"], frozen["plans"], frozen["payloads"]
    ordered = sorted(plans)
    ledger = {"status": "ready", "attempt_n": 0, "completed_blinded_request_ids": [], "input_tokens": 0, "output_tokens": 0, "observed_cost_usd": 0.0, "retry_n": 0, "latencies_seconds": []}
    write_json(OUT / "ledger.json", ledger, overwrite=False)
    for blind in ordered:
        remaining = [item for item in ordered if item not in ledger["completed_blinded_request_ids"]]
        if projected(ledger, remaining, plans, config["ambiguous_dispatch_reserve_usd"]) > config["generation_hard_cap_usd"]:
            ledger.update(status="failed_projected_cost_cap", failed_blinded_request_id=blind)
            write_json(OUT / "ledger.json", ledger, overwrite=True)
            return 77
        ledger.update(status="attempt_counted_before_dispatch", attempt_n=ledger["attempt_n"] + 1, active_blinded_request_id=blind)
        write_json(OUT / "ledger.json", ledger, overwrite=True)
        started = time.perf_counter()
        try:
            response = client.messages.create(**copy.deepcopy(payloads[blind]["request"]))
            raw = response.model_dump(mode="json", by_alias=True, exclude_none=True)
        except Exception as exc:
            ledger.update(status="failed_ambiguous_dispatch", failure={"type": type(exc).__name__})
            write_json(OUT / "ledger.json", ledger, overwrite=True)
            return 76
        write_json(OUT / "raw" / f"{blind}.json", raw, overwrite=False)
        try:
            valid = validate_provider_response(raw, available_evidence_ids=list(plans[blind]["evidence_id_to_chunk_id"]))
        except Exception as exc:
            ledger.update(status="failed_terminal_validation", failure={"type": type(exc).__name__, "message": str(exc)})
            write_json(OUT / "ledger.json", ledger, overwrite=True)
            return 78
        write_json(OUT / "validated" / f"{blind}.json", {"blinded_request_id": blind, **valid}, overwrite=False)
        ledger["completed_blinded_request_ids"].append(blind)
        ledger["input_tokens"] += valid["usage"]["input_tokens"]
        ledger["output_tokens"] += valid["usage"]["output_tokens"]
        ledger["observed_cost_usd"] = round(observed_cost_usd(ledger["input_tokens"], ledger["output_tokens"]), 6)
        ledger["latencies_seconds"].append(round(time.perf_counter() - started, 6))
        ledger.update(status="running", active_blinded_request_id=None)
        write_json(OUT / "ledger.json", ledger, overwrite=True)
    ledger["status"] = "complete"
    write_json(OUT / "ledger.json", ledger, overwrite=True)
    summary = {
        "status": "complete", "coverage": "50/50", "retry_n": 0,
        "input_tokens": ledger["input_tokens"], "output_tokens": ledger["output_tokens"],
        "cost_usd": ledger["observed_cost_usd"],
        "mean_latency_seconds": statistics.fmean(ledger["latencies_seconds"]),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(OUT / "summary.json", summary, overwrite=False)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
