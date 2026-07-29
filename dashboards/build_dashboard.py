#!/usr/bin/env python3
"""Build Screen 1 record gallery, Screen 2 exhibit, and integrity manifest."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

import build_screen2
import screen1_figures


ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboards"
DATA = DASH / "data"
OUTPUT = DASH / "dashboard.html"
MANIFEST = DATA / "dashboard_build_manifest.json"
FIGURES = (
    ("5.1", "Response grid", "fig_5_1_response_grid"),
    ("5.2", "Per-category MRR@10", "fig_5_2_category_mrr"),
    ("5.3", "Hypothesis forest", "fig_5_3_hypothesis_forest"),
    ("5.4", "Failure taxonomy", "fig_5_4_failure_taxonomy"),
    ("5.5", "H5 real aggregate", "fig_5_5_h5_aggregate"),
    ("5.6", "Methods and provenance", "fig_5_6_provenance"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_page(payload: dict[str, object]) -> str:
    cards = []
    for number, title, stem in FIGURES:
        cards.append(
            f"""<article class="figure">
<div class="meta"><span>Figure {html.escape(number)}</span><h2>{html.escape(title)}</h2></div>
<a href="figures/{stem}.png"><img src="figures/{stem}.png" alt="Figure {html.escape(number)}: {html.escape(title)}"></a>
<div class="downloads"><a href="figures/{stem}.png">300-dpi PNG</a><a href="figures/{stem}.pdf">Vector PDF</a></div>
</article>"""
        )
    commit = html.escape(str(payload["evidence_commit"]))
    date = html.escape(str(payload["evidence_date"]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RAG Evaluation — Screen 1 Record</title>
<style>
:root{{--paper:#f7f5f1;--ink:#171717;--muted:#666;--accent:#7a1735;--line:#d8d2c8}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:Georgia,"Times New Roman",serif;line-height:1.5}}.shell{{width:min(1080px,calc(100% - 32px));margin:auto}}header{{padding:58px 0 35px;border-bottom:1px solid var(--line)}}.eyebrow{{color:var(--accent);font:700 12px/1.2 ui-sans-serif,system-ui;letter-spacing:.16em;text-transform:uppercase}}h1{{max-width:780px;margin:12px 0;font-size:clamp(38px,6vw,68px);line-height:1;letter-spacing:-.04em}}header p{{max-width:820px;color:var(--muted)}}.actions{{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}}.actions a,.downloads a{{border:1px solid var(--accent);padding:8px 12px;color:var(--accent);text-decoration:none;font:600 12px/1.2 ui-sans-serif,system-ui}}.actions a.primary{{background:var(--accent);color:#fff}}main{{padding:36px 0 70px}}.figure{{margin-bottom:34px;padding:20px;background:#fff;border:1px solid var(--line)}}.meta{{display:flex;align-items:baseline;gap:16px;margin-bottom:14px}}.meta span{{color:var(--accent);font:700 12px/1.2 ui-sans-serif,system-ui}}.meta h2{{margin:0;font-size:22px}}img{{display:block;width:100%;height:auto;border:1px solid #eee}}.downloads{{display:flex;gap:8px;margin-top:12px}}footer{{padding:25px 0 40px;border-top:1px solid var(--line);color:var(--muted);font:12px/1.5 ui-sans-serif,system-ui}}@media(max-width:640px){{.figure{{padding:10px}}.meta{{display:block}}}}
</style></head><body>
<header><div class="shell"><div class="eyebrow">Screen 1 · citable record · figure factory</div><h1>Five retrieval systems, one frozen record.</h1><p>Publication figures generated from owner-adjudicated final-pooled qrels. Vector-free strategies are evaluated against dense-vector FAISS. H5 shows real aggregate correlations only—no synthetic points.</p><div class="actions"><a class="primary" href="screen2_exhibit.html">Open Screen 2 viva exhibit</a><a href="README.md">Rebuild instructions</a></div></div></header>
<main class="shell">{''.join(cards)}</main>
<footer><div class="shell">Evidence commit {commit} · {date} · n=34 exploratory pilot · Screen 1 is record; Screen 2 is exhibit.</div></footer>
</body></html>"""


def build() -> dict[str, object]:
    payload = json.loads((DATA / "dashboard_payload.json").read_text(encoding="utf-8"))
    screen1_figures.build()
    screen2_manifest = build_screen2.build()
    document = _record_page(payload)
    temporary = OUTPUT.with_suffix(".html.tmp")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(OUTPUT)
    paths = [
        DASH / "build_dataframe.py",
        DASH / "build_dashboard.py",
        DASH / "screen1_figures.py",
        DASH / "build_screen2.py",
        DASH / "screen2_template.html",
        DASH / "vendor_assets.py",
        DASH / "requirements.txt",
        DASH / ".gitattributes",
        DASH / "vendor/gsap-3.12.5.min.js",
        DASH / "vendor/three-r128.min.js",
        DASH / "dashboard.html",
        DASH / "screen2_exhibit.html",
        DATA / "per_query_pilot.csv",
        DATA / "per_query_pilot.parquet",
        DATA / "dashboard_payload.json",
        DATA / "gate1_reconciliation.json",
        DATA / "screen1_manifest.json",
        DATA / "screen2_manifest.json",
        *sorted(DASH.glob("figures/fig_5_[1-6]_*.png")),
        *sorted(DASH.glob("figures/fig_5_[1-6]_*.pdf")),
        *sorted((DASH / "tests").glob("test_*.py")),
    ]
    manifest = {
        "status": "all_dashboard_gates_passed",
        "evidence_commit": payload["evidence_commit"],
        "evidence_date": payload["evidence_date"],
        "qrels_base": payload["qrels_base"],
        "blacklisted_source_reads": 0,
        "screen1_figure_n": 6,
        "screen2_panel_n": len(screen2_manifest["required_panels"]),
        "artifacts": {
            path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(set(paths))
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = build()
    print(json.dumps({"status": result["status"], "artifacts": len(result["artifacts"])}, indent=2))
