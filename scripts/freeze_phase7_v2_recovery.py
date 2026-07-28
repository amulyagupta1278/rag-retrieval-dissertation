#!/usr/bin/env python3
"""Freeze network-free Phase 7 V2 recovery with 512-token output cap."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.generation import phase7_freeze as v1  # noqa: E402
from src.generation.phase7_v2_freeze import (  # noqa: E402
    HARD_COST_CAP_USD,
    MAX_OUTPUT_TOKENS,
    MODEL,
    SDK_VERSION,
    TRACE_N,
    V1_MAX_OUTPUT_TOKENS,
    V1_SPENT_USD,
    PREVIOUS_HARD_COST_CAP_USD,
    build_request,
    conservative_input_token_envelope,
    maximum_cost_usd,
    request_sha256,
)
from src.utils.atomic_io import write_bytes, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


BASE_COMMIT = "86bd63d2ad141ef1ca756605a77a9fd430aaf31a"
V1_FREEZE_COMMIT = "511c232537c14a28b12eee7022416a6b23dd1485"
V1_RUNNER_COMMIT = "29bae3616233f7ff76dbf6707cc399a0b0d63ab0"
V1_EVIDENCE_COMMIT = "86bd63d2ad141ef1ca756605a77a9fd430aaf31a"
V1_CHECKPOINT_SHA256 = "2d195c8c5c44d806111cb0c346d25c4b8bf1ffb21574893c7fe7f9ddb8f9337c"
V1_ROOT = ROOT / "runs/v2/phase7_generation_claude_top3"
V2_ROOT = ROOT / "runs/v2/phase7_generation_claude_top3_v2"
V1_AUDIT_ROOT = ROOT / "audits/phase7_generation"
V2_AUDIT_ROOT = ROOT / "audits/phase7_generation/v2"
V1_DOC_ROOT = ROOT / "docs/phase7"
V2_DOC_ROOT = ROOT / "docs/phase7/v2"
OWNER_CAP_AMENDMENT_STATEMENT = (
    "i have just added money into my claude api u can spend upto 3 dollar"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {relative(path)}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"invalid JSONL: {relative(path)}")
    return rows


def file_map(paths: list[Path]) -> dict[str, str]:
    return {relative(path): sha256_file(path) for path in sorted(paths)}


def verify_ancestor(commit: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"required V1 commit is not current history: {commit}")


def verify_v1() -> dict[str, str]:
    verify_ancestor(BASE_COMMIT)
    for commit in (V1_FREEZE_COMMIT, V1_RUNNER_COMMIT, V1_EVIDENCE_COMMIT):
        verify_ancestor(commit)
    if version("anthropic") != SDK_VERSION:
        raise ValueError(f"installed Anthropic SDK must equal {SDK_VERSION}")

    manifest = read_json(V1_ROOT / "freeze_manifest.json")
    for field in ("artifacts", "code", "dependency_hashes"):
        for path, expected in manifest[field].items():
            if sha256_file(ROOT / path) != expected:
                raise ValueError(f"V1 freeze hash mismatch: {path}")
    checkpoint_path = V1_AUDIT_ROOT / "trace_v1_failure_checkpoint.json"
    if sha256_file(checkpoint_path) != V1_CHECKPOINT_SHA256:
        raise ValueError("V1 failure checkpoint hash differs")
    checkpoint = read_json(checkpoint_path)
    expected_checkpoint = {
        "attempted_request_n": 2,
        "completed_valid_request_n": 1,
        "input_tokens": 4002,
        "observed_cost_usd": V1_SPENT_USD,
        "output_tokens": 369,
        "retry_n": 0,
        "status": "terminal_trace_failure_preserved",
    }
    for field, expected in expected_checkpoint.items():
        if checkpoint.get(field) != expected:
            raise ValueError(f"V1 checkpoint field differs: {field}")
    if (
        checkpoint.get("failure", {}).get("blinded_request_id") != "P7B002"
        or checkpoint.get("failure", {}).get("class") != "truncation"
        or checkpoint.get("failure", {}).get("stop_reason") != "max_tokens"
        or checkpoint.get("full_panel_executed") is not False
    ):
        raise ValueError("V1 terminal failure evidence differs")

    paths = [path for path in V1_ROOT.rglob("*") if path.is_file()]
    paths.extend(
        [
            V1_AUDIT_ROOT / "trace_execution_approval.json",
            checkpoint_path,
            ROOT / "scripts/run_phase7_generation_trace.py",
            ROOT / "src/generation/phase7_freeze.py",
        ]
    )
    return file_map(paths)


def generation_protocol() -> str:
    return """# Phase 7 V2 Claude Top-3 Generation Recovery Protocol

