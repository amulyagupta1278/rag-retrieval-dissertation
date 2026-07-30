import json

import pytest

from src.generation.phase7_freeze import Phase7ExecutionFailure
from src.generation.phase7_v2_freeze import validate_provider_response as old_validate
from src.generation.phase8_r4_v2_validation import validate_provider_response as corrected_validate


RAW = "runs/phase8_r4_improvements/generation_r4_v2_trace/raw/P8R4G0fb0ef5d959c.json"
PLAN = "runs/phase8_r4_improvements/generation_r4_v2_freeze/recovery_request_plan.jsonl"
CONFIG = "runs/phase8_r4_improvements/generation_r4_v2_correction_freeze/execution_config.json"


def evidence_ids():
    plans = [json.loads(x) for x in open(PLAN)]
    row = next(r for r in plans if r["blinded_request_id"] == "P8R4G0fb0ef5d959c")
    return list(row["evidence_id_to_chunk_id"])


def test_only_output_ceiling_changes_for_preserved_response():
    raw = json.load(open(RAW))
    with pytest.raises(Phase7ExecutionFailure) as exc:
        old_validate(raw, available_evidence_ids=evidence_ids())
    assert exc.value.failure_class == "missing_usage"
    valid = corrected_validate(raw, available_evidence_ids=evidence_ids())
    assert valid["usage"] == {"input_tokens": 2686, "output_tokens": 670}
    assert raw["stop_reason"] == "end_turn"


def test_corrected_continuation_is_cost_safe_and_four_call_trace():
    config = json.load(open(CONFIG))
    assert config["change_from_v2"] == "validator output-token ceiling only: 512 to 1024"
    assert len(config["remaining_trace_request_ids"]) == 4
    assert config["remaining_dispatch_n"] == 89
    assert config["continuation_hard_cap_usd"] <= config["remaining_cumulative_cap_usd"]
    assert config["prior_cumulative_r4_cost_usd"] + config["continuation_hard_cap_usd"] <= 3.70
