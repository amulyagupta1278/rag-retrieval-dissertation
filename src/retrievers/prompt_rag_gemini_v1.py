"""Frozen offline contract for Gemini Prompt-RAG reranking.

No function runs a network request unless its caller explicitly invokes the
callable returned by :func:`make_live_sender`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import errors, local_tokenizer, types

from src.utils.atomic_io import stable_json, write_json
from src.utils.hashing import sha256_file, sha256_text


MODEL = "gemini-2.5-flash"
API_VERSION = "v1"
SDK_VERSION = "2.13.0"
CANDIDATE_N = 50
SCORE_MIN = 0
SCORE_MAX = 3
MAX_OUTPUT_TOKENS = 4096
TIMEOUT_MILLISECONDS = 120_000
TOTAL_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
TRANSIENT_HTTP_STATUSES = frozenset({408, 500, 502, 503, 504})
MODE_ATTEMPT_CAPS = {"trace": 24, "full": 26}


class PromptRAGContractError(ValueError):
    """Base class for fail-closed request or response contract errors."""


class TransientGeminiError(RuntimeError):
    """Retryable transport/provider error with no response-content validation."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TerminalGeminiError(RuntimeError):
    """Non-retryable provider error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class QuotaExhaustedError(RuntimeError):
    """Free-tier quota stop. Never retried during same execution."""

    status_code = 429


class NetworkAttemptCapError(RuntimeError):
    """Raised before dispatch when mode's frozen network cap is exhausted."""


class FreeTierConfirmationError(RuntimeError):
    """Raised when manual zero-charge owner attestation is absent or invalid."""


class ExecutionApprovalError(RuntimeError):
    """Raised when mode-specific owner approval does not bind exact execution."""


