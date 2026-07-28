"""Shared fail-closed contract validation."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Iterable
from urllib.parse import urlparse

SCHEMA_VERSION = "2.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(r"\b(?:placeholder|synthetic|dummy|lorem ipsum|fallback corpus)\b", re.I)


class ContractError(ValueError):
    """Raised when a V2 artifact violates its declared contract."""


def required_text(name: str, value: Any, *, allow_markers: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string")
    value = value.strip()
    if not allow_markers and PLACEHOLDER_RE.search(value):
        raise ContractError(f"{name} contains forbidden placeholder/synthetic marker")
    return value


def require_schema(value: str) -> None:
    if value != SCHEMA_VERSION:
        raise ContractError(f"schema_version must equal {SCHEMA_VERSION!r}, got {value!r}")


def require_sha256(name: str, value: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ContractError(f"{name} must be a lowercase 64-character SHA-256 hex digest")


def require_url(name: str, value: str) -> None:
    required_text(name, value)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ContractError(f"{name} must be an absolute HTTPS URL")


def require_unique(name: str, values: Iterable[str]) -> None:
    items = list(values)
    if len(items) != len(set(items)):
        raise ContractError(f"{name} contains duplicate IDs")


def stable_dict(value: Any) -> dict[str, Any]:
    """Return dataclass as JSON-compatible mapping."""
    return asdict(value)
