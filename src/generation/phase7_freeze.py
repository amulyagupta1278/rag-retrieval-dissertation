"""Frozen Claude Phase 7 request, response, trace, and cost contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from src.utils.atomic_io import stable_json
from src.utils.hashing import sha256_text


MODEL = "claude-haiku-4-5-20251001"
RETURNED_MODEL_POLICY = "exact_match_only"
SDK_NAME = "anthropic"
SDK_VERSION = "0.116.0"
API_VERSION = "2023-06-01"
ENDPOINT = "/v1/messages"
CONTEXT_DEPTH = 3
MAX_OUTPUT_TOKENS = 256
TEMPERATURE = 0
TIMEOUT_SECONDS = 120.0
RETRY_N = 0
TRACE_N = 10
HARD_COST_CAP_USD = 0.95
INPUT_USD_PER_MILLION = 1.0
OUTPUT_USD_PER_MILLION = 5.0
TOKEN_ENVELOPE_BYTES_PER_TOKEN = 2
TOKEN_ENVELOPE_REQUEST_OVERHEAD = 256
LEGAL_EVIDENCE_IDS = ("E01", "E02", "E03")

FAILURE_CLASSES = (
    "credential_unavailable",
    "non_2xx_response",
    "timeout",
    "ambiguous_dispatch",
    "model_drift",
    "refusal",
    "safety_block",
    "missing_usage",
    "missing_response",
    "malformed_response",
    "schema_violation",
    "invalid_citation",
    "unsupported_citation",
    "truncation",
    "duplicate_response",
    "context_mismatch",
    "cost_cap_breach",
)

INLINE_CITATION = re.compile(r"\[(E\d{2})\]")


class Phase7FreezeError(ValueError):
    """Raised when a frozen Phase 7 contract is violated."""


class Phase7ExecutionFailure(RuntimeError):
    """Terminal failure with one frozen failure classification."""

    def __init__(self, failure_class: str, message: str = "") -> None:
        if failure_class not in FAILURE_CLASSES:
            raise ValueError(f"unknown Phase 7 failure class: {failure_class}")
        super().__init__(message or failure_class)
        self.failure_class = failure_class


def response_schema() -> dict[str, Any]:
    """Return strict structured-output schema for one answer."""

    evidence_enum = list(LEGAL_EVIDENCE_IDS)
    return {
        "additionalProperties": False,
        "properties": {
            "abstained": {"type": "boolean"},
            "abstention_reason": {"type": "string"},
            "answer": {"type": "string"},
            "cited_evidence_ids": {
                "items": {"enum": evidence_enum, "type": "string"},
                "type": "array",
            },
            "claim_to_evidence": {
                "items": {
                    "additionalProperties": False,
                    "properties": {
                        "claim": {"type": "string"},
                        "evidence_ids": {
                            "items": {"enum": evidence_enum, "type": "string"},
                            "type": "array",
                        },
                    },
                    "required": ["claim", "evidence_ids"],
                    "type": "object",
                },
                "type": "array",
            },
        },
        "required": [
            "answer",
            "cited_evidence_ids",
            "abstained",
            "abstention_reason",
        ],
        "type": "object",
    }


def _validate_context(serialized_context: str) -> dict[str, Any]:
    try:
        context = json.loads(serialized_context)
    except json.JSONDecodeError as exc:
        raise Phase7FreezeError("serialized context is malformed JSON") from exc
    if not isinstance(context, dict) or set(context) != {"evidence", "question"}:
        raise Phase7FreezeError("serialized context fields are not blind allowlist")
    if not isinstance(context["question"], str) or not context["question"].strip():
        raise Phase7FreezeError("question is empty")
    evidence = context["evidence"]
    if not isinstance(evidence, list) or len(evidence) > CONTEXT_DEPTH:
        raise Phase7FreezeError("evidence depth exceeds frozen top-3")
    expected_ids = list(LEGAL_EVIDENCE_IDS[: len(evidence)])
    actual_ids: list[str] = []
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"evidence_id", "text"}:
            raise Phase7FreezeError("evidence contains forbidden fields")
        if not isinstance(item["text"], str) or not item["text"].strip():
            raise Phase7FreezeError("evidence text is empty")
        actual_ids.append(item["evidence_id"])
    if actual_ids != expected_ids:
        raise Phase7FreezeError("evidence IDs must be sequential E01-E03")
    return context


def build_request(
    *, prompt: str, serialized_context: str, schema: Mapping[str, Any]
) -> dict[str, Any]:
    """Build one exact stateless Claude request without system identity."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise Phase7FreezeError("prompt is empty")
    _validate_context(serialized_context)
    if dict(schema) != response_schema():
        raise Phase7FreezeError("response schema differs from frozen schema")
    request = {
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [{"content": serialized_context, "role": "user"}],
        "model": MODEL,
        "output_config": {
            "format": {"schema": dict(schema), "type": "json_schema"}
        },
        "service_tier": "standard_only",
        "stream": False,
        "system": prompt,
        "temperature": TEMPERATURE,
        "tools": [],
    }
    forbidden = (
        "reference_answer",
        "gold_chunk",
        "qrel",
        "retrieval_system",
        "system_id",
        "retrieval_score",
        "question_category",
        "owner_grade",
    )
    lowered = stable_json(request).lower()
    if any(term in lowered for term in forbidden):
        raise Phase7FreezeError("request contains forbidden benchmark metadata")
    return request