Status: frozen offline; $3.00 cumulative owner cap passes; live trace still requires
commit-bound owner approval.

## Recovery boundary

V1 stopped after two attempts: one valid response, then terminal `max_tokens`
truncation for P7B002. V1 remains immutable and is never resumed, retried,
overwritten, deleted, relabelled, or reused as V2 output.

V2 is a separate protocol version and output root. Sole generation-contract change:
`max_tokens` increases from 256 to 512. Provider, exact model, prompt, schema,
top-3 contexts, 170-pair panel, rankings, serialization, temperature, citations,
abstention, zero-retry, no-fallback, failure, evaluation, and H5 contracts remain
unchanged.

## Trace and reuse

V2 uses the same deterministic ten logical trace IDs. Each V2 trace request is a
new protocol-version request, not a V1 retry. V1 responses cannot be reused.
A valid V2 trace response may count toward the final V2 panel only when its exact
canonical request SHA-256 equals the frozen V2 panel request SHA-256. Such a reused
record must not be billed again in full-panel execution.

Token-limit finish reason remains terminal `truncation`; partial content is invalid.
No retry, replacement, fallback, or best-of selection is allowed.

## Cost gate

Frozen pricing remains Anthropic Haiku input $1/MTok and output $5/MTok. V1 spent
$0.005847. Conservative V2 full-panel exposure plus ambiguous-dispatch reserve and
V1 spend totals $1.119437. Owner amended cumulative Phase 7 cap from $0.95 to
$3.00 before V2 freeze, leaving $1.880563 headroom after worst-case exposure.

