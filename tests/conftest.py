"""Transparent lifecycle supersessions for immutable historical tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "audits/lifecycle_supersessions/expected_failures.json"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run exact obsolete assertions as strict expected failures, never silent skips."""
    if not REGISTRY.exists():
        return
    entries = json.loads(REGISTRY.read_text(encoding="utf-8"))["supersessions"]
    collected = {item.nodeid: item for item in items}
    for nodeid, entry in entries.items():
        item = collected.get(nodeid)
        if item is None:
            continue
        item.add_marker(
            pytest.mark.xfail(
                reason=entry["reason"],
                run=True,
                strict=True,
            )
        )