def request_sha256(request: Mapping[str, Any]) -> str:
    """Hash exact canonical request payload."""

    return sha256_text(stable_json(dict(request)))


def conservative_input_token_envelope(request: Mapping[str, Any]) -> dict[str, int | str]:
    """Return offline cost envelope without API/tokenizer access.

    Anthropic publishes no local model-compatible tokenizer in installed SDK.
    Envelope uses one token per two UTF-8 request bytes plus fixed hidden-format
    reserve. This is deliberately above typical English token density, but actual
    provider usage remains authoritative during execution.
    """

    byte_n = len(stable_json(dict(request)).encode("utf-8"))
    token_n = math.ceil(byte_n / TOKEN_ENVELOPE_BYTES_PER_TOKEN)
    token_n += TOKEN_ENVELOPE_REQUEST_OVERHEAD
    return {
        "method": "ceil(canonical_request_utf8_bytes/2)+256",
        "request_utf8_byte_n": byte_n,
        "token_envelope": token_n,
    }


def maximum_cost_usd(input_token_n: int, request_n: int) -> float:
    """Price input envelope and maximum 256 output tokens per request."""

    if input_token_n < 0 or request_n < 0:
        raise Phase7FreezeError("token and request counts cannot be negative")
    return (
        input_token_n * INPUT_USD_PER_MILLION
        + request_n * MAX_OUTPUT_TOKENS * OUTPUT_USD_PER_MILLION
    ) / 1_000_000


def enforce_cost_cap(cumulative_worst_case_usd: float) -> None:
    """Fail closed when planned worst-case exposure exceeds frozen cap."""

    if cumulative_worst_case_usd > HARD_COST_CAP_USD + 1e-12:
        raise Phase7ExecutionFailure(
            "cost_cap_breach",
            f"planned exposure ${cumulative_worst_case_usd:.6f} exceeds "
            f"${HARD_COST_CAP_USD:.2f}",
        )


