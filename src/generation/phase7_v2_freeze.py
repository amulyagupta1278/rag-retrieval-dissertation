"""Offline Phase 7 V2 recovery contract with 512-token output cap."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from src.generation import phase7_freeze as v1
from src.utils.atomic_io import stable_json
from src.utils.hashing import sha256_text


MODEL = v1.MODEL
SDK_VERSION = v1.SDK_VERSION
API_VERSION = v1.API_VERSION
ENDPOINT = v1.ENDPOINT
CONTEXT_DEPTH = v1.CONTEXT_DEPTH
TEMPERATURE = v1.TEMPERATURE
TIMEOUT_SECONDS = v1.TIMEOUT_SECONDS
RETRY_N = v1.RETRY_N
TRACE_N = v1.TRACE_N
FAILURE_CLASSES = v1.FAILURE_CLASSES
INPUT_USD_PER_MILLION = v1.INPUT_USD_PER_MILLION
OUTPUT_USD_PER_MILLION = v1.OUTPUT_USD_PER_MILLION
PREVIOUS_HARD_COST_CAP_USD = v1.HARD_COST_CAP_USD
HARD_COST_CAP_USD = 3.0
V1_SPENT_USD = 0.005847
MAX_OUTPUT_TOKENS = 512
V1_MAX_OUTPUT_TOKENS = v1.MAX_OUTPUT_TOKENS


class Phase7V2ContractError(ValueError):
    """Raised when V2 recovery contract differs from frozen design."""


def build_request(
    *, prompt: str, serialized_context: str, schema: Mapping[str, Any]
) -> dict[str, Any]:
    """Build V2 request by changing only V1 output-token cap."""

    request = v1.build_request(
        prompt=prompt,
        serialized_context=serialized_context,
        schema=schema,
    )
    if request["max_tokens"] != V1_MAX_OUTPUT_TOKENS:
        raise Phase7V2ContractError("unexpected V1 output-token cap")
    request["max_tokens"] = MAX_OUTPUT_TOKENS
    return request


def request_sha256(request: Mapping[str, Any]) -> str:
    """Hash exact canonical V2 request payload."""

    return sha256_text(stable_json(dict(request)))


def conservative_input_token_envelope(request: Mapping[str, Any]) -> int:
    """Reuse frozen V1 conservative input-token method."""

    return int(v1.conservative_input_token_envelope(request)["token_envelope"])


def maximum_cost_usd(input_token_n: int, request_n: int) -> float:
    """Price V2 input envelope and maximum 512 output tokens per request."""

    if input_token_n < 0 or request_n < 0:
        raise Phase7V2ContractError("token and request counts cannot be negative")
    return (
        input_token_n * INPUT_USD_PER_MILLION
        + request_n * MAX_OUTPUT_TOKENS * OUTPUT_USD_PER_MILLION
    ) / 1_000_000


def observed_cost_usd(input_token_n: int, output_token_n: int) -> float:
    """Price actual provider usage using frozen official rates."""

    if input_token_n < 0 or output_token_n < 0:
        raise Phase7V2ContractError("observed token counts cannot be negative")
    return (
        input_token_n * INPUT_USD_PER_MILLION
        + output_token_n * OUTPUT_USD_PER_MILLION
    ) / 1_000_000


def projected_cumulative_exposure_usd(
    *,
    v2_observed_input_tokens: int,
    v2_observed_output_tokens: int,
    unexecuted_input_token_envelope: int,
    unexecuted_request_n: int,
    ambiguous_dispatch_reserve_usd: float,
) -> float:
    """Return cumulative V1 + actual V2 + remaining V2 + reserve exposure."""

    if ambiguous_dispatch_reserve_usd < 0:
        raise Phase7V2ContractError("ambiguous reserve cannot be negative")
    return (
        V1_SPENT_USD
        + observed_cost_usd(v2_observed_input_tokens, v2_observed_output_tokens)
        + maximum_cost_usd(
            unexecuted_input_token_envelope,
            unexecuted_request_n,
        )
        + ambiguous_dispatch_reserve_usd
    )


def enforce_pre_dispatch_cap(
    projected_cumulative_usd: float,
    *,
    hard_cap_usd: float = HARD_COST_CAP_USD,
) -> None:
    """Refuse before dispatch when projected cumulative exposure exceeds cap."""

    if projected_cumulative_usd > hard_cap_usd + 1e-12:
        raise v1.Phase7ExecutionFailure(
            "cost_cap_breach",
            f"projected cumulative exposure ${projected_cumulative_usd:.6f} "
            f"exceeds ${hard_cap_usd:.6f}",
        )


def dispatch_once_after_cap_gate(
    *,
    projected_cumulative_usd: float,
    request: Mapping[str, Any],
    sender: Callable[[dict[str, Any]], Any],
    hard_cap_usd: float = HARD_COST_CAP_USD,
) -> Any:
    """Gate cost, then perform exactly one sender call; never retry."""

    enforce_pre_dispatch_cap(
        projected_cumulative_usd,
        hard_cap_usd=hard_cap_usd,
    )
    return sender(copy.deepcopy(dict(request)))


def validate_provider_response(
    response: Any,
    *,
    available_evidence_ids: Iterable[str],
) -> dict[str, Any]:
    """Validate V2 response; token-limit finish remains terminal truncation."""

    if not isinstance(response, Mapping):
        raise v1.Phase7ExecutionFailure("missing_response")
    response_id = response.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise v1.Phase7ExecutionFailure("missing_response")
    if response.get("model") != MODEL:
        raise v1.Phase7ExecutionFailure("model_drift")
    usage = response.get("usage")
    if not isinstance(usage, Mapping) or not {
        "input_tokens",
        "output_tokens",
    }.issubset(usage):
        raise v1.Phase7ExecutionFailure("missing_usage")
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
        raise v1.Phase7ExecutionFailure("missing_usage")
    if int(usage.get("cache_creation_input_tokens") or 0) != 0 or int(
        usage.get("cache_read_input_tokens") or 0
    ) != 0:
        raise v1.Phase7ExecutionFailure(
            "cost_cap_breach",
            "unexpected prompt-cache usage invalidates cost plan",
        )
    stop_reason = response.get("stop_reason")
    if stop_reason == "max_tokens":
        raise v1.Phase7ExecutionFailure("truncation")
    if stop_reason in {"refusal", "model_context_window_exceeded"}:
        raise v1.Phase7ExecutionFailure("refusal")
    if stop_reason != "end_turn":
        raise v1.Phase7ExecutionFailure("missing_response")
    content = response.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise v1.Phase7ExecutionFailure("missing_response")
    block = content[0]
    if not isinstance(block, Mapping) or block.get("type") != "text":
        raise v1.Phase7ExecutionFailure("refusal")
    text = block.get("text")
    if not isinstance(text, str) or not text.strip():
        raise v1.Phase7ExecutionFailure("missing_response")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise v1.Phase7ExecutionFailure("malformed_response") from exc
    return {
        "answer": v1.validate_answer_payload(
            payload,
            available_evidence_ids=available_evidence_ids,
        ),
        "model": response["model"],
        "response_id": response_id,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


def assert_v2_output_path(
    path: str | Path,
    *,
    v2_root: str | Path,
    v1_root: str | Path,
) -> Path:
    """Require output below V2 root and outside immutable V1 root."""

    target = Path(path).resolve()
    resolved_v2 = Path(v2_root).resolve()
    resolved_v1 = Path(v1_root).resolve()
    try:
        target.relative_to(resolved_v2)
    except ValueError:
        raise Phase7V2ContractError("V2 output path escapes V2 root") from None
    try:
        target.relative_to(resolved_v1)
    except ValueError:
        return target
    raise Phase7V2ContractError("V2 output path overlaps immutable V1 root")


def validate_trace_reuse(
    *,
    trace_request: Mapping[str, Any],
    frozen_panel_request: Mapping[str, Any],
    response_valid: bool,
    already_has_panel_output: bool,
) -> str:
    """Return request hash only for one valid, exact V2 panel request."""

    trace_hash = request_sha256(trace_request)
    panel_hash = request_sha256(frozen_panel_request)
    if trace_hash != panel_hash:
        raise Phase7V2ContractError("trace request hash differs from frozen V2 panel")
    if not response_valid:
        raise Phase7V2ContractError("invalid trace response cannot be reused")
    if already_has_panel_output:
        raise Phase7V2ContractError("panel output already exists; duplicate billing forbidden")
    if trace_request.get("max_tokens") != MAX_OUTPUT_TOKENS:
        raise Phase7V2ContractError("trace response is not V2 512-token protocol")
    return trace_hash


__all__ = [
    "API_VERSION",
    "CONTEXT_DEPTH",
    "ENDPOINT",
    "FAILURE_CLASSES",
    "HARD_COST_CAP_USD",
    "MAX_OUTPUT_TOKENS",
    "MODEL",
    "PREVIOUS_HARD_COST_CAP_USD",
    "RETRY_N",
    "SDK_VERSION",
    "TEMPERATURE",
    "TIMEOUT_SECONDS",
    "TRACE_N",
    "V1_MAX_OUTPUT_TOKENS",
    "V1_SPENT_USD",
    "Phase7V2ContractError",
    "assert_v2_output_path",
    "build_request",
    "conservative_input_token_envelope",
    "dispatch_once_after_cap_gate",
    "enforce_pre_dispatch_cap",
    "maximum_cost_usd",
    "observed_cost_usd",
    "projected_cumulative_exposure_usd",
    "request_sha256",
    "validate_provider_response",
    "validate_trace_reuse",
]
