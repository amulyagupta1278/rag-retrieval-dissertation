"""Offline tests for dashboard analyses and dual-render outputs."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dashboards"))

from charts import (  # noqa: E402
    SYSTEMS,
    bootstrap_category_intervals,
    discrimination_audit,
    forest_rows,
)


FRAME = ROOT / "dashboards/data/per_query_pilot.csv"
STATS = ROOT / "runs/v2/phase6_seed42_final/statistics/preregistered_h1_h4_results.json"


def test_category_intervals_cover_every_slice_deterministically() -> None:
    frame = pd.read_csv(FRAME)
    first = bootstrap_category_intervals(frame)
    second = bootstrap_category_intervals(frame)
    assert len(first) == 6 * 5 * 3
    pd.testing.assert_frame_equal(first, second)
    assert set(first["query_n"]) == {4, 6}
    assert set(first["seed"]) == {42}
    assert ((first["ci_low"] <= first["mean"]) & (first["mean"] <= first["ci_high"])).all()


def test_discrimination_audit_uses_five_systems_without_irt() -> None:
    frame = pd.read_csv(FRAME)
    audit = discrimination_audit(frame)
    assert len(audit) == 34
    assert audit["query_id"].nunique() == 34
    for system in SYSTEMS:
        assert f"{system}_gold_rank" in audit.columns
    assert set(audit["status"]) <= {"positive", "flag_negative_or_near_zero", "undefined_all_same"}


def test_forest_reads_authoritative_seed42_effects() -> None:
    statistics = json.loads(STATS.read_text(encoding="utf-8"))
    rows = forest_rows(statistics)
    assert set(rows["hypothesis"]) == {"H1", "H2", "H3", "H4"}
    h2 = rows.loc[
        (rows["hypothesis"] == "H2")
        & rows["comparison"].str.contains("paraphrase", case=False)
    ]
    assert len(h2) == 1
    assert float(h2.iloc[0]["effect"]) == -0.425
    assert h2.iloc[0]["verdict"] == "not supported"