def select_trace(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Select first ten SHA-256-ordered logical request IDs."""

    if len(rows) != 170:
        raise Phase7FreezeError("trace selection requires exact 170-request panel")
    logical_ids = [row.get("logical_request_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in logical_ids):
        raise Phase7FreezeError("trace row lacks logical request ID")
    if len(set(logical_ids)) != len(logical_ids):
        raise Phase7FreezeError("duplicate logical request ID")
    selected = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            hashlib.sha256(row["logical_request_id"].encode("utf-8")).hexdigest(),
            row["logical_request_id"],
        ),
    )[:TRACE_N]
    systems = {row.get("system_id") for row in selected}
    if len(systems) != 5:
        raise Phase7FreezeError("SHA trace does not cover all five systems")
    if len({row.get("category") for row in selected}) < 2:
        raise Phase7FreezeError("SHA trace lacks multiple categories")
    if len({row.get("serialized_context_utf8_bytes") for row in selected}) < 2:
        raise Phase7FreezeError("SHA trace lacks varying context lengths")
    return selected


def _validate_claim_mapping(
    value: Any, allowed_ids: set[str], cited_ids: set[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise Phase7ExecutionFailure("schema_violation", "claim mapping must be array")
    claims: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"claim", "evidence_ids"}:
            raise Phase7ExecutionFailure("schema_violation", "invalid claim mapping")
        claim = item["claim"]
        evidence_ids = item["evidence_ids"]
        if not isinstance(claim, str) or not claim.strip() or claim in claims:
            raise Phase7ExecutionFailure("schema_violation", "invalid duplicate claim")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or any(not isinstance(value, str) for value in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            raise Phase7ExecutionFailure("schema_violation", "invalid claim citations")
        if not set(evidence_ids).issubset(allowed_ids & cited_ids):
            raise Phase7ExecutionFailure("invalid_citation", "claim citation is invalid")
        claims.add(claim)
        output.append({"claim": claim, "evidence_ids": list(evidence_ids)})
    return output


def validate_answer_payload(
    payload: Any, *, available_evidence_ids: Iterable[str]
) -> dict[str, Any]:
    """Validate schema, abstention, and deterministic citation coverage."""

    if not isinstance(payload, Mapping):
        raise Phase7ExecutionFailure("schema_violation", "answer is not object")
    required = {"answer", "cited_evidence_ids", "abstained", "abstention_reason"}
    allowed = required | {"claim_to_evidence"}
    if not required.issubset(payload) or set(payload) - allowed:
        raise Phase7ExecutionFailure("schema_violation", "answer fields differ")
    answer = payload["answer"]
    citations = payload["cited_evidence_ids"]
    abstained = payload["abstained"]
    reason = payload["abstention_reason"]
    if (
        not isinstance(answer, str)
        or not isinstance(citations, list)
        or not isinstance(abstained, bool)
        or not isinstance(reason, str)
        or any(not isinstance(value, str) for value in citations)
    ):
        raise Phase7ExecutionFailure("schema_violation", "answer field type differs")
    if len(citations) != len(set(citations)):
        raise Phase7ExecutionFailure("schema_violation", "duplicate citation ID")
    available = set(available_evidence_ids)
    if not available.issubset(set(LEGAL_EVIDENCE_IDS)):
        raise Phase7FreezeError("available evidence ID is outside E01-E03")
    if not set(citations).issubset(available):
        raise Phase7ExecutionFailure("invalid_citation", "citation not supplied")
    inline = set(INLINE_CITATION.findall(answer))
    if not inline.issubset(available):
        raise Phase7ExecutionFailure("invalid_citation", "inline citation not supplied")
    if abstained:
        if answer.strip() or citations or not reason.strip():
            raise Phase7ExecutionFailure(
                "schema_violation", "abstention requires empty answer/citations and reason"
            )
    else:
        if not answer.strip() or reason or not citations or inline != set(citations):
            raise Phase7ExecutionFailure(
                "schema_violation", "answer citation coverage or abstention fields differ"
            )
    result = dict(payload)
    if "claim_to_evidence" in payload:
        result["claim_to_evidence"] = _validate_claim_mapping(
            payload["claim_to_evidence"], available, set(citations)
        )
    return result


def validate_provider_response(
    response: Any, *, available_evidence_ids: Iterable[str]
) -> dict[str, Any]:
    """Validate one provider envelope and embedded structured answer."""

    if not isinstance(response, Mapping):
        raise Phase7ExecutionFailure("missing_response")
    response_id = response.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise Phase7ExecutionFailure("missing_response")
    if response.get("model") != MODEL:
        raise Phase7ExecutionFailure("model_drift")
    usage = response.get("usage")
    if not isinstance(usage, Mapping) or not {
        "input_tokens",
        "output_tokens",
    }.issubset(usage):
        raise Phase7ExecutionFailure("missing_usage")
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens <= 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens <= 0
        or output_tokens > MAX_OUTPUT_TOKENS
    ):
        raise Phase7ExecutionFailure("missing_usage")
    if int(usage.get("cache_creation_input_tokens") or 0) != 0 or int(
        usage.get("cache_read_input_tokens") or 0
    ) != 0:
        raise Phase7ExecutionFailure(
            "cost_cap_breach", "unexpected prompt-cache usage invalidates cost plan"
        )
    stop_reason = response.get("stop_reason")
    if stop_reason == "max_tokens":
        raise Phase7ExecutionFailure("truncation")
    if stop_reason in {"refusal", "model_context_window_exceeded"}:
        raise Phase7ExecutionFailure("refusal")
    if stop_reason != "end_turn":
        raise Phase7ExecutionFailure("missing_response")
    content = response.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise Phase7ExecutionFailure("missing_response")
    block = content[0]
    if not isinstance(block, Mapping) or block.get("type") != "text":
        raise Phase7ExecutionFailure("refusal")
    text = block.get("text")
    if not isinstance(text, str) or not text.strip():
        raise Phase7ExecutionFailure("missing_response")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Phase7ExecutionFailure("malformed_response") from exc
    return {
        "answer": validate_answer_payload(
            payload, available_evidence_ids=available_evidence_ids
        ),
        "model": response["model"],
        "response_id": response_id,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


def trace_hash(logical_request_id: str) -> str:
    """Return selection digest published with trace plan."""

    return hashlib.sha256(logical_request_id.encode("utf-8")).hexdigest()


__all__ = [
    "API_VERSION",
    "CONTEXT_DEPTH",
    "ENDPOINT",
    "FAILURE_CLASSES",
    "HARD_COST_CAP_USD",
    "INPUT_USD_PER_MILLION",
    "LEGAL_EVIDENCE_IDS",
    "MAX_OUTPUT_TOKENS",
    "MODEL",
    "OUTPUT_USD_PER_MILLION",
    "RETRY_N",
    "RETURNED_MODEL_POLICY",
    "SDK_NAME",
    "SDK_VERSION",
    "TEMPERATURE",
    "TIMEOUT_SECONDS",
    "TRACE_N",
    "Phase7ExecutionFailure",
    "Phase7FreezeError",
    "build_request",
    "conservative_input_token_envelope",
    "enforce_cost_cap",
    "maximum_cost_usd",
    "request_sha256",
    "response_schema",
    "select_trace",
    "trace_hash",
    "validate_answer_payload",
    "validate_provider_response",
]
