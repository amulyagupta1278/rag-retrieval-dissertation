import json

import pytest

from src.retrievers.prompt_rag_claude_v2 import ClaudeContractError
from src.retrievers.prompt_rag_phase8_r4 import build_request, parse_ranking


def candidates(n=25):
    return [{"chunk_id": f"c{i:02d}", "text": f"text {i}"} for i in range(n)]


def test_dynamic_candidate_contract_and_fixed_ranking():
    rows = candidates(35)
    request = build_request(query={"query_id": "q1", "question": "why?"}, candidates=rows, system_instruction="score")
    assert request["max_tokens"] == 512
    scores = {row["chunk_id"]: i % 4 for i, row in enumerate(rows)}
    ranking = parse_ranking(json.dumps({"candidate_scores": scores}), scores)
    assert len(ranking) == 35
    assert [row["score"] for row in ranking] == sorted(scores.values(), reverse=True)


@pytest.mark.parametrize("n", [24, 51])
def test_candidate_bounds_fail_closed(n):
    with pytest.raises(ClaudeContractError):
        build_request(query={"query_id": "q1", "question": "why?"}, candidates=candidates(n), system_instruction="score")


def test_frozen_plan_is_unique_and_hash_bound():
    base = "runs/phase8_r4_improvements/prompt_rag_r4_freeze/"
    config = json.load(open(base + "execution_config.json"))
    plans = [json.loads(x) for x in open(base + "request_plan.jsonl")]
    assert len(plans) == 100 == len({p["query_id"] for p in plans})
    assert all(25 <= p["candidate_n"] <= 50 for p in plans)
    assert all(len(p["candidate_chunk_ids"]) == len(set(p["candidate_chunk_ids"])) for p in plans)
    assert config["retrieval_hard_cap_usd"] + config["generation_reserved_usd"] <= 3.70