class AttemptFailure(PromptRAGContractError):
    """Terminal failure carrying sanitized, credential-free attempt evidence."""

    def __init__(
        self,
        message: str,
        *,
        attempt_history: list[dict[str, Any]],
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.attempt_history = copy.deepcopy(attempt_history)
        self.raw_response = copy.deepcopy(raw_response)


def build_response_schema(expected_chunk_ids: Iterable[str]) -> dict[str, Any]:
    """Build strict per-request schema with exact supplied chunk-ID enum."""

    chunk_ids = list(expected_chunk_ids)
    if len(chunk_ids) != CANDIDATE_N:
        raise PromptRAGContractError(f"exactly {CANDIDATE_N} candidate IDs required")
    if any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in chunk_ids):
        raise PromptRAGContractError("candidate IDs must be non-empty strings")
    if len(set(chunk_ids)) != CANDIDATE_N:
        raise PromptRAGContractError("candidate IDs must be unique")
    return {
        "type": "object",
        "properties": {
            "candidate_scores": {
                "type": "array",
                "minItems": CANDIDATE_N,
                "maxItems": CANDIDATE_N,
                "items": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string", "enum": sorted(chunk_ids)},
                        "score": {
                            "type": "integer",
                            "minimum": SCORE_MIN,
                            "maximum": SCORE_MAX,
                        },
                    },
                    "required": ["chunk_id", "score"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidate_scores"],
        "additionalProperties": False,
    }


def build_request(
    *,
    query: Mapping[str, Any],
    candidates: Iterable[Mapping[str, Any]],
    system_instruction: str,
) -> dict[str, Any]:
    """Build one stateless request containing one query and 50 candidates."""

    if set(query) != {"query_id", "question"}:
        raise PromptRAGContractError("query must contain only query_id and question")
    query_id = query["query_id"]
    question = query["question"]
    if not isinstance(query_id, str) or not query_id:
        raise PromptRAGContractError("query_id must be a non-empty string")
    if not isinstance(question, str) or not question.strip():
        raise PromptRAGContractError("question must be a non-empty string")
    if not isinstance(system_instruction, str) or not system_instruction.strip():
        raise PromptRAGContractError("system instruction must be non-empty")

    candidate_rows = [dict(candidate) for candidate in candidates]
    if len(candidate_rows) != CANDIDATE_N:
        raise PromptRAGContractError(f"exactly {CANDIDATE_N} candidates required")
    chunk_ids: list[str] = []
    for index, candidate in enumerate(candidate_rows):
        if set(candidate) != {"chunk_id", "text"}:
            raise PromptRAGContractError(
                f"candidate[{index}] must contain only chunk_id and text"
            )
        chunk_id = candidate["chunk_id"]
        text = candidate["text"]
        if not isinstance(chunk_id, str) or not chunk_id:
            raise PromptRAGContractError(f"candidate[{index}] chunk_id is invalid")
        if not isinstance(text, str) or not text.strip():
            raise PromptRAGContractError(f"candidate[{index}] text is invalid")
        chunk_ids.append(chunk_id)
    if len(set(chunk_ids)) != CANDIDATE_N:
        raise PromptRAGContractError("duplicate candidate chunk_id")

    contents = stable_json(
        {
            "candidates": candidate_rows,
            "query_id": query_id,
            "question": question,
        }
    )
    return {
        "model": MODEL,
        "contents": contents,
        "config": {
            "candidate_count": 1,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "response_mime_type": "application/json",
            "response_json_schema": build_response_schema(chunk_ids),
            "system_instruction": system_instruction,
            "temperature": 0,
            "thinking_config": {"thinking_budget": 0},
        },
    }


def count_request_tokens(
    request: Mapping[str, Any],
    *,
    tokenizer: local_tokenizer.LocalTokenizer,
) -> int:
    """Count contents, system instruction, and response schema locally.

    Live generation sends standard JSON Schema through ``responseJsonSchema``.
    google-genai 2.13.0's experimental local tokenizer omits that field from
    counting, so token accounting projects the identical schema through its
    supported OpenAPI ``responseSchema`` counting path. This changes no live
    request bytes and preserves conservative schema-token accounting.
    """

    config = request["config"]
    schema = types.Schema.model_validate(config["response_json_schema"])
    count_config = types.CountTokensConfig(
        system_instruction=config["system_instruction"],
        generation_config=types.GenerationConfig(response_schema=schema),
    )
    result = tokenizer.count_tokens(request["contents"], config=count_config)
    if result.total_tokens is None or result.total_tokens <= 0:
        raise PromptRAGContractError("local tokenizer returned no positive count")
    return result.total_tokens


def require_free_tier_owner_confirmation(
    confirmation_path: str | Path,
    *,
    frozen_config_path: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Require fresh owner attestation for active free-tier credential context.

    Billing status cannot be verified cryptographically without persisting a
    forbidden project or credential identifier. This gate therefore remains a
    deliberately explicit, short-lived owner attestation.
    """

    path = Path(confirmation_path)
    if not path.is_file():
        raise FreeTierConfirmationError("free-tier owner confirmation artifact is missing")
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreeTierConfirmationError("free-tier owner confirmation artifact is invalid") from exc
    required_keys = {
        "artifact_type",
        "attestation",
        "confirmed_at",
        "context_attestation",
        "frozen_config_sha256",
        "schema_version",
        "status",
    }
    if not isinstance(artifact, dict) or set(artifact) != required_keys:
        raise FreeTierConfirmationError("free-tier confirmation has unexpected fields")
    if artifact["artifact_type"] != "phase5b_free_tier_owner_confirmation":
        raise FreeTierConfirmationError("free-tier confirmation type mismatch")
    if artifact["status"] != "confirmed" or not isinstance(artifact["confirmed_at"], str):
        raise FreeTierConfirmationError("free-tier owner confirmation remains pending")
    try:
        confirmed_at = datetime.fromisoformat(artifact["confirmed_at"])
    except ValueError as exc:
        raise FreeTierConfirmationError("free-tier confirmation timestamp is invalid") from exc
    if confirmed_at.tzinfo is None:
        raise FreeTierConfirmationError("free-tier confirmation timestamp lacks timezone")
    current = now or datetime.now(timezone.utc)
    age_seconds = (current.astimezone(timezone.utc) - confirmed_at.astimezone(timezone.utc)).total_seconds()
    if age_seconds < 0 or age_seconds > 24 * 60 * 60:
        raise FreeTierConfirmationError(
            "free-tier confirmation must be renewed within 24 hours of execution"
        )
    expected_hash = sha256_file(frozen_config_path)
    if artifact["frozen_config_sha256"] != expected_hash:
        raise FreeTierConfirmationError("free-tier confirmation does not match frozen config")
    expected_attestation = {
        "google_ai_studio_plan": "Free",
        "linked_billing_account": False,
        "monetary_charge_authorized": False,
    }
    if artifact["attestation"] != expected_attestation:
        raise FreeTierConfirmationError("free-tier attestation is incomplete")
    expected_context = {
        "active_execution_environment_confirmed": True,
        "credential_or_environment_changed_since_confirmation": False,
        "reconfirmation_required_after_any_change": True,
        "scope": "current process environment and active GEMINI_API_KEY context",
    }
    if artifact["context_attestation"] != expected_context:
        raise FreeTierConfirmationError("active credential-context attestation is incomplete")
    return artifact


def require_mode_execution_approval(
    approval_path: str | Path,
    *,
    mode: str,
    frozen_config_sha256: str,
    prompt_sha256: str,
    plan_sha256: str,
    free_tier_confirmation_sha256: str,
    git_commit: str,
    git_tree: str,
    trace_decision_sha256: str | None,
) -> dict[str, Any]:
    """Require strict mode-specific approval bound to immutable execution inputs."""

    if mode not in MODE_ATTEMPT_CAPS:
        raise ExecutionApprovalError(f"unsupported execution mode: {mode}")
    path = Path(approval_path)
    if not path.is_file():
        raise ExecutionApprovalError(f"{mode} execution approval artifact is missing")
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionApprovalError(f"{mode} execution approval artifact is invalid") from exc
    expected_keys = {
        "approved",
        "approved_at",
        "artifact_type",
        "free_tier_confirmation_sha256",
        "frozen_config_sha256",
        "git_commit",
        "git_tree",
        "mode",
        "plan_sha256",
        "prompt_sha256",
        "schema_version",
        "trace_decision_sha256",
    }
    if not isinstance(artifact, dict) or set(artifact) != expected_keys:
        raise ExecutionApprovalError(f"{mode} execution approval has unexpected fields")
    expected = {
        "approved": True,
        "approved_at": artifact.get("approved_at"),
        "artifact_type": f"phase5b_{mode}_execution_approval",
        "free_tier_confirmation_sha256": free_tier_confirmation_sha256,
        "frozen_config_sha256": frozen_config_sha256,
        "git_commit": git_commit,
        "git_tree": git_tree,
        "mode": mode,
        "plan_sha256": plan_sha256,
        "prompt_sha256": prompt_sha256,
        "schema_version": 1,
        "trace_decision_sha256": trace_decision_sha256,
    }
    if not isinstance(artifact.get("approved_at"), str) or artifact != expected:
        raise ExecutionApprovalError(f"{mode} execution approval does not match frozen execution")
    if mode == "trace" and trace_decision_sha256 is not None:
        raise ExecutionApprovalError("trace approval cannot bind a trace decision")
    if mode == "full" and trace_decision_sha256 is None:
        raise ExecutionApprovalError("full approval must bind verified trace decision")
    return artifact


def require_control_approval(
    approval_path: str | Path,
    *,
    artifact_type: str,
    frozen_config_sha256: str,
    mode: str,
    checkpoint_sha256: str,
) -> dict[str, Any]:
    """Validate full-run or post-quota-reset owner approval without identifiers."""

    path = Path(approval_path)
    if not path.is_file():
        raise FreeTierConfirmationError(f"{artifact_type} artifact is missing")
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreeTierConfirmationError(f"{artifact_type} artifact is invalid") from exc
    expected = {
        "artifact_type": artifact_type,
        "approved": True,
        "approved_at": artifact.get("approved_at"),
        "checkpoint_sha256": checkpoint_sha256,
        "frozen_config_sha256": frozen_config_sha256,
        "mode": mode,
        "schema_version": 1,
    }
    if not isinstance(artifact.get("approved_at"), str) or artifact != expected:
        raise FreeTierConfirmationError(f"{artifact_type} does not match frozen execution")
    return artifact


class ExecutionLock:
    """Process-safe exclusive lock; stale locks require explicit owner inspection."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fd: int | None = None

    def __enter__(self) -> "ExecutionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise NetworkAttemptCapError("another runner holds canonical execution lock") from None
        os.write(self._fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(self._fd)
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self.path.unlink(missing_ok=True)


class NetworkAttemptLedger:
    """Strict config/plan-bound durable request ledger."""

    _REQUEST_STATES = {
        "planned",
        "dispatched",
        "retry_pending",
        "response_received",
        "validated",
        "committed",
        "terminal_failure",
        "quota_stopped",
    }

    def __init__(
        self,
        path: str | Path,
        *,
        mode: str,
        frozen_config_sha256: str,
        prompt_sha256: str,
        plan_sha256: str,
        query_ids: Iterable[str],
        expected_logical_request_ids: Iterable[str],
        expected_request_hashes: Mapping[str, str],
        model: str,
        output_root: str,
        trace_decision_sha256: str | None = None,
        established_model_version: str | None = None,
    ) -> None:
        if mode not in MODE_ATTEMPT_CAPS:
            raise ValueError(f"unknown execution mode: {mode}")
        self.path = Path(path)
        self.mode = mode
        self.cap = MODE_ATTEMPT_CAPS[mode]
        logical_ids = list(expected_logical_request_ids)
        ids = list(query_ids)
        request_hashes = dict(expected_request_hashes)
        if not logical_ids or len(logical_ids) != len(set(logical_ids)):
            raise NetworkAttemptCapError("logical request plan is empty or duplicated")
        if len(ids) != len(set(ids)):
            raise NetworkAttemptCapError("ledger query IDs are duplicated")
        if set(request_hashes) != set(logical_ids):
            raise NetworkAttemptCapError("ledger request hashes do not match logical plan")
        self.bindings = {
            "frozen_config_sha256": frozen_config_sha256,
            "mode": mode,
            "model": model,
            "output_root": output_root,
            "plan_sha256": plan_sha256,
            "prompt_sha256": prompt_sha256,
            "query_ids": ids,
            "trace_decision_sha256": trace_decision_sha256,
        }
        self.expected_logical_ids = logical_ids
        self.expected_request_hashes = request_hashes
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise NetworkAttemptCapError("canonical ledger is malformed") from exc
            self._validate_state()
        else:
            requests = {
                logical_id: {
                    "attempts": [],
                    "request_sha256": request_hashes[logical_id],
                    "state": "planned",
                }
                for logical_id in logical_ids
            }
            self.state = {
                "attempted_network_request_n": 0,
                "bindings": self.bindings,
                "completed_logical_request_ids": [],
                "network_attempt_cap": self.cap,
                "monetary_cost_usd": None,
                "quota_stop": None,
                "requests": requests,
                "returned_model_version": established_model_version,
                "schema_version": 2,
                "status": "ready",
            }
            self._write()

    def _validate_state(self) -> None:
        required = {
            "attempted_network_request_n",
            "bindings",
            "completed_logical_request_ids",
            "network_attempt_cap",
            "monetary_cost_usd",
            "quota_stop",
            "requests",
            "returned_model_version",
            "schema_version",
            "status",
        }
        if not isinstance(self.state, dict) or set(self.state) != required:
            raise NetworkAttemptCapError("canonical ledger schema mismatch")
        if self.state["schema_version"] != 2 or self.state["bindings"] != self.bindings:
            raise NetworkAttemptCapError("canonical ledger binding mismatch")
        if self.state["network_attempt_cap"] != self.cap:
            raise NetworkAttemptCapError("canonical ledger attempt cap mismatch")
        requests = self.state["requests"]
        if not isinstance(requests, dict) or set(requests) != set(self.expected_logical_ids):
            raise NetworkAttemptCapError("canonical ledger request plan mismatch")
        attempt_total = 0
        committed: list[str] = []
        for logical_id in self.expected_logical_ids:
            row = requests[logical_id]
            if not isinstance(row, dict) or set(row) != {"attempts", "request_sha256", "state"}:
                raise NetworkAttemptCapError("canonical ledger request schema mismatch")
            if row["request_sha256"] != self.expected_request_hashes[logical_id]:
                raise NetworkAttemptCapError("canonical ledger request hash mismatch")
            if row["state"] not in self._REQUEST_STATES or not isinstance(row["attempts"], list):
                raise NetworkAttemptCapError("canonical ledger request state is invalid")
            attempt_total += len(row["attempts"])
            if row["state"] == "committed":
                committed.append(logical_id)
        attempted = self.state["attempted_network_request_n"]
        if not isinstance(attempted, int) or attempted != attempt_total or not 0 <= attempted <= self.cap:
            raise NetworkAttemptCapError("canonical ledger attempt count is invalid")
        completed = self.state["completed_logical_request_ids"]
        if completed != sorted(committed) or len(completed) != len(set(completed)):
            raise NetworkAttemptCapError("canonical ledger completed IDs are forged")

    def _write(self) -> None:
        write_json(self.path, self.state, overwrite=self.path.exists())

    @property
    def attempted(self) -> int:
        return int(self.state["attempted_network_request_n"])

    def require_resume_approval(self, approval_path: str | Path) -> None:
        """Clear quota stop only after owner confirms reset for exact ledger bytes."""

        if self.state.get("quota_stop") is None:
            return
        require_control_approval(
            approval_path,
            artifact_type="phase5b_quota_reset_resume_approval",
            frozen_config_sha256=self.bindings["frozen_config_sha256"],
            mode=self.mode,
            checkpoint_sha256=sha256_file(self.path),
        )
        logical_id = self.state["quota_stop"]["logical_request_id"]
        request = self.state["requests"][logical_id]
        if request["state"] != "quota_stopped":
            raise NetworkAttemptCapError("quota-stop ledger state is inconsistent")
        request["state"] = "retry_pending"
        self.state["quota_stop"] = None
        self.state["status"] = "ready_after_owner_approved_quota_reset"
        self._write()

    def before_dispatch(
        self, logical_request_id: str, request_sha256: str, attempt_number: int = 1
    ) -> None:
        """Consume one attempt durably before network dispatch."""

        if self.state["quota_stop"] is not None:
            raise QuotaExhaustedError("quota stop requires owner-approved reset")
        if logical_request_id not in self.state["requests"]:
            raise NetworkAttemptCapError("logical request is outside frozen plan")
        request = self.state["requests"][logical_request_id]
        if request["request_sha256"] != request_sha256:
            raise NetworkAttemptCapError("dispatched request hash differs from frozen plan")
        if request["state"] not in {"planned", "retry_pending"}:
            raise NetworkAttemptCapError(
                f"request cannot dispatch from durable state {request['state']}"
            )
        if attempt_number != len(request["attempts"]) + 1:
            raise NetworkAttemptCapError("attempt number does not continue durable history")
        if self.attempted >= self.cap:
            raise NetworkAttemptCapError(f"{self.mode} network attempt cap exhausted: {self.cap}")
        request["attempts"].append(
            {
                "attempt": attempt_number,
                "request_sha256": request_sha256,
                "state": "dispatched",
            }
        )
        request["state"] = "dispatched"
        self.state["attempted_network_request_n"] = self.attempted + 1
        self.state["status"] = "attempt_counted_before_dispatch"
        self._write()

    def record_attempt_evidence(self, logical_request_id: str, evidence: Mapping[str, Any]) -> None:
        """Persist complete sanitized attempt evidence and next durable state."""

        request = self.state["requests"].get(logical_request_id)
        if not request or request["state"] != "dispatched" or not request["attempts"]:
            raise NetworkAttemptCapError("attempt evidence has no matching dispatch")
        if evidence.get("attempt") != len(request["attempts"]):
            raise NetworkAttemptCapError("attempt evidence number mismatch")
        request["attempts"][-1] = copy.deepcopy(dict(evidence))
        decision = evidence.get("retry_decision")
        if decision == "retry":
            request["state"] = "retry_pending"
        elif decision == "quota_stop":
            request["state"] = "quota_stopped"
        elif decision == "terminal":
            request["state"] = "terminal_failure"
        elif decision == "validate":
            request["state"] = "response_received"
        else:
            raise NetworkAttemptCapError("attempt evidence retry decision is invalid")
        self._write()

    def record_validated(self, logical_request_id: str, *, model_version: str) -> None:
        """Advance response_received to validated after strict response validation."""

        request = self.state["requests"].get(logical_request_id)
        if not request or request["state"] != "response_received":
            raise NetworkAttemptCapError("validated response lacks response_received state")
        frozen = self.state["returned_model_version"]
        if frozen is not None and model_version != frozen:
            raise PromptRAGContractError(
                f"modelVersion mismatch: expected {frozen}, got {model_version}"
            )
        self.state["returned_model_version"] = model_version
        request["state"] = "validated"
        self._write()

    def record_committed(self, logical_request_id: str) -> None:
        """Commit one validated artifact; valid primary output is never overwritten."""

        request = self.state["requests"].get(logical_request_id)
        if not request or request["state"] != "validated":
            raise NetworkAttemptCapError("commit requires validated durable state")
        request["state"] = "committed"
        completed = self.state["completed_logical_request_ids"]
        completed.append(logical_request_id)
        completed.sort()
        self.state["status"] = "request_committed"
        self._write()

    def record_success(self, logical_request_id: str, *, model_version: str) -> None:
        """Compatibility helper for tests using explicit response_received state."""

        self.record_validated(logical_request_id, model_version=model_version)
        self.record_committed(logical_request_id)

    def record_quota_stop(self, logical_request_id: str) -> None:
        """Persist sanitized 429 status without provider body."""

        request = self.state["requests"].get(logical_request_id)
        if not request or request["state"] != "quota_stopped":
            raise NetworkAttemptCapError("quota stop lacks matching attempt evidence")
        self.state["quota_stop"] = {
            "error_class": "QuotaExhaustedError",
            "http_status": 429,
            "logical_request_id": logical_request_id,
        }
        self.state["status"] = "quota_stopped"
        self._write()

    def finalize_mode(self) -> None:
        """Complete mode only when every planned request is durably committed."""

        if self.state["completed_logical_request_ids"] != sorted(self.expected_logical_ids):
            raise NetworkAttemptCapError("cannot finalize incomplete logical request plan")
        self.state["status"] = f"{self.mode}_network_scope_complete"
        self.state["monetary_cost_usd"] = 0.0
        self._write()


def parse_scored_response(
    raw_text: str, expected_chunk_ids: Iterable[str]
) -> list[dict[str, Any]]:
    """Parse strict 0..3 integer scores and apply deterministic ranking."""

    expected = list(expected_chunk_ids)
    if len(expected) != CANDIDATE_N or len(set(expected)) != CANDIDATE_N:
        raise PromptRAGContractError("expected candidate set must contain 50 unique IDs")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PromptRAGContractError(f"malformed JSON: {exc.msg}") from exc
    if not isinstance(payload, dict) or set(payload) != {"candidate_scores"}:
        raise PromptRAGContractError("response must contain only candidate_scores")
    rows = payload["candidate_scores"]
    if not isinstance(rows, list) or len(rows) != CANDIDATE_N:
        raise PromptRAGContractError("response must contain exactly 50 scores")

    scores: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"chunk_id", "score"}:
            raise PromptRAGContractError(
                f"candidate_scores[{index}] must contain only chunk_id and score"
            )
        chunk_id = row["chunk_id"]
        score = row["score"]
        if not isinstance(chunk_id, str) or not chunk_id:
            raise PromptRAGContractError(f"candidate_scores[{index}] chunk_id is invalid")
        if chunk_id in scores:
            raise PromptRAGContractError(f"duplicate response chunk_id: {chunk_id}")
        if isinstance(score, bool) or not isinstance(score, int):
            raise PromptRAGContractError(f"score for {chunk_id} must be an integer")
        if not SCORE_MIN <= score <= SCORE_MAX:
            raise PromptRAGContractError(f"score for {chunk_id} is outside 0..3")
        scores[chunk_id] = score

    expected_set = set(expected)
    actual_set = set(scores)
    if actual_set != expected_set:
        missing = sorted(expected_set - actual_set)
        extra = sorted(actual_set - expected_set)
        raise PromptRAGContractError(
            f"response candidate set mismatch; missing={missing}, extra={extra}"
        )
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"chunk_id": chunk_id, "score": score, "rank": rank}
        for rank, (chunk_id, score) in enumerate(ordered, start=1)
    ]


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    raise PromptRAGContractError("response is not serializable")


def _field(mapping: Mapping[str, Any], snake: str, camel: str) -> Any:
    return mapping.get(camel, mapping.get(snake))


def validate_response(
    response: Any,
    *,
    expected_chunk_ids: Iterable[str],
    expected_model_version: str | None = None,
) -> dict[str, Any]:
    """Reject blocked, truncated, refused, tool-bearing, or mismatched output."""

    raw = _mapping(response)
    response_id = _field(raw, "response_id", "responseId")
    model_version = _field(raw, "model_version", "modelVersion")
    if not isinstance(response_id, str) or not response_id:
        raise PromptRAGContractError("missing responseId")
    if not isinstance(model_version, str) or not model_version:
        raise PromptRAGContractError("missing modelVersion")
    if expected_model_version is not None and model_version != expected_model_version:
        raise PromptRAGContractError(
            f"modelVersion mismatch: expected {expected_model_version}, got {model_version}"
        )

    feedback = _field(raw, "prompt_feedback", "promptFeedback") or {}
    block_reason = _field(feedback, "block_reason", "blockReason")
    if block_reason not in (None, "", "BLOCK_REASON_UNSPECIFIED"):
        raise PromptRAGContractError(f"prompt blocked: {block_reason}")

    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise PromptRAGContractError("response must contain exactly one candidate")
    candidate = candidates[0]
    finish_reason = _field(candidate, "finish_reason", "finishReason")
    if finish_reason != "STOP":
        raise PromptRAGContractError(f"non-complete finish reason: {finish_reason}")
    content = candidate.get("content") or {}
    parts = content.get("parts")
    if not isinstance(parts, list) or len(parts) != 1:
        raise PromptRAGContractError("response must contain exactly one text part")
    part = parts[0]
    if not isinstance(part, Mapping) or set(part) != {"text"}:
        raise PromptRAGContractError("unexpected tool or non-text response part")
    text = part["text"]
    if not isinstance(text, str) or not text.strip():
        raise PromptRAGContractError("incomplete empty response text")
    ranking = parse_scored_response(text, expected_chunk_ids)
    return {
        "model_version": model_version,
        "ranking": ranking,
        "raw_response": raw,
        "response_id": response_id,
    }


def _status_code(exc: BaseException) -> int | None:
    for name in ("code", "status_code"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            return value
    return None


def create_client_from_environment(
    *,
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[..., Any] = genai.Client,
) -> Any:
    """Create stable-v1 client from environment without logging credential."""

    enforce_sdk_version()
    environment = os.environ if environ is None else environ
    api_key = environment.get("GEMINI_API_KEY", "")
    if not api_key:
        raise TerminalGeminiError("GEMINI_API_KEY is missing")
    return client_factory(
        api_key=api_key,
        http_options=types.HttpOptions(
            api_version=API_VERSION,
            timeout=TIMEOUT_MILLISECONDS,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def enforce_sdk_version() -> None:
    """Reject runtime SDK drift from exact frozen install contract."""

    try:
        installed = metadata.version("google-genai")
    except metadata.PackageNotFoundError:
        raise TerminalGeminiError("required google-genai SDK is not installed") from None
    if installed != SDK_VERSION:
        raise TerminalGeminiError(
            f"google-genai version mismatch: expected {SDK_VERSION}, got {installed}"
        )


def make_live_sender(client: Any) -> Callable[[dict[str, Any]], Any]:
    """Return explicit live sender. Creating it performs no network request."""

    def send(request: dict[str, Any]) -> Any:
        try:
            return client.models.generate_content(
                model=request["model"],
                contents=request["contents"],
                config=types.GenerateContentConfig.model_validate(request["config"]),
            )
        except errors.APIError as exc:
            status = _status_code(exc)
            if status == 429:
                raise QuotaExhaustedError("Gemini free-tier quota exhausted") from None
            if status in TRANSIENT_HTTP_STATUSES:
                raise TransientGeminiError(
                    "transient Gemini API error", status_code=status
                ) from None
            raise TerminalGeminiError(
                f"terminal Gemini API error status={status}", status_code=status
            ) from None
        except (httpx.TimeoutException, TimeoutError) as exc:
            del exc
            raise TransientGeminiError("transient Gemini timeout", status_code=408) from None
        except (httpx.ConnectError, ConnectionError) as exc:
            del exc
            raise TransientGeminiError("transient Gemini connection error") from None

    return send


def execute_with_retry(
    request: Mapping[str, Any],
    *,
    expected_chunk_ids: Iterable[str],
    send: Callable[[dict[str, Any]], Any],
    before_dispatch: Callable[[int, str], None] | None = None,
    on_attempt: Callable[[dict[str, Any]], None] | None = None,
    expected_model_version: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Execute identical retries and retain sanitized evidence for every attempt."""

    serialized_request = stable_json(request)
    request_hash = sha256_text(serialized_request)
    attempts: list[dict[str, Any]] = []
    for attempt_number in range(1, TOTAL_ATTEMPTS + 1):
        started = now().isoformat()
        if before_dispatch is None:
            raise NetworkAttemptCapError("pre-dispatch network counter is required")
        before_dispatch(attempt_number, request_hash)
        try:
            response = send(json.loads(serialized_request))
        except TransientGeminiError as exc:
            evidence = {
                "attempt": attempt_number,
                "ended_at": now().isoformat(),
                "error_class": type(exc).__name__,
                "finish_reason": None,
                "http_status": exc.status_code,
                "model_version": None,
                "request_sha256": request_hash,
                "response_id_sha256": None,
                "response_sha256": None,
                "retry_decision": "retry" if attempt_number < TOTAL_ATTEMPTS else "terminal",
                "schema_failure_classification": None,
                "started_at": started,
                "status": "transport_failure",
            }
            attempts.append(evidence)
            if on_attempt is not None:
                on_attempt(evidence)
            if attempt_number == TOTAL_ATTEMPTS:
                failure = AttemptFailure(
                    "transient Gemini failure exhausted bounded retries",
                    attempt_history=attempts,
                )
                raise failure from None
            sleep(BACKOFF_SECONDS[attempt_number - 1])
            continue
        except QuotaExhaustedError as exc:
            evidence = {
                "attempt": attempt_number,
                "ended_at": now().isoformat(),
                "error_class": type(exc).__name__,
                "finish_reason": None,
                "http_status": 429,
                "model_version": None,
                "request_sha256": request_hash,
                "response_id_sha256": None,
                "response_sha256": None,
                "retry_decision": "quota_stop",
                "schema_failure_classification": None,
                "started_at": started,
                "status": "quota_stopped",
            }
            attempts.append(evidence)
            if on_attempt is not None:
                on_attempt(evidence)
            exc.attempt_history = copy.deepcopy(attempts)
            raise exc from None
        except TerminalGeminiError as exc:
            evidence = {
                "attempt": attempt_number,
                "ended_at": now().isoformat(),
                "error_class": type(exc).__name__,
                "finish_reason": None,
                "http_status": _status_code(exc),
                "model_version": None,
                "request_sha256": request_hash,
                "response_id_sha256": None,
                "response_sha256": None,
                "retry_decision": "terminal",
                "schema_failure_classification": None,
                "started_at": started,
                "status": "terminal_provider_failure",
            }
            attempts.append(evidence)
            if on_attempt is not None:
                on_attempt(evidence)
            failure = AttemptFailure(
                "terminal Gemini provider failure", attempt_history=attempts
            )
            raise failure from None

        try:
            raw_response = _mapping(response)
            raw_response_json = stable_json(raw_response)
        except PromptRAGContractError:
            raw_response = {}
            raw_response_json = stable_json(raw_response)
        response_hash = sha256_text(raw_response_json)
        response_id = _field(raw_response, "response_id", "responseId")
        model_version = _field(raw_response, "model_version", "modelVersion")
        candidates = raw_response.get("candidates")
        candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
        finish_reason = _field(candidate, "finish_reason", "finishReason") if isinstance(candidate, Mapping) else None
        try:
            validated = validate_response(
                response,
                expected_chunk_ids=expected_chunk_ids,
                expected_model_version=expected_model_version,
            )
        except PromptRAGContractError as exc:
            evidence = {
                "attempt": attempt_number,
                "ended_at": now().isoformat(),
                "error_class": type(exc).__name__,
                "finish_reason": finish_reason if isinstance(finish_reason, str) else None,
                "http_status": None,
                "model_version": model_version if isinstance(model_version, str) else None,
                "request_sha256": request_hash,
                "response_id_sha256": sha256_text(response_id) if isinstance(response_id, str) else None,
                "response_sha256": response_hash,
                "retry_decision": "terminal",
                "schema_failure_classification": str(exc).split(":", 1)[0],
                "started_at": started,
                "status": "response_contract_failure",
            }
            attempts.append(evidence)
            if on_attempt is not None:
                on_attempt(evidence)
            failure = AttemptFailure(
                "Gemini response failed frozen contract",
                attempt_history=attempts,
                raw_response=raw_response,
            )
            raise failure from None

        evidence = {
            "attempt": attempt_number,
            "ended_at": now().isoformat(),
            "error_class": None,
            "finish_reason": finish_reason,
            "http_status": 200,
            "model_version": validated["model_version"],
            "request_sha256": request_hash,
            "response_id_sha256": sha256_text(validated["response_id"]),
            "response_sha256": response_hash,
            "retry_decision": "validate",
            "schema_failure_classification": None,
            "started_at": started,
            "status": "valid",
        }
        attempts.append(evidence)
        if on_attempt is not None:
            on_attempt(evidence)
        return {
            "attempts": attempts,
            "model_version": validated["model_version"],
            "ranking": validated["ranking"],
            "raw_request": json.loads(serialized_request),
            "raw_response": validated["raw_response"],
            "request_sha256": request_hash,
            "response_id": validated["response_id"],
            "response_sha256": response_hash,
        }
    raise AssertionError("unreachable retry state")


def select_trace_query_ids(query_ids: Iterable[str], *, seed: str = "42") -> list[str]:
    """Select eight IDs using SHA-256(seed + NUL + query_id), smallest first."""

    ids = list(query_ids)
    if len(ids) != 34 or len(set(ids)) != 34:
        raise PromptRAGContractError("trace selection requires 34 unique query IDs")
    if any(not isinstance(query_id, str) or not query_id for query_id in ids):
        raise PromptRAGContractError("query IDs must be non-empty strings")
    scored = [
        (hashlib.sha256(f"{seed}\0{query_id}".encode("utf-8")).hexdigest(), query_id)
        for query_id in ids
    ]
    return [query_id for _, query_id in sorted(scored)[:8]]


def _pearson(left: list[float], right: list[float]) -> float:
    """Return Pearson correlation, defining equal identical constants as one."""

    if len(left) != len(right) or not left:
        raise PromptRAGContractError("correlation vectors must have equal nonzero length")
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_ss = sum((a - left_mean) ** 2 for a in left)
    right_ss = sum((b - right_mean) ** 2 for b in right)
    if left_ss == 0 or right_ss == 0:
        return 1.0 if left == right else 0.0
    return numerator / (left_ss * right_ss) ** 0.5


def _kendall_tau_b(left: list[int], right: list[int]) -> float:
    """Return Kendall tau-b over aligned score vectors with ties retained."""

    if len(left) != len(right) or len(left) < 2:
        raise PromptRAGContractError("Kendall vectors must have equal length >= 2")
    concordant = discordant = ties_left = ties_right = 0
    for first in range(len(left) - 1):
        for second in range(first + 1, len(left)):
            delta_left = left[first] - left[second]
            delta_right = right[first] - right[second]
            if delta_left == 0 and delta_right == 0:
                continue
            if delta_left == 0:
                ties_left += 1
            elif delta_right == 0:
                ties_right += 1
            elif delta_left * delta_right > 0:
                concordant += 1
            else:
                discordant += 1
    denominator = ((concordant + discordant + ties_left) * (concordant + discordant + ties_right)) ** 0.5
    if denominator == 0:
        return 1.0 if left == right else 0.0
    return (concordant - discordant) / denominator


def repeatability_comparison(
    first: list[dict[str, Any]], second: list[dict[str, Any]]
) -> dict[str, float]:
    """Compute frozen repeatability panel for two complete 50-candidate rankings."""

    if len(first) != CANDIDATE_N or len(second) != CANDIDATE_N:
        raise PromptRAGContractError("repeatability rankings must each contain 50 rows")
    first_by_id = {row["chunk_id"]: row for row in first}
    second_by_id = {row["chunk_id"]: row for row in second}
    if len(first_by_id) != CANDIDATE_N or set(first_by_id) != set(second_by_id):
        raise PromptRAGContractError("repeatability candidate sets differ or duplicate")
    ids = sorted(first_by_id)
    first_scores = [int(first_by_id[chunk_id]["score"]) for chunk_id in ids]
    second_scores = [int(second_by_id[chunk_id]["score"]) for chunk_id in ids]
    first_positions = [int(first_by_id[chunk_id]["rank"]) for chunk_id in ids]
    second_positions = [int(second_by_id[chunk_id]["rank"]) for chunk_id in ids]
    first_top = {row["chunk_id"] for row in first if int(row["rank"]) <= 10}
    second_top = {row["chunk_id"] for row in second if int(row["rank"]) <= 10}
    return {
        "candidate_score_agreement": sum(a == b for a, b in zip(first_scores, second_scores)) / CANDIDATE_N,
        "kendall_tau_b": _kendall_tau_b(first_scores, second_scores),
        "ranking_position_agreement": sum(a == b for a, b in zip(first_positions, second_positions)) / CANDIDATE_N,
        "spearman_rho": _pearson([float(value) for value in first_positions], [float(value) for value in second_positions]),
        "top_10_overlap": len(first_top & second_top) / 10,
    }


def recompute_trace_decision(
    records: Iterable[Mapping[str, Any]],
    *,
    trace_ids: Iterable[str],
    expected_request_hashes: Mapping[str, str],
    thresholds: Mapping[str, float],
) -> dict[str, Any]:
    """Independently validate 24 raw trace responses and recompute gate decision."""

    trace = list(trace_ids)
    if len(trace) != 8 or len(set(trace)) != 8:
        raise PromptRAGContractError("trace decision requires eight unique frozen IDs")
    roles = ("primary", "replicate-1", "replicate-2")
    expected_logical = {f"{query_id}:{role}" for query_id in trace for role in roles}
    rows: dict[str, dict[str, Any]] = {}
    model_versions: set[str] = set()
    for source in records:
        row = copy.deepcopy(dict(source))
        logical_id = row.get("logical_request_id")
        if logical_id not in expected_logical or logical_id in rows:
            raise PromptRAGContractError("trace records contain missing, extra, or duplicate logical ID")
        query_id, _role = str(logical_id).split(":", 1)
        request = row.get("raw_request")
        if not isinstance(request, dict):
            raise PromptRAGContractError("trace record lacks raw request")
        request_hash = sha256_text(stable_json(request))
        if request_hash != expected_request_hashes.get(query_id) or row.get("request_sha256") != request_hash:
            raise PromptRAGContractError("trace request hash differs from frozen per-query payload")
        try:
            contents = json.loads(request["contents"])
            candidate_ids = [item["chunk_id"] for item in contents["candidates"]]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PromptRAGContractError("trace request candidate contract is malformed") from exc
        validated = validate_response(
            row.get("raw_response"), expected_chunk_ids=candidate_ids
        )
        if row.get("response_sha256") != sha256_text(stable_json(validated["raw_response"])):
            raise PromptRAGContractError("trace response hash mismatch")
        if row.get("ranking") != validated["ranking"]:
            raise PromptRAGContractError("trace saved ranking differs from raw response")
        if row.get("model_version") != validated["model_version"]:
            raise PromptRAGContractError("trace saved modelVersion differs from raw response")
        model_versions.add(validated["model_version"])
        rows[str(logical_id)] = row
    if set(rows) != expected_logical:
        raise PromptRAGContractError("trace requires exactly three executions for each frozen ID")
    if len(model_versions) != 1:
        raise PromptRAGContractError("trace modelVersion differs across requests")
    required_metrics = {
        "candidate_score_agreement",
        "kendall_tau_b",
        "ranking_position_agreement",
        "spearman_rho",
        "top_10_overlap",
    }
    if set(thresholds) != required_metrics:
        raise PromptRAGContractError("repeatability threshold set differs from frozen protocol")
    comparisons: list[dict[str, Any]] = []
    all_pass = True
    for query_id in trace:
        logical_ids = [f"{query_id}:{role}" for role in roles]
        for left_index, right_index in ((0, 1), (0, 2), (1, 2)):
            metrics = repeatability_comparison(
                rows[logical_ids[left_index]]["ranking"],
                rows[logical_ids[right_index]]["ranking"],
            )
            passed = all(metrics[name] >= float(thresholds[name]) for name in required_metrics)
            all_pass = all_pass and passed
            comparisons.append(
                {
                    "left_logical_request_id": logical_ids[left_index],
                    "metrics": metrics,
                    "passed": passed,
                    "query_id": query_id,
                    "right_logical_request_id": logical_ids[right_index],
                }
            )
    return {
        "comparison_n": len(comparisons),
        "comparisons": comparisons,
        "first_valid_execution_role": "primary",
        "model_version": next(iter(model_versions)),
        "schema_version": 1,
        "selected_query_ids": trace,
        "status": "repeatability_gate_passed" if all_pass else "repeatability_gate_failed",
        "terminal_failure_n": 0,
        "thresholds": dict(sorted(thresholds.items())),
        "trace_record_n": len(rows),
    }
