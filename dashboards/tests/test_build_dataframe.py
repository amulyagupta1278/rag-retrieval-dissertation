"""Gate 1 contracts for single-commit dashboard pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dashboards"))

import build_dataframe  # noqa: E402


def test_gate1_builds_exact_primary_panel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(build_dataframe, "OUT", tmp_path)
    frame, audit = build_dataframe.build()

    assert len(frame) == 170
    assert frame["query_id"].nunique() == 34
    assert frame["system"].nunique() == 5
    assert set(frame["qrel_base"]) == {"final_pooled"}
    assert not frame.isna().any().any()
    assert audit["status"] == "gate1_passed"
    assert audit["evidence_commit"] == build_dataframe.EVIDENCE_COMMIT
    assert audit["blacklisted_sources_read"] == []
    assert audit["h5_source_available"] is True
    assert max(abs(row["delta"]) for row in audit["primary_reconciliation"]) <= 1e-12
    assert (tmp_path / "per_query_pilot.csv").is_file()
    assert (tmp_path / "per_query_pilot.parquet").is_file()

    payload = json.loads((tmp_path / "dashboard_payload.json").read_text(encoding="utf-8"))
    assert payload["evidence_commit"] == build_dataframe.EVIDENCE_COMMIT
    assert len(payload["queries"]) == 34
    assert len(payload["category_mrr"]) == 6 * 5
    assert len(payload["forest"]) == 10
    assert payload["h5"]["label_sources"] == {"human_owner": 26, "offline_ai_knn": 144}
    assert [row["spearman_rho"] for row in payload["h5"]["correlations"]] == [
        -0.033280283273840396,
        0.3395352861284314,
    ]


def test_blacklisted_read_fails_before_git_access() -> None:
    reader = build_dataframe.SourceReader()
    relative = next(iter(build_dataframe.BLACKLISTED))
    try:
        reader.bytes(relative)
    except build_dataframe.ValidityError as exc:
        assert "blacklisted source read attempted" in str(exc)
    else:
        raise AssertionError("blacklisted read did not fail closed")


def test_difficulty_direction_is_hard_when_more_systems_miss() -> None:
    frame, _ = build_dataframe.build()
    query = frame[["query_id", "n_systems_hit_at_5", "difficulty"]].drop_duplicates()
    expected = 1 - query["n_systems_hit_at_5"] / 5
    assert (query["difficulty"] == expected).all()
    assert query.sort_values("difficulty").iloc[-1]["n_systems_hit_at_5"] <= query.sort_values("difficulty").iloc[0]["n_systems_hit_at_5"]
