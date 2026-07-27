"""Phase 7 response, failure, ledger, and idempotence contracts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


FAILURE_CLASSES = {
    "missing_response",
    "timeout",
    "ambiguous_dispatch",
    "non_2xx",
    "refusal",
    "safety_block",
    "truncation",
    "malformed_structured_output",
    "model_drift",
    "missing_usage",
    "invalid_citation_ids",
    "unsupported_citations",
    "duplicate_response",
    "context_mismatch",
}


class Phase7ContractError(ValueError):
    """Raised when a generated record violates a frozen contract."""


class Phase7ProviderFailure(RuntimeError):
    """Explicit provider-neutral failure carrying a frozen failure class."""

    def __init__(self, failure_class: str) -> None:
        if failure_class not in FAILURE_CLASSES:
            raise ValueError(f"unknown failure class: {failure_class}")
        super().__init__(failure_class)
        self.failure_class = failure_class


def validate_response(
    payload: Mapping[str, Any],
    allowed_evidence_ids: set[str],
    expected_model_version: str,
    returned_model_version: str | None,
    usage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate response content, citations, model identity, and usage metadata."""

    required = {"answer", "cited_evidence_ids", "abstained", "abstention_reason"}
    if set(payload) - (required | {"claim_to_evidence"}) or not required.issubset(payload):
        raise Phase7ContractError("response fields do not match contract")
    if returned_model_version != expected_model_version:
        raise Phase7ProviderFailure("model_drift")
    if usage is None or not {"input_tokens", "output_tokens"}.issubset(usage):
        raise Phase7ProviderFailure("missing_usage")
    answer = payload["answer"]
    citations = payload["cited_evidence_ids"]
    abstained = payload["abstained"]
    reason = payload["abstention_reason"]
    if not isinstance(answer, str) or not isinstance(citations, list) or not isinstance(abstained, bool):
        raise Phase7ContractError("response field types are invalid")
    if not isinstance(reason, str) or any(not isinstance(item, str) for item in citations):
        raise Phase7ContractError("citation or abstention fields are invalid")
    if len(citations) != len(set(citations)):
        raise Phase7ContractError("duplicate citation ID")
    if not set(citations).issubset(allowed_evidence_ids):
        raise Phase7ProviderFailure("invalid_citation_ids")
    if abstained and not reason.strip():
        raise Phase7ContractError("abstention requires a reason")
    if not abstained and not answer.strip():
        raise Phase7ContractError("non-abstaining response requires an answer")
    return dict(payload)


@dataclass
class AttemptLedger:
    """In-memory duplicate guard for logical requests and response records."""

    logical_request_ids: set[str]
    response_hashes: set[str]

    @classmethod
    def empty(cls) -> "AttemptLedger":
        return cls(set(), set())

    def register(self, logical_request_id: str, response_hash: str) -> None:
        if logical_request_id in self.logical_request_ids:
            raise Phase7ProviderFailure("duplicate_response")
        if response_hash in self.response_hashes:
            raise Phase7ProviderFailure("duplicate_response")
        self.logical_request_ids.add(logical_request_id)
        self.response_hashes.add(response_hash)


def write_record_once(path: Path, record: Mapping[str, Any]) -> None:
    """Create one immutable JSON record; refuse any overwrite."""

    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise

