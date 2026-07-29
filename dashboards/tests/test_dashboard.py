"""Gate 3 and end-to-end offline integrity tests."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboards"


def test_screen2_is_offline_complete_and_honest() -> None:
    page = (DASH / "screen2_exhibit.html").read_text(encoding="utf-8")
    assert not re.search(r"(?:src|href)=[\"']https?://|@import\s+url", page, flags=re.I)
    assert "GSAP 3.12.5" in page
    assert "Copyright 2010-2021 Three.js Authors" in page
    for panel_id in ("responses", "ability", "field", "radar", "categories", "h5", "provenance"):
        assert f'id="{panel_id}"' in page
    assert "dense-vector FAISS baseline" in page
    assert "no synthetic scatter" in page.lower()
    assert "plausible" not in page.lower()
    assert "difficulty = 1 − systems hitting@5 / 5" not in page  # Screen 1 wording only.
    assert "Harder questions sit to the right" in page
    assert "co-winner tie" in page
    assert '$("#bootBanner").hidden=true' in page
    assert page.count("<script>") == 3
    assert (DASH / "screen2_exhibit.html").stat().st_size < 1_000_000


def test_record_page_links_six_figures_and_exhibit() -> None:
    page = (DASH / "dashboard.html").read_text(encoding="utf-8")
    assert "Screen 1 · citable record" in page
    assert 'href="screen2_exhibit.html"' in page
    assert page.count("300-dpi PNG") == 6
    assert page.count("Vector PDF") == 6
    assert "H5 shows real aggregate correlations only" in page


def test_manifests_hash_every_declared_artifact() -> None:
    manifest = json.loads((DASH / "data/dashboard_build_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "all_dashboard_gates_passed"
    assert manifest["blacklisted_source_reads"] == 0
    assert manifest["evidence_commit"] == "7bc5bda9c6fc01964bab0247145699fe14e35175"
    assert manifest["screen1_figure_n"] == 6
    assert manifest["screen2_panel_n"] == 7
    for relative, expected in manifest["artifacts"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_screen2_manifest_matches_output() -> None:
    manifest = json.loads((DASH / "data/screen2_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "gate3_passed"
    assert manifest["offline_external_reference_n"] == 0
    assert manifest["output_sha256"] == hashlib.sha256((DASH / "screen2_exhibit.html").read_bytes()).hexdigest()
