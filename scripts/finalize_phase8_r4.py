#!/usr/bin/env python3
"""Freeze final R4 hashes after successful automated completion."""

import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audits/phase8_r4/final_manifest.json"
PATHS = [
    "docs/PHASE8_R4_FINAL_REPORT.md",
    "audits/phase8_r4/canonical_status.json",
    "runs/phase8_r4_improvements/manifest.json",
    "runs/phase8_r4_improvements/evaluation_r4/metrics.json",
    "runs/phase8_r4_improvements/evaluation_r4/exploratory_statistics.json",
    "runs/phase8_r4_improvements/prompt_rag_r4_v2_full/summary.json",
    "runs/phase8_r4_improvements/generation_r4_v3_full/summary.json",
    "runs/phase8_r4_improvements/generation_r4_v3_full/combined_100_record_index.jsonl",
    "runs/phase8_r4_improvements/evaluation_ai_h5/ai_quality_labels_100.jsonl",
    "runs/phase8_r4_improvements/evaluation_ai_h5/ai_owner_agreement.json",
    "runs/phase8_r4_improvements/evaluation_ai_h5/h5_results.json",
    "runs/phase8_r4_improvements/evaluation_ai_h5/manifest.json",
    "runs/phase8_r4_improvements/benchmark/synthesis_candidates_20.jsonl",
    "audits/phase8_r4/prompt_rag_trace_v1_failure_checkpoint.json",
    "audits/phase8_r4/generation_v1_failure_checkpoint.json",
    "audits/phase8_r4/generation_v2_validator_failure_checkpoint.json",
    "audits/phase8_r4/generation_v2_corrected_semantic_failure_checkpoint.json",
]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists(): raise SystemExit("final manifest exists; refusing overwrite")
    paths = [ROOT / p for p in PATHS]
    if not all(p.is_file() for p in paths): raise SystemExit("final artifact missing")
    status = json.loads((ROOT / "audits/phase8_r4/canonical_status.json").read_text())
    if status["human_validation_complete"] is not False or status["generation_valid"] != 100 or status["cumulative_r4_api_cost_usd"] > status["absolute_hard_cap_usd"]:
        raise SystemExit("final R4 state invalid")
    manifest = {"schema_version": 1, "status": status["status"], "human_validation_complete": False, "api_calls_during_finalization": 0, "artifacts": {str(p.relative_to(ROOT)): sha(p) for p in paths}}
    OUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__": main()
