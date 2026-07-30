import json


BASE = "runs/phase8_r4_improvements/generation_r4_v3_freeze/"


def rows(name):
    return [json.loads(x) for x in open(BASE + name) if x.strip()]


def test_v3_reuses_50_and_recovers_exactly_50():
    reused, plans, payloads = rows("reuse_50_records.jsonl"), rows("request_plan.jsonl"), rows("request_payloads.jsonl")
    assert len(reused) == len({r["blinded_request_id"] for r in reused}) == 50
    assert len(plans) == len(payloads) == 50
    assert {r["blinded_request_id"] for r in reused}.isdisjoint({r["blinded_request_id"] for r in plans})
    assert all(r["request_sha256"] != r["v2_request_sha256"] for r in plans)


def test_v3_trace_covers_systems_categories_failed_request_and_cap():
    config = json.load(open(BASE + "execution_config.json"))
    plans = {r["blinded_request_id"]: r for r in rows("request_plan.jsonl")}
    trace = [plans[x] for x in config["v3_trace_request_ids"]]
    assert len(trace) == 5
    assert len({r["system_id"] for r in trace}) == 5
    assert len({r["category"] for r in trace}) == 5
    assert config["v3_trace_includes_failed_request"] in config["v3_trace_request_ids"]
    assert config["v3_hard_cap_usd"] <= config["remaining_cumulative_cap_usd"]
    assert config["prior_cumulative_r4_cost_usd"] + config["v3_hard_cap_usd"] <= 3.70


def test_v3_prompt_requires_exact_claim_coverage():
    prompt = open("prompts/phase8_r4_answer_generation_v3.txt").read()
    assert "exactly one claim_to_evidence entry for every factual claim" in prompt
    assert "union of evidence_ids" in prompt
