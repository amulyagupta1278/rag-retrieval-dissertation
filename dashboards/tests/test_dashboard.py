"""End-to-end integrity tests for generated offline dashboard."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboards"


def test_self_contained_dashboard_and_honest_h5_block() -> None:
    page = (DASH / "dashboard.html").read_text(encoding="utf-8")
    assert "H5 evidence unavailable at required base commit" in page
    assert "No later-branch value was copied" in page
    assert "Prompt-RAG reranker" in page
    assert "no router was built or claimed" in page.lower()
    assert "Frozen reference answer:" in page
    assert "Pooled positive evidence passages" in page
    assert 'src="https://cdn.plot.ly' not in page
    assert "plotly.js v" in page.lower()
    assert "ρ ≈" not in page


def test_static_figure_contract() -> None:
    expected = {
        "category_leader_matrix",
        "item_response_matrix",
        "hypothesis_forest",
        "rank_failure_drilldown",
        "exploratory_complementarity",
        "exploratory_oracle_ceiling",
    }
    assert {path.stem for path in (DASH / "figures").glob("*.png")} == expected
    assert {path.stem for path in (DASH / "figures").glob("*.pdf")} == expected
    assert all(path.stat().st_size > 1_000 for path in (DASH / "figures").iterdir())


def test_manifest_hashes_and_validity_boundary() -> None:
    manifest = json.loads((DASH / "data/dashboard_build_manifest.json").read_text(encoding="utf-8"))
    assert manifest["validity_status"] == "passed_seed42_only"
    assert manifest["blacklisted_source_reads"] == 0
    assert manifest["primary_qrel_base"] == "final_pooled"
    assert manifest["h5_source_available"] is False
    for relative, expected_hash in manifest["artifacts"].items():
        payload = (ROOT / relative).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_hash
