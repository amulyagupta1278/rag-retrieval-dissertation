#!/usr/bin/env python3
"""Run one owner-approved Phase 5B network scope after fail-closed preflight."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.retrievers.prompt_rag_gemini_v1 import (  # noqa: E402
    AttemptFailure,
    ExecutionApprovalError,
    ExecutionLock,
    FreeTierConfirmationError,
    NetworkAttemptCapError,
    NetworkAttemptLedger,
    PromptRAGContractError,
    QuotaExhaustedError,
    build_request,
    create_client_from_environment,
    execute_with_retry,
    make_live_sender,
    recompute_trace_decision,
    require_control_approval,
    require_free_tier_owner_confirmation,
    require_mode_execution_approval,
    sha256_text,
    stable_json,
    validate_response,
)
from src.utils.atomic_io import write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


CONFIG_PATH = ROOT / "configs/prompt_rag_v1_frozen.json"
MANIFEST_PATH = ROOT / "audits/phase5b/freeze_manifest.json"
ROTATION_ATTESTATION_PATH = ROOT / "audits/phase5b/credential_rotation_owner_attestation.json"
FREE_TIER_CONFIRMATION_PATH = ROOT / "audits/phase5b/free_tier_owner_confirmation.json"
TRACE_APPROVAL_PATH = ROOT / "audits/phase5b/trace_execution_approval.json"
FULL_APPROVAL_PATH = ROOT / "audits/phase5b/full_execution_approval.json"
RESUME_APPROVAL_PATH = ROOT / "audits/phase5b/quota_reset_resume_approval.json"
TRACE_DECISION_PATH = ROOT / "runs/v2/phase5b_prompt_rag/trace/repeatability_decision.json"
OUTPUT_ROOT = ROOT / "runs/v2/phase5b_prompt_rag"
EXPECTED_QUERY_IDS = tuple(f"v2q-{index:03d}" for index in range(1, 35))
RUNTIME_CONTROL_PATHS = frozenset(
    {
        FREE_TIER_CONFIRMATION_PATH,
        TRACE_APPROVAL_PATH,
        FULL_APPROVAL_PATH,
        RESUME_APPROVAL_PATH,
    }
)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromptRAGContractError(f"invalid JSON artifact: {path.relative_to(ROOT)}") from exc
    if not isinstance(value, dict):
        raise PromptRAGContractError(f"JSON artifact must be object: {path.relative_to(ROOT)}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PromptRAGContractError(f"cannot read JSONL artifact: {path.relative_to(ROOT)}") from exc
    for line_number, line in enumerate(raw_lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PromptRAGContractError(
                f"invalid JSONL at {path.relative_to(ROOT)}:{line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise PromptRAGContractError(
                f"JSONL row must be object at {path.relative_to(ROOT)}:{line_number}"
            )
        rows.append(row)
    if not rows:
        raise PromptRAGContractError(f"JSONL artifact is empty: {path.relative_to(ROOT)}")
    return rows


def _canonical(relative: str) -> Path:
    """Resolve config path only when it remains canonical and inside repository."""

    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise PromptRAGContractError("frozen config contains non-relative path")
    candidate = (ROOT / relative).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        raise PromptRAGContractError("frozen config path escapes repository") from None
    if candidate != ROOT / relative:
        raise PromptRAGContractError("frozen config path is not canonical")
    return candidate


def build_logical_plan(
    mode: str, query_ids: list[str], trace_ids: list[str]
) -> list[tuple[str, str]]:
    """Return exact trace 24-call or remaining-full 26-call plan."""

    if query_ids != list(EXPECTED_QUERY_IDS):
        raise PromptRAGContractError("execution requires exact ordered R5 query IDs v2q-001..034")
    if len(trace_ids) != 8 or len(set(trace_ids)) != 8 or not set(trace_ids) <= set(query_ids):
        raise PromptRAGContractError("trace selection must contain eight exact known IDs")
    if mode == "trace":
        return [
            (f"{query_id}:{role}", query_id)
            for role in ("primary", "replicate-1", "replicate-2")
            for query_id in trace_ids
        ]
    if mode == "full":
        return [
            (f"{query_id}:primary", query_id)
            for query_id in query_ids
            if query_id not in set(trace_ids)
        ]
    raise PromptRAGContractError(f"unknown mode: {mode}")


def _plan_sha256(plan: list[tuple[str, str]]) -> str:
    rows = [
        {"logical_request_id": logical_id, "query_id": query_id}
        for logical_id, query_id in plan
    ]
    return sha256_text(stable_json(rows))


def _git_identity() -> tuple[str, str]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    return commit, tree


def _is_allowed_resume_output(
    relative: str, *, output_root: Path, allowed_safe_names: set[str]
) -> bool:
    """Accept only canonical durable files created by an interrupted mode run."""

    root_relative = output_root.relative_to(ROOT)
    path = Path(relative)
    try:
        suffix = path.relative_to(root_relative)
    except ValueError:
        return False
    parts = suffix.parts
    if parts == ("control", "ledger.json"):
        return True
    if len(parts) == 2 and parts[0] == "raw":
        return parts[1].endswith(".json") and parts[1][:-5] in allowed_safe_names
    if len(parts) == 3 and parts[0] == "attempts" and parts[1] in allowed_safe_names:
        name = parts[2]
        return name.startswith("attempt-") and name.endswith(".json") and name[8:-5] in {
            "001",
            "002",
            "003",
        }
    if len(parts) == 2 and parts[0] == "failures":
        return any(parts[1] == f"{safe}__quota-stop.json" for safe in allowed_safe_names)
    return False


def _validate_worktree_status(
    status: str,
    *,
    allowed_runtime_controls: set[Path],
    resume_output_root: Path | None = None,
    allowed_resume_safe_names: set[str] | None = None,
) -> None:
    """Allow only exact unstaged runtime-control edits over committed HEAD."""

    allowed = {str(path.relative_to(ROOT)) for path in allowed_runtime_controls}
    for line in status.splitlines():
        if len(line) < 4:
            raise ExecutionApprovalError(
                "frozen implementation differs from HEAD outside allowed runtime controls"
            )
        state, relative = line[:2], line[3:]
        control_allowed = state == " M" and relative in allowed
        resume_allowed = (
            resume_output_root is not None
            and allowed_resume_safe_names is not None
            and state in {" M", "??"}
            and _is_allowed_resume_output(
                relative,
                output_root=resume_output_root,
                allowed_safe_names=allowed_resume_safe_names,
            )
        )
        if not control_allowed and not resume_allowed:
            raise ExecutionApprovalError(
                "frozen implementation differs from HEAD outside allowed runtime controls"
            )


def _require_frozen_worktree(
    *,
    mode: str,
    resume_after_quota_reset: bool,
    plan: list[tuple[str, str]],
) -> None:
    """Require committed frozen code while permitting explicit owner-control records."""

    approval_path = TRACE_APPROVAL_PATH if mode == "trace" else FULL_APPROVAL_PATH
    allowed = {FREE_TIER_CONFIRMATION_PATH, approval_path}
    if resume_after_quota_reset:
        allowed.add(RESUME_APPROVAL_PATH)
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True
    )
    mode_root = OUTPUT_ROOT / mode
    safe_names = {_safe_name(logical_id, {item[0] for item in plan}) for logical_id, _ in plan}
    _validate_worktree_status(
        status,
        allowed_runtime_controls=allowed,
        resume_output_root=mode_root if resume_after_quota_reset else None,
        allowed_resume_safe_names=safe_names if resume_after_quota_reset else None,
    )


def _require_rotation_attestation(path: Path) -> dict[str, Any]:
    artifact = _json(path)
    expected = {
        "artifact_type": "phase5b_credential_rotation_owner_attestation",
        "attestation": {
            "exposed_credential_replaced": True,
            "exposed_credential_revoked": True,
            "replacement_remains_environment_only": True,
        },
        "confirmed_at": artifact.get("confirmed_at"),
        "credentials_or_identifiers_stored": False,
        "schema_version": 1,
        "status": "owner_confirmed",
    }
    if not isinstance(artifact.get("confirmed_at"), str) or artifact != expected:
        raise ExecutionApprovalError("credential rotation owner attestation is invalid")
    return artifact


def _verify_manifest(config_hash: str) -> dict[str, Any]:
    manifest = _json(MANIFEST_PATH)
    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, dict) or hashes.get("configs/prompt_rag_v1_frozen.json") != config_hash:
        raise PromptRAGContractError("freeze manifest does not bind exact frozen config")
    runtime_controls = manifest.get("mutable_runtime_controls")
    expected_controls = sorted(str(path.relative_to(ROOT)) for path in RUNTIME_CONTROL_PATHS)
    if runtime_controls != expected_controls or set(runtime_controls) & set(hashes):
        raise PromptRAGContractError("freeze manifest mutable runtime controls are invalid")
    for relative, expected in hashes.items():
        path = _canonical(relative)
        if path == MANIFEST_PATH:
            raise PromptRAGContractError("freeze manifest must not hash itself")
        if not path.is_file() or sha256_file(path) != expected:
            raise PromptRAGContractError(f"freeze manifest hash mismatch: {relative}")
    return manifest


def _verify_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise PromptRAGContractError(f"{label} SHA-256 mismatch")


def _trace_thresholds() -> dict[str, float]:
    protocol = _json(ROOT / "audits/phase5b/repeatability_protocol.json")
    comparisons = protocol.get("comparisons")
    if not isinstance(comparisons, dict):
        raise PromptRAGContractError("repeatability protocol comparisons are invalid")
    return {name: float(value["minimum"]) for name, value in comparisons.items()}


def _safe_name(logical_id: str, expected_ids: set[str]) -> str:
    if logical_id not in expected_ids:
        raise PromptRAGContractError("logical ID is outside frozen plan")
    query_id, role = logical_id.split(":", 1)
    if query_id not in EXPECTED_QUERY_IDS or role not in {"primary", "replicate-1", "replicate-2"}:
        raise PromptRAGContractError("logical ID is malformed")
    return f"{query_id}__{role}"


def preflight(mode: str, *, resume_after_quota_reset: bool = False) -> dict[str, Any]:
    """Verify every frozen byte and request before credential access/client creation."""

    config = _json(CONFIG_PATH)
    config_hash = sha256_file(CONFIG_PATH)
    _verify_manifest(config_hash)
    if config.get("execution_authorized") is not True:
        raise ExecutionApprovalError("frozen config does not authorize executable contract")
    if config.get("status") != "offline_frozen_ready_pending_mode_specific_owner_approval":
        raise ExecutionApprovalError("frozen config status is not execution-ready")

    prompt_path = _canonical(config["prompt"]["path"])
    query_path = _canonical(config["benchmark_boundary"]["query_path"])
    chunk_path = _canonical(config["benchmark_boundary"]["chunk_path"])
    source_ranking_path = _canonical(config["architecture"]["source_ranking_path"])
    ranking_path = _canonical(config["architecture"]["sanitized_ranking_path"])
    trace_path = _canonical(config["request_contract"]["trace_selection_path"])
    token_path = _canonical(config["request_contract"]["request_hash_source_path"])
    for path, expected, label in (
        (prompt_path, config["prompt"]["sha256"], "prompt"),
        (query_path, config["benchmark_boundary"]["query_sha256"], "sanitized query-only input"),
        (chunk_path, config["benchmark_boundary"]["chunk_sha256"], "chunks"),
        (source_ranking_path, config["architecture"]["source_ranking_sha256"], "BM25 top-50"),
        (ranking_path, config["architecture"]["sanitized_ranking_sha256"], "sanitized BM25 ranking"),
        (trace_path, config["request_contract"]["trace_selection_sha256"], "trace selection"),
        (token_path, config["request_contract"]["request_hash_source_sha256"], "request hash source"),
    ):
        _verify_hash(path, expected, label)

    query_rows = _jsonl(query_path)
    query_ids = [row.get("query_id") for row in query_rows]
    if query_ids != list(EXPECTED_QUERY_IDS) or any(set(row) != {"query_id", "question"} for row in query_rows):
        raise PromptRAGContractError("query-only input must contain exact ordered IDs and fields")
    chunk_rows = _jsonl(chunk_path)
    if len(chunk_rows) != 140:
        raise PromptRAGContractError("frozen corpus must contain exactly 140 chunks")
    chunks: dict[str, str] = {}
    for row in chunk_rows:
        chunk_id, text = row.get("chunk_id"), row.get("text")
        if not isinstance(chunk_id, str) or not isinstance(text, str) or not text.strip() or chunk_id in chunks:
            raise PromptRAGContractError("frozen chunks contain duplicate/invalid ID or text")
        chunks[chunk_id] = text
    ranking_rows = _jsonl(ranking_path)
    if [row.get("query_id") for row in ranking_rows] != list(EXPECTED_QUERY_IDS):
        raise PromptRAGContractError("sanitized ranking query order differs from exact R5 IDs")
    rankings: dict[str, list[str]] = {}
    for row in ranking_rows:
        if set(row) != {"query_id", "chunk_ids"}:
            raise PromptRAGContractError("sanitized ranking contains forbidden or missing fields")
        ids = row["chunk_ids"]
        if not isinstance(ids, list) or len(ids) != 50 or len(set(ids)) != 50:
            raise PromptRAGContractError("every query must have exactly 50 unique candidates")
        if any(chunk_id not in chunks for chunk_id in ids):
            raise PromptRAGContractError("sanitized ranking references unknown chunk")
        rankings[row["query_id"]] = ids
    source_rows = _jsonl(source_ranking_path)
    source = {row.get("query_id"): [item.get("chunk_id") for item in row.get("ranking", [])] for row in source_rows}
    if source != rankings:
        raise PromptRAGContractError("sanitized ranking differs from frozen BM25 top-50")

    trace_artifact = _json(trace_path)
    trace_ids = [row.get("query_id") for row in trace_artifact.get("selected", [])]
    plan = build_logical_plan(mode, query_ids, trace_ids)
    plan_hash = _plan_sha256(plan)
    if plan_hash != config["request_contract"][f"{mode}_plan_sha256"]:
        raise PromptRAGContractError(f"{mode} request plan SHA-256 mismatch")
    prompt = prompt_path.read_text(encoding="utf-8")
    queries = {row["query_id"]: row for row in query_rows}
    token_audit = _json(token_path)
    expected_per_query = {row["query_id"]: row["request_sha256"] for row in token_audit["per_query"]}
    if set(expected_per_query) != set(EXPECTED_QUERY_IDS):
        raise PromptRAGContractError("request hash source lacks exact 34 query IDs")
    requests: dict[str, dict[str, Any]] = {}
    for query_id in EXPECTED_QUERY_IDS:
        request = build_request(
            query=queries[query_id],
            candidates=[{"chunk_id": chunk_id, "text": chunks[chunk_id]} for chunk_id in rankings[query_id]],
            system_instruction=prompt,
        )
        if sha256_text(stable_json(request)) != expected_per_query[query_id]:
            raise PromptRAGContractError(f"per-request payload hash mismatch: {query_id}")
        requests[query_id] = request

    trace_decision_hash: str | None = None
    established_model_version: str | None = None
    if mode == "full":
        raw_dir = OUTPUT_ROOT / "trace" / "raw"
        expected_trace_logical = {logical_id for logical_id, _query_id in build_logical_plan("trace", query_ids, trace_ids)}
        records = []
        for logical_id in sorted(expected_trace_logical):
            path = raw_dir / f"{_safe_name(logical_id, expected_trace_logical)}.json"
            records.append(_json(path))
        recomputed = recompute_trace_decision(
            records,
            trace_ids=trace_ids,
            expected_request_hashes=expected_per_query,
            thresholds=_trace_thresholds(),
        )
        saved_decision = _json(TRACE_DECISION_PATH)
        if recomputed != saved_decision or recomputed["status"] != "repeatability_gate_passed":
            raise ExecutionApprovalError("saved trace decision differs from independent recomputation")
        trace_decision_hash = sha256_file(TRACE_DECISION_PATH)
        established_model_version = recomputed["model_version"]

    _require_frozen_worktree(
        mode=mode,
        resume_after_quota_reset=resume_after_quota_reset,
        plan=plan,
    )
    git_commit, git_tree = _git_identity()
    _require_rotation_attestation(ROTATION_ATTESTATION_PATH)
    require_free_tier_owner_confirmation(
        FREE_TIER_CONFIRMATION_PATH, frozen_config_path=CONFIG_PATH
    )
    free_hash = sha256_file(FREE_TIER_CONFIRMATION_PATH)
    approval_path = TRACE_APPROVAL_PATH if mode == "trace" else FULL_APPROVAL_PATH
    require_mode_execution_approval(
        approval_path,
        mode=mode,
        frozen_config_sha256=config_hash,
        prompt_sha256=sha256_file(prompt_path),
        plan_sha256=plan_hash,
        free_tier_confirmation_sha256=free_hash,
        git_commit=git_commit,
        git_tree=git_tree,
        trace_decision_sha256=trace_decision_hash,
    )
    return {
        "config": config,
        "config_hash": config_hash,
        "established_model_version": established_model_version,
        "expected_per_query": expected_per_query,
        "plan": plan,
        "plan_hash": plan_hash,
        "prompt_hash": sha256_file(prompt_path),
        "query_ids": query_ids,
        "rankings": rankings,
        "requests": requests,
        "trace_decision_hash": trace_decision_hash,
    }


def _verify_saved_record(
    record: dict[str, Any], logical_id: str, request: dict[str, Any], candidate_ids: list[str]
) -> dict[str, Any]:
    if record.get("logical_request_id") != logical_id:
        raise PromptRAGContractError("saved response logical ID mismatch")
    request_hash = sha256_text(stable_json(request))
    if record.get("raw_request") != request or record.get("request_sha256") != request_hash:
        raise PromptRAGContractError("saved response request differs from frozen payload")
    validated = validate_response(record.get("raw_response"), expected_chunk_ids=candidate_ids)
    if record.get("ranking") != validated["ranking"]:
        raise PromptRAGContractError("saved response ranking differs from raw response")
    if record.get("response_sha256") != sha256_text(stable_json(validated["raw_response"])):
        raise PromptRAGContractError("saved response hash mismatch")
    return validated


def run(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[], Any] = create_client_from_environment,
) -> int:
    """Execute selected mode only after complete preflight and canonical locking."""

    if not args.require_free_tier_owner_confirmation:
        raise FreeTierConfirmationError("--require-free-tier-owner-confirmation is mandatory")
    frozen = preflight(
        args.mode, resume_after_quota_reset=args.resume_after_quota_reset
    )
    mode_root = OUTPUT_ROOT / args.mode
    ledger_path = mode_root / "control" / "ledger.json"
    lock_path = mode_root / "control" / "execution.lock"
    expected_logical = {logical_id for logical_id, _query_id in frozen["plan"]}
    logical_hashes = {
        logical_id: frozen["expected_per_query"][query_id]
        for logical_id, query_id in frozen["plan"]
    }
    with ExecutionLock(lock_path):
        ledger = NetworkAttemptLedger(
            ledger_path,
            mode=args.mode,
            frozen_config_sha256=frozen["config_hash"],
            prompt_sha256=frozen["prompt_hash"],
            plan_sha256=frozen["plan_hash"],
            query_ids=frozen["query_ids"],
            expected_logical_request_ids=[logical_id for logical_id, _query_id in frozen["plan"]],
            expected_request_hashes=logical_hashes,
            model=frozen["config"]["generation"]["model"],
            output_root=str(mode_root.relative_to(ROOT)),
            trace_decision_sha256=frozen["trace_decision_hash"],
            established_model_version=frozen["established_model_version"],
        )
        if ledger.state["quota_stop"] is not None:
            if not args.resume_after_quota_reset:
                raise QuotaExhaustedError("quota reset requires explicit owner-approved resume flag")
            ledger.require_resume_approval(RESUME_APPROVAL_PATH)

        # Credential is read only after every file, Git, approval, and ledger gate passes.
        client = client_factory()
        sender = make_live_sender(client)
        for logical_id, query_id in frozen["plan"]:
            safe = _safe_name(logical_id, expected_logical)
            raw_path = mode_root / "raw" / f"{safe}.json"
            request_state = ledger.state["requests"][logical_id]["state"]
            request = frozen["requests"][query_id]
            candidate_ids = frozen["rankings"][query_id]
            if raw_path.exists():
                record = _json(raw_path)
                validated = _verify_saved_record(record, logical_id, request, candidate_ids)
                if request_state == "response_received":
                    ledger.record_validated(logical_id, model_version=validated["model_version"])
                    ledger.record_committed(logical_id)
                elif request_state == "validated":
                    ledger.record_committed(logical_id)
                elif request_state != "committed":
                    raise NetworkAttemptCapError("saved response conflicts with durable ledger state")
                continue
            if request_state == "committed":
                raise NetworkAttemptCapError("committed ledger response artifact is missing")
            if request_state == "dispatched":
                raise NetworkAttemptCapError(
                    "ambiguous prior dispatch has no saved response; manual adjudication required"
                )
            if request_state in {"terminal_failure", "quota_stopped", "response_received", "validated"}:
                raise NetworkAttemptCapError(f"incomplete artifact for durable state {request_state}")

            request_hash = sha256_text(stable_json(request))

            def before_dispatch(attempt: int, dispatched_hash: str) -> None:
                if dispatched_hash != request_hash:
                    raise PromptRAGContractError("retry payload hash changed")
                ledger.before_dispatch(logical_id, dispatched_hash, attempt)

            def on_attempt(evidence: dict[str, Any]) -> None:
                ledger.record_attempt_evidence(logical_id, evidence)
                attempt_path = mode_root / "attempts" / safe / f"attempt-{evidence['attempt']:03d}.json"
                write_json(attempt_path, evidence, overwrite=False)

            try:
                record = execute_with_retry(
                    request,
                    expected_chunk_ids=candidate_ids,
                    expected_model_version=ledger.state["returned_model_version"],
                    send=sender,
                    before_dispatch=before_dispatch,
                    on_attempt=on_attempt,
                )
            except QuotaExhaustedError as exc:
                ledger.record_quota_stop(logical_id)
                write_json(
                    mode_root / "failures" / f"{safe}__quota-stop.json",
                    {
                        "attempt_history": getattr(exc, "attempt_history", []),
                        "error_class": "QuotaExhaustedError",
                        "http_status": 429,
                        "logical_request_id": logical_id,
                        "request_sha256": request_hash,
                    },
                    overwrite=False,
                )
                return 75
            except AttemptFailure as exc:
                failure = {
                    "attempt_history": exc.attempt_history,
                    "error_class": type(exc).__name__,
                    "logical_request_id": logical_id,
                    "request_sha256": request_hash,
                }
                if getattr(exc, "raw_response", None) is not None:
                    failure["invalid_raw_response"] = exc.raw_response
                write_json(
                    mode_root / "failures" / f"{safe}__terminal.json",
                    failure,
                    overwrite=False,
                )
                return 76

            record["logical_request_id"] = logical_id
            if raw_path.exists():
                raise NetworkAttemptCapError("valid response artifact already exists; refusing overwrite")
            write_json(raw_path, record, overwrite=False)
            ledger.record_validated(logical_id, model_version=record["model_version"])
            ledger.record_committed(logical_id)

        ledger.finalize_mode()
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=("trace", "full"), required=True)
    result.add_argument(
        "--require-free-tier-owner-confirmation", action="store_true", required=True
    )
    result.add_argument(
        "--resume-after-quota-reset",
        action="store_true",
        help="resume canonical ledger only after canonical owner approval exists",
    )
    return result


def main() -> int:
    try:
        return run(parser().parse_args())
    except (
        ExecutionApprovalError,
        FreeTierConfirmationError,
        NetworkAttemptCapError,
        PromptRAGContractError,
        QuotaExhaustedError,
    ) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
