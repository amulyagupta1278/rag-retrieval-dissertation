"""Static tests for Phase 7 draft prompt and config blindness."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prompt_is_draft_and_contains_no_system_or_gold_placeholders() -> None:
    prompt = (ROOT / "prompts/phase7_answer_generation_draft.txt").read_text(encoding="utf-8")
    assert "draft_pending_owner_review" in prompt
    assert "{question}" in prompt
    assert "{evidence_blocks}" in prompt
    lowered = prompt.lower()
    for forbidden in ("{system", "{score", "{qrel", "{metric", "{owner_grade"):
        assert forbidden not in lowered


def test_config_leaves_methodology_decisions_unselected() -> None:
    config = json.loads((ROOT / "configs/phase7_generation_draft.json").read_text())
    assert config["provider"] is None
    assert config["model"] is None
    assert config["context_depth"] is None
    assert config["evaluator_design"] is None
    assert config["execution_enabled"] is False

