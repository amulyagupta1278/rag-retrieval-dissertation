"""Gate 2 contracts for publication figure set."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboards"


def _png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", payload[16:24])


def test_six_numbered_print_figures_and_hashes() -> None:
    manifest = json.loads((DASH / "data/screen1_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "gate2_passed"
    assert manifest["figure_n"] == 6
    assert manifest["png_dpi"] == 300
    expected = {f"fig_5_{number}_" for number in range(1, 7)}
    pngs = sorted(DASH.glob("figures/fig_5_[1-6]_*.png"))
    pdfs = sorted(DASH.glob("figures/fig_5_[1-6]_*.pdf"))
    assert len(pngs) == len(pdfs) == 6
    assert all(any(path.name.startswith(prefix) for path in pngs) for prefix in expected)
    assert all(min(_png_dimensions(path)) > 900 for path in pngs)
    for relative, expected_hash in manifest["artifact_hashes"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected_hash


def test_category_leader_data_keeps_all_exact_ties() -> None:
    payload = json.loads((DASH / "data/dashboard_payload.json").read_text(encoding="utf-8"))
    for category in {row["category"] for row in payload["category_mrr"]}:
        panel = [row for row in payload["category_mrr"] if row["category"] == category]
        maximum = max(row["mean"] for row in panel)
        leaders = [row["system"] for row in panel if abs(row["mean"] - maximum) < 1e-12]
        assert leaders
        if category in {"exact_lookup", "terminology", "entity_relation", "multi_hop"}:
            assert len(leaders) > 1


def test_h5_figure_uses_frozen_aggregate_not_synthetic_points() -> None:
    payload = json.loads((DASH / "data/dashboard_payload.json").read_text(encoding="utf-8"))
    assert payload["h5"]["decision"] == "exploratory_descriptive_only"
    assert payload["h5"]["label_sources"] == {"human_owner": 26, "offline_ai_knn": 144}
    assert len(payload["h5"]["correlations"]) == 2
