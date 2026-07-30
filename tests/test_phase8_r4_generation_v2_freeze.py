import json


BASE = "runs/phase8_r4_improvements/generation_r4_v2_freeze/"


def rows(name):
    return [json.loads(x) for x in open(BASE + name) if x.strip()]


def test_v2_reuses_only_exact_v1_records_and_dispatches_90():
    reused = rows("reused_v1_records.jsonl")
    recovery = rows("recovery_request_plan.jsonl")
    assert len(reused) == 10 == len({r["blinded_request_id"] for r in reused})
    assert len(recovery) == 90 == len({r["blinded_request_id"] for r in recovery})
    assert not ({r["blinded_request_id"] for r in reused} & {r["blinded_request_id"] for r in recovery})
    assert all(r["request_sha256"] != r["v1_request_sha256"] for r in recovery)


def test_v2_trace_and_cap_are_fail_closed():
    config = json.load(open(BASE + "execution_config.json"))
    plans = {r["blinded_request_id"]: r for r in rows("recovery_request_plan.jsonl")}
    trace = [plans[x] for x in config["v2_trace_request_ids"]]
    assert len(trace) == 5
    assert len({r["system_id"] for r in trace}) == 5
    assert len({r["category"] for r in trace}) == 5
    assert config["v2_trace_includes_v1_failed_request"] in config["v2_trace_request_ids"]
    assert config["v2_hard_cap_usd"] <= config["remaining_cumulative_r4_cap_usd"]
    assert config["prior_cumulative_r4_cost_usd"] + config["v2_hard_cap_usd"] <= 3.70