Every dispatch must first account for V1 spend, actual V2 usage, all unexecuted V2
request envelopes, and ambiguous reserve. Cap failure occurs before network call.
"""


def approval_template() -> str:
    return (
        "Approve Phase 7 V2 512-token 10-request recovery trace at commit "
        "<V2_FREEZE_COMMIT>, using claude-haiku-4-5-20251001, frozen prompt, "
        "schema, top-3 contexts, and trace IDs, temperature 0, zero retries, no "
        "fallback or replacement, and separate V2 outputs, under owner-amended "
        "cumulative Phase 7 generation hard cap of $3.00, including $0.005847 V1 spend, "
        "$1.106295 V2 full-panel worst case, and $0.007295 ambiguous-dispatch "
        "reserve. Valid V2 trace records may be reused only for byte-identical "
        "frozen V2 panel requests and must not be billed twice. Full-panel execution "
        "remains prohibited pending V2 trace review.\n"
    )


def main() -> None:
    args = parse_args()
    v1_hashes_before = verify_v1()
    if V2_ROOT.exists() and not args.overwrite:
        raise FileExistsError(f"V2 output exists: {relative(V2_ROOT)}")
    if V2_AUDIT_ROOT.exists() and not args.overwrite:
        raise FileExistsError(f"V2 audit exists: {relative(V2_AUDIT_ROOT)}")
    if V2_DOC_ROOT.exists() and not args.overwrite:
        raise FileExistsError(f"V2 docs exist: {relative(V2_DOC_ROOT)}")

    v1_payloads = read_jsonl(V1_ROOT / "blinded/request_payloads.jsonl")
    v1_contexts = read_jsonl(V1_ROOT / "blinded/serialized_contexts.jsonl")
    v1_plan = read_jsonl(V1_ROOT / "sealed/request_plan.jsonl")
    v1_trace = read_json(V1_ROOT / "sealed/trace_plan.json")
    prompt_text = (V1_ROOT / "prompt.txt").read_text(encoding="utf-8")
    schema = read_json(V1_ROOT / "response_schema.json")
    contexts_by_id = {row["blinded_request_id"]: row for row in v1_contexts}
    plan_by_id = {row["blinded_request_id"]: row for row in v1_plan}
    if len(contexts_by_id) != 170 or len(plan_by_id) != 170:
        raise ValueError("V1 panel cardinality differs")

    v2_payloads: list[dict[str, Any]] = []
    v2_plan: list[dict[str, Any]] = []
    for row in v1_payloads:
        blinded_id = row["blinded_request_id"]
        serialized_context = contexts_by_id[blinded_id]["serialized_context"]
        request = build_request(
            prompt=prompt_text,
            serialized_context=serialized_context,
            schema=schema,
        )
        v1_request_without_cap = copy.deepcopy(row["request"])
        v2_request_without_cap = copy.deepcopy(request)
        if v1_request_without_cap.pop("max_tokens") != V1_MAX_OUTPUT_TOKENS:
            raise ValueError("V1 request output-token cap differs")
        if v2_request_without_cap.pop("max_tokens") != MAX_OUTPUT_TOKENS:
            raise ValueError("V2 request output-token cap differs")
        if v1_request_without_cap != v2_request_without_cap:
            raise ValueError(f"V2 request changes more than token cap: {blinded_id}")
        request_hash = request_sha256(request)
        envelope = conservative_input_token_envelope(request)
        if envelope != plan_by_id[blinded_id]["planned_input_token_envelope"]:
            raise ValueError("V2 input envelope unexpectedly differs from V1")
        v2_payloads.append(
            {
                "blinded_request_id": blinded_id,
                "request": request,
                "request_sha256": request_hash,
            }
        )
        plan_row = copy.deepcopy(plan_by_id[blinded_id])
        plan_row["request_hash"] = request_hash
        v2_plan.append(plan_row)

    selected_ids = [row["logical_request_id"] for row in v1_trace["selected"]]
    trace_ids = set(selected_ids)
    trace_input = sum(
        row["planned_input_token_envelope"]
        for row in v2_plan
        if row["logical_request_id"] in trace_ids
    )
    full_input = sum(row["planned_input_token_envelope"] for row in v2_plan)
    remaining_input = full_input - trace_input
    largest_input = max(row["planned_input_token_envelope"] for row in v2_plan)
    trace_cost = maximum_cost_usd(trace_input, TRACE_N)
    full_cost = maximum_cost_usd(full_input, 170)
    remaining_cost = maximum_cost_usd(remaining_input, 170 - TRACE_N)
    reserve = maximum_cost_usd(largest_input, 1)
    cumulative = V1_SPENT_USD + full_cost + reserve
    remaining_cap = HARD_COST_CAP_USD - V1_SPENT_USD
    headroom = HARD_COST_CAP_USD - cumulative
    if cumulative > HARD_COST_CAP_USD:
        raise ValueError("V2 cumulative worst case exceeds amended owner cap")
    cost_plan = {
        "ambiguous_dispatch_reserve": {
            "basis": "one largest V2 request at maximum 512-token output",
            "input_token_envelope": largest_input,
            "usd": reserve,
        },
        "cache_discount_assumed": False,
        "current_hard_cap_usd": HARD_COST_CAP_USD,
        "cumulative_worst_case_including_v1_usd": cumulative,
        "full_panel": {
            "input_token_envelope": full_input,
            "maximum_output_tokens": 170 * MAX_OUTPUT_TOKENS,
            "request_n": 170,
            "trace_records_count_once": True,
            "worst_case_usd": full_cost,
        },
        "hard_cap_pass": True,
        "input_price_usd_per_million_tokens": v1.INPUT_USD_PER_MILLION,
        "minimum_required_cap_usd": cumulative,
        "output_price_usd_per_million_tokens": v1.OUTPUT_USD_PER_MILLION,
        "pricing": read_json(V1_ROOT / "cost_plan.json")["pricing"],
        "pricing_lineage": {
            "source_v1_cost_plan_sha256": sha256_file(V1_ROOT / "cost_plan.json"),
            "status": "unchanged frozen official pricing metadata inherited from V1",
        },
        "remaining_after_trace": {
            "input_token_envelope": remaining_input,
            "maximum_output_tokens": (170 - TRACE_N) * MAX_OUTPUT_TOKENS,
            "request_n": 170 - TRACE_N,
            "worst_case_usd": remaining_cost,
        },
        "headroom_after_cumulative_worst_case_usd": headroom,
        "previous_hard_cap_usd": PREVIOUS_HARD_COST_CAP_USD,
        "remaining_current_cap_after_v1_usd": remaining_cap,
        "token_counting": read_json(V1_ROOT / "cost_plan.json")["token_counting"],
        "trace": {
            "cumulative_with_v1_and_reserve_usd": V1_SPENT_USD + trace_cost + reserve,
            "input_token_envelope": trace_input,
            "maximum_output_tokens": TRACE_N * MAX_OUTPUT_TOKENS,
            "request_n": TRACE_N,
            "worst_case_usd": trace_cost,
        },
        "v1_spent_usd": V1_SPENT_USD,
    }

    copied_files = {
        V1_ROOT / "prompt.txt": V2_ROOT / "prompt.txt",
        V1_ROOT / "response_schema.json": V2_ROOT / "response_schema.json",
        V1_ROOT / "blinded/serialized_contexts.jsonl": V2_ROOT
        / "blinded/serialized_contexts.jsonl",
        V1_ROOT / "dependency_manifest.json": V2_ROOT / "dependency_manifest.json",
        V1_ROOT / "failure_contract.json": V2_ROOT / "failure_contract.json",
        V1_ROOT / "evaluator_protocol.json": V2_ROOT / "evaluator_protocol.json",
        V1_ROOT / "h5_protocol.json": V2_ROOT / "h5_protocol.json",
        V1_ROOT / "sealed/trace_plan.json": V2_ROOT / "sealed/trace_plan.json",
        V1_DOC_ROOT / "EVALUATION_PROTOCOL_V1.md": V2_DOC_ROOT
        / "EVALUATION_PROTOCOL_V1.md",
        V1_DOC_ROOT / "H5_ANALYSIS_PROTOCOL_V1.md": V2_DOC_ROOT
        / "H5_ANALYSIS_PROTOCOL_V1.md",
    }
    for source, target in copied_files.items():
        write_bytes(target, source.read_bytes(), overwrite=args.overwrite)
    failure_contract = read_json(V1_ROOT / "failure_contract.json")
    failure_contract["pre_dispatch_cost_rule"] = (
        "refuse when V1 spend plus actual V2 cost plus current and unexecuted V2 "
        "request envelopes plus ambiguous-dispatch reserve exceeds $3.00"
    )
    write_json(
        V2_ROOT / "failure_contract.json",
        failure_contract,
        overwrite=True,
    )
    write_bytes(
        V2_DOC_ROOT / "GENERATION_PROTOCOL_V2.md",
        generation_protocol().encode("utf-8"),
        overwrite=args.overwrite,
    )
    write_jsonl(
        V2_ROOT / "blinded/request_payloads.jsonl",
        v2_payloads,
        key="blinded_request_id",
        overwrite=args.overwrite,
    )
    write_jsonl(
        V2_ROOT / "sealed/request_plan.jsonl",
        v2_plan,
        key="logical_request_id",
        overwrite=args.overwrite,
    )
    write_json(V2_ROOT / "cost_plan.json", cost_plan, overwrite=args.overwrite)

    config = copy.deepcopy(read_json(V1_ROOT / "execution_config.json"))
    config["cost"] = cost_plan
    config["execution_enabled"] = False
    config["generation"]["max_output_tokens"] = MAX_OUTPUT_TOKENS
    config["hard_cap_usd"] = HARD_COST_CAP_USD
    config["output_root"] = relative(V2_ROOT)
    config["prompt"]["path"] = relative(V2_ROOT / "prompt.txt")
    config["response_schema"]["path"] = relative(V2_ROOT / "response_schema.json")
    config["status"] = "offline_frozen_pending_owner_trace_approval"
    write_json(V2_ROOT / "execution_config.json", config, overwrite=args.overwrite)

    v1_preservation = {
        "preservation_rule": "all listed V1 bytes immutable; V2 is separate protocol root",
        "schema_version": 1,
        "status": "verified_unchanged_before_v2_freeze",
        "v1_artifact_hashes": v1_hashes_before,
        "v1_commits": {
            "failure_evidence": V1_EVIDENCE_COMMIT,
            "freeze": V1_FREEZE_COMMIT,
            "runner": V1_RUNNER_COMMIT,
        },
        "v1_evidence": {
            "attempted_request_n": 2,
            "completed_valid_request_n": 1,
            "failure_blinded_request_id": "P7B002",
            "failure_class": "truncation",
            "full_panel_executed": False,
            "model_matched": True,
            "retry_n": 0,
            "spent_usd": V1_SPENT_USD,
        },
    }
    write_json(
        V2_AUDIT_ROOT / "v1_preservation.json",
        v1_preservation,
        overwrite=args.overwrite,
    )
    deviation = {
        "administrative_budget_amendment": {
            "affects_request_bytes": False,
            "owner_amended_cap_usd": HARD_COST_CAP_USD,
            "previous_cap_usd": PREVIOUS_HARD_COST_CAP_USD,
        },
        "changed_request_fields": {"max_tokens": {"v1": 256, "v2": 512}},
        "contexts_byte_identical": sha256_file(
            V1_ROOT / "blinded/serialized_contexts.jsonl"
        )
        == sha256_file(V2_ROOT / "blinded/serialized_contexts.jsonl"),
        "evaluation_protocol_byte_identical": sha256_file(
            V1_ROOT / "evaluator_protocol.json"
        )
        == sha256_file(V2_ROOT / "evaluator_protocol.json"),
        "failure_classes_identical": read_json(V1_ROOT / "failure_contract.json")[
            "failure_classes"
        ]
        == read_json(V2_ROOT / "failure_contract.json")["failure_classes"],
        "h5_protocol_byte_identical": sha256_file(V1_ROOT / "h5_protocol.json")
        == sha256_file(V2_ROOT / "h5_protocol.json"),
        "prompt_byte_identical": sha256_file(V1_ROOT / "prompt.txt")
        == sha256_file(V2_ROOT / "prompt.txt"),
        "request_n": len(v2_payloads),
        "response_schema_byte_identical": sha256_file(
            V1_ROOT / "response_schema.json"
        )
        == sha256_file(V2_ROOT / "response_schema.json"),
        "schema_version": 1,
        "sole_protocol_change": "max_tokens 256 to 512",
        "trace_plan_byte_identical": sha256_file(V1_ROOT / "sealed/trace_plan.json")
        == sha256_file(V2_ROOT / "sealed/trace_plan.json"),
        "unchanged_contracts": [
            "provider",
            "exact_model",
            "top3_context",
            "prompt",
            "response_schema",
            "questions",
            "systems",
            "rankings",
            "context_serialization",
            "citation_rules",
            "abstention_rules",
            "temperature",
            "zero_retries",
            "no_fallback",
            "failure_classes",
            "trace_selection",
            "evaluation_protocol",
            "h5_protocol",
        ],
    }
    if not all(
        value is True
        for key, value in deviation.items()
        if key.endswith("_byte_identical") or key == "failure_classes_identical"
    ):
        raise ValueError("V1-to-V2 unchanged artifact comparison failed")
    write_json(
        V2_AUDIT_ROOT / "v1_to_v2_deviation.json",
        deviation,
        overwrite=args.overwrite,
    )
    reuse_policy = {
        "duplicate_full_panel_call_allowed": False,
        "invalid_or_truncated_trace_reusable": False,
        "request_identity_rule": "canonical V2 trace request SHA-256 must equal frozen V2 panel request SHA-256",
        "response_replacement_allowed": False,
        "schema_version": 1,
        "successful_v2_trace_records_count_toward_panel": True,
        "v1_response_reusable_in_v2": False,
    }
    write_json(
        V2_AUDIT_ROOT / "reuse_policy.json",
        reuse_policy,
        overwrite=args.overwrite,
    )
    write_json(
        V2_AUDIT_ROOT / "cost_and_cap_audit.json",
        cost_plan,
        overwrite=args.overwrite,
    )
    write_bytes(
        V2_AUDIT_ROOT / "recovery_approval_template.txt",
        approval_template().encode("utf-8"),
        overwrite=args.overwrite,
    )
    write_json(
        V2_AUDIT_ROOT / "owner_cap_amendment.json",
        {
            "amended_cumulative_hard_cap_usd": HARD_COST_CAP_USD,
            "credential_or_billing_identifier_stored": False,
            "live_trace_authorized": False,
            "owner_statement": OWNER_CAP_AMENDMENT_STATEMENT,
            "previous_hard_cap_usd": PREVIOUS_HARD_COST_CAP_USD,
            "recorded_date": "2026-07-28",
            "schema_version": 1,
            "scope": "cumulative Phase 7 generation exposure",
            "status": "owner_cap_amendment_recorded",
        },
        overwrite=args.overwrite,
    )
    write_json(
        V2_AUDIT_ROOT / "freeze_readiness.json",
        {
            "api_calls_n": 0,
            "credential_access_n": 0,
            "current_cap_usd": HARD_COST_CAP_USD,
            "execution_authorized": False,
            "hard_cap_pass": True,
            "request_n": 170,
            "required_cap_usd": cumulative,
            "schema_version": 1,
            "status": "ready_for_commit_bound_owner_trace_approval",
            "trace_request_n": TRACE_N,
        },
        overwrite=args.overwrite,
    )

    v1_hashes_after = file_map(
        [Path(ROOT / path) for path in v1_hashes_before]
    )
    if v1_hashes_after != v1_hashes_before:
        raise ValueError("V1 bytes changed during V2 freeze")

    artifacts = [
        path
        for root in (V2_ROOT, V2_AUDIT_ROOT, V2_DOC_ROOT)
        for path in root.rglob("*")
        if path.is_file() and path.name != "freeze_manifest.json"
    ]
    freeze_manifest = {
        "artifacts": file_map(artifacts),
        "base_commit": BASE_COMMIT,
        "code": file_map(
            [
                ROOT / "scripts/freeze_phase7_v2_recovery.py",
                ROOT / "src/generation/phase7_v2_freeze.py",
                ROOT / "src/generation/phase7_freeze.py",
                ROOT / "src/generation/phase7_context.py",
                ROOT / "src/utils/atomic_io.py",
                ROOT / "src/utils/hashing.py",
            ]
        ),
        "current_hard_cap_usd": HARD_COST_CAP_USD,
        "cumulative_worst_case_usd": cumulative,
        "execution_authorized": False,
        "hard_cap_pass": True,
        "live_api_calls_n": 0,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "prompt_sha256": sha256_file(V2_ROOT / "prompt.txt"),
        "response_schema_sha256": sha256_file(V2_ROOT / "response_schema.json"),
        "schema_version": 1,
        "status": "frozen_offline_pending_owner_trace_approval",
        "trace_logical_request_ids": selected_ids,
        "v1_preservation_sha256": sha256_file(
            V2_AUDIT_ROOT / "v1_preservation.json"
        ),
    }
    write_json(
        V2_ROOT / "freeze_manifest.json",
        freeze_manifest,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "cumulative_worst_case_usd": cumulative,
                "full_panel_worst_case_usd": full_cost,
                "hard_cap_pass": True,
                "remaining_current_cap_after_v1_usd": remaining_cap,
                "headroom_usd": headroom,
                "trace_ids": selected_ids,
                "trace_worst_case_usd": trace_cost,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
