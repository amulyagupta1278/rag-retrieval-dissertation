"""Gate 1 contracts for dashboard dataframe."""

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
    assert audit["blacklisted_sources_read"] == []
    assert max(abs(row["delta"]) for row in audit["primary_reconciliation"]) <= 1e-12
    assert (tmp_path / "per_query_pilot.csv").is_file()
    assert (tmp_path / "per_query_pilot.parquet").is_file()
    browser = json.loads((tmp_path / "evidence_browser.json").read_text(encoding="utf-8"))
    assert len(browser) == 34
    assert all(row["evidence"] for row in browser)
    assert all(passage["text"] for row in browser for passage in row["evidence"])


def test_blacklisted_read_fails_closed() -> None:
    reader = build_dataframe.SourceReader()
    blacklisted = next(iter(build_dataframe.BLACKLISTED))

    try:
        reader.bytes(blacklisted)
    except build_dataframe.ValidityError as exc:
        assert "blacklisted source read attempted" in str(exc)
    else:
        raise AssertionError("blacklisted read did not fail closed")


def test_gate1_audit_is_machine_readable_after_build(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(build_dataframe, "OUT", tmp_path)
    _, audit = build_dataframe.build()
    stored = json.loads((tmp_path / "gate1_reconciliation.json").read_text(encoding="utf-8"))

    assert stored == audit
    assert stored["statistics_summaries"]["H1"] == "inconclusive"
    assert stored["statistics_summaries"]["H2"]["verdict"] == "not_supported"
    assert stored["statistics_summaries"]["H4"]["verdict"] == "not_supported"
