"""Deterministic network-free fake provider for Phase 7 contract tests."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from src.generation.phase7_contract import FAILURE_CLASSES, Phase7ProviderFailure


class MockPhase7Provider:
    """Return deterministic synthetic responses or one requested failure."""

    def __init__(self, model_version: str = "mock-model-v1", failure_class: str | None = None) -> None:
        if failure_class is not None and failure_class not in FAILURE_CLASSES:
            raise ValueError(f"unknown failure class: {failure_class}")
        self.model_version = model_version
        self.failure_class = failure_class

    def generate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self.failure_class is not None:
            raise Phase7ProviderFailure(self.failure_class)
        evidence = request.get("evidence", [])
        evidence_ids = [item["evidence_id"] for item in evidence]
        fingerprint = hashlib.sha256(str(sorted(request.items())).encode("utf-8")).hexdigest()
        if evidence_ids:
            response = {
                "answer": "Synthetic answer for offline contract testing.",
                "cited_evidence_ids": [evidence_ids[0]],
                "abstained": False,
                "abstention_reason": "",
            }
        else:
            response = {
                "answer": "",
                "cited_evidence_ids": [],
                "abstained": True,
                "abstention_reason": "No evidence supplied.",
            }
        return {
            "response": response,
            "model_version": self.model_version,
            "usage": {"input_tokens": len(fingerprint), "output_tokens": 8},
            "request_fingerprint": fingerprint,
        }

