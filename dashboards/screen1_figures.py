#!/usr/bin/env python3
"""Render six print-grade dissertation figures from verified dashboard payload."""

from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Rectangle


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dashboards/data/dashboard_payload.json"
OUT = ROOT / "dashboards/figures"
MANIFEST = ROOT / "dashboards/data/screen1_manifest.json"
ACCENT = "#7A1735"
INK = "#171717"
MID = "#656565"
LIGHT = "#D9D9D9"
PAPER = "#FFFFFF"
SYSTEMS = (
    "bm25",
    "faiss_windowed_max",
    "graph_v3_2",
    "hybrid_rrf",
    "prompt_rag_claude",
)
SHORT = {
    "bm25": "BM25",
    "faiss_windowed_max": "FAISS",
    "graph_v3_2": "Entity Graph",
    "hybrid_rrf": "Hybrid RRF",
    "prompt_rag_claude": "Prompt-RAG",
}
CATEGORY_LABELS = {
    "exact_lookup": "Exact lookup",
    "terminology": "Terminology",
    "paraphrase": "Paraphrase",
    "entity_relation": "Entity relation",
    "multi_hop": "Multi-hop",
    "synthesis": "Synthesis",
}
FAILURE_LABELS = {
    "hit": "Hit (rank 1–5)",
    "near_miss": "Near miss (6–10)",
    "ranking_failure": "Ranking failure (11–50)",
    "missing_evidence": "Missing evidence (>50)",
}


def _load() -> dict[str, Any]:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    if payload.get("evidence_commit") != "7bc5bda9c6fc01964bab0247145699fe14e35175":
        raise ValueError("unexpected evidence commit")
    if payload.get("qrels_base") != "final_pooled" or len(payload.get("queries", [])) != 34:
        raise ValueError("invalid shared payload")
    return payload


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Serif",
            "font.size": 8.5,
            "axes.titlesize": 10,
            "axes.labelsize": 8.5,
            "axes.edgecolor": INK,
            "axes.linewidth": 0.55,
            "xtick.major.width": 0.5,
            "ytick.major.width": 0.5,
            "grid.linewidth": 0.4,
            "grid.color": "#D8D8D8",
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "savefig.facecolor": PAPER,
        }
    )


def _caption(fig: plt.Figure, number: str, caption: str, payload: dict[str, Any]) -> None:
    fig.text(0.01, 0.985, f"Figure {number}", ha="left", va="top", weight="bold", color=INK)
    fig.text(
        0.01,
        0.045,
        textwrap.fill(caption, width=140),
        ha="left",
        va="bottom",
        color=INK,
        fontsize=7.2,
    )
    fig.text(
        0.99,
        0.012,
        (
            f"n=34 · final_pooled owner-adjudicated qrels · seed 42 · "
            f"evidence {payload['evidence_commit'][:12]} · {payload['evidence_date']}"
        ),
        ha="right",
        va="bottom",
        color=MID,
        fontsize=6.5,
    )


def _save(fig: plt.Figure, stem: str) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{stem}.png"
    pdf = OUT / f"{stem}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight", pad_inches=0.08)
    fig.savefig(
        pdf,
        dpi=300,
        bbox_inches="tight",
        pad_inches=0.08,
        metadata={"CreationDate": None, "ModDate": None, "Creator": "screen1_figures.py"},
    )
    plt.close(fig)
    return [png, pdf]


def _response_grid(payload: dict[str, Any]) -> list[Path]:
    queries = sorted(payload["queries"], key=lambda row: (-row["difficulty"], row["query_id"]))
    matrix = np.array(
        [
            [next(item["hit_at_5"] for item in query["systems"] if item["system"] == system) for query in queries]
            for system in SYSTEMS
        ],
        dtype=float,
    )
    category_index = {key: index for index, key in enumerate(CATEGORY_LABELS)}
    strip = np.array([[category_index[query["category"]] for query in queries]])
    fig = plt.figure(figsize=(7.25, 4.15))
    grid = fig.add_gridspec(2, 1, height_ratios=[0.16, 1], hspace=0.04, top=0.86, bottom=0.22)
    strip_axis = fig.add_subplot(grid[0])
    axis = fig.add_subplot(grid[1], sharex=strip_axis)
    strip_axis.imshow(strip, aspect="auto", cmap="Greys", vmin=0, vmax=7)
    strip_axis.set_yticks([0], ["Category"])
    strip_axis.tick_params(axis="x", bottom=False, labelbottom=False)
    for spine in strip_axis.spines.values():
        spine.set_visible(False)
    axis.imshow(matrix, aspect="auto", vmin=0, vmax=1, cmap=ListedColormap(["#ECECEC", ACCENT]))
    axis.set_yticks(range(len(SYSTEMS)), [SHORT[system] for system in SYSTEMS])
    axis.set_xticks(range(len(queries)), [query["query_id"] for query in queries], rotation=90)
    axis.set_xlabel("Questions sorted hardest → easiest (difficulty = 1 − systems hitting@5 / 5)")
    axis.set_title("Hit@5 response grid", pad=10)
    for row in range(len(SYSTEMS)):
        for column in range(len(queries)):
            axis.text(column, row, "●" if matrix[row, column] else "×", ha="center", va="center", color="white" if matrix[row, column] else MID, fontsize=5.5)
    _caption(
        fig,
        "5.1",
        "Response grid for five retrieval systems. Filled circles denote a pooled-relevant chunk within top five; crosses denote misses. Category strip uses ordered grey bands only as labels.",
        payload,
    )
    return _save(fig, "fig_5_1_response_grid")


def _category_mrr(payload: dict[str, Any]) -> list[Path]:
    rows = payload["category_mrr"]
    fig, axes = plt.subplots(3, 2, figsize=(7.25, 8.2), sharex=True)
    fig.subplots_adjust(top=0.90, bottom=0.20, left=0.18, right=0.97, hspace=0.36, wspace=0.52)
    for axis, category in zip(axes.flat, CATEGORY_LABELS, strict=True):
        panel = [row for row in rows if row["category"] == category]
        means = np.array([next(row["mean"] for row in panel if row["system"] == system) for system in SYSTEMS])
        lows = np.array([next(row["ci95"][0] for row in panel if row["system"] == system) for system in SYSTEMS])
        highs = np.array([next(row["ci95"][1] for row in panel if row["system"] == system) for system in SYSTEMS])
        leader = float(means.max())
        co_leaders = np.isclose(means, leader, atol=1e-12)
        y = np.arange(len(SYSTEMS))
        bars = axis.barh(y, means, color="#D0D0D0", edgecolor=[ACCENT if leader_flag else "#808080" for leader_flag in co_leaders], linewidth=[1.6 if leader_flag else 0.55 for leader_flag in co_leaders])
        axis.errorbar(means, y, xerr=[means - lows, highs - means], fmt="none", ecolor=INK, elinewidth=0.65, capsize=1.8)
        axis.set_yticks(y, [SHORT[system] + ("  †" if flag else "") for system, flag in zip(SYSTEMS, co_leaders, strict=True)])
        axis.invert_yaxis()
        axis.set_xlim(0, 1.03)
        axis.set_title(f"{CATEGORY_LABELS[category]} (n={panel[0]['query_n']})")
        axis.grid(axis="x", alpha=0.7)
        for bar, value in zip(bars, means, strict=True):
            inside = value >= 0.16
            axis.text(
                value - 0.025 if inside else value + 0.025,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.2f}",
                ha="right" if inside else "left",
                va="center",
                fontsize=6.5,
            )
    fig.supxlabel("MRR@10 with 95% whole-query bootstrap CI", y=0.13)
    fig.suptitle("Per-category MRR@10 — † marks every tied row leader", y=0.945, fontsize=11)
    _caption(
        fig,
        "5.2",
        "Category performance under final pooled qrels. CIs use 10,000 whole-query bootstrap samples (seed 42). Ties are retained as co-leaders; small category n yields wide intervals.",
        payload,
    )
    return _save(fig, "fig_5_2_category_mrr")


def _forest(payload: dict[str, Any]) -> list[Path]:
    rows = list(reversed(payload["forest"]))
    labels = [f"{row['hypothesis']}  {row['comparison']}" for row in rows]
    effects = np.array([row["effect"] for row in rows], dtype=float)
    lows = np.array([row["ci_low"] for row in rows], dtype=float)
    highs = np.array([row["ci_high"] for row in rows], dtype=float)
    fig, axis = plt.subplots(figsize=(7.25, 5.15))
    fig.subplots_adjust(top=0.87, bottom=0.17, left=0.38, right=0.97)
    y = np.arange(len(rows))
    axis.errorbar(effects, y, xerr=[effects - lows, highs - effects], fmt="o", color=ACCENT, ecolor=INK, elinewidth=0.7, capsize=2, markersize=4)
    axis.axvline(0, color=INK, linewidth=0.75)
    h1_index = next(index for index, row in enumerate(rows) if row["hypothesis"] == "H1")
    axis.add_patch(Rectangle((-0.05, h1_index - 0.38), 0.10, 0.76, color=ACCENT, alpha=0.10, linewidth=0))
    axis.set_xlim(-0.85, 0.65)
    axis.set_yticks(y, labels)
    axis.set_xlabel("Effect: left system minus right system (MRR@10)")
    axis.set_title("Preregistered H1–H4 effects and 95% intervals")
    axis.grid(axis="x", alpha=0.7)
    for index, row in enumerate(rows):
        verdict = row["verdict"]
        if row["hypothesis"] != "H1":
            verdict += f"; Holm p={row['adjusted_p']:.3g}"
        axis.text(
            0.63,
            index,
            verdict,
            ha="right",
            va="center",
            fontsize=6.2,
            color=MID,
            bbox={"facecolor": PAPER, "edgecolor": "none", "pad": 0.8},
        )
    _caption(
        fig,
        "5.3",
        "H1 equivalence uses the preregistered ±0.05 margin (shaded on H1 row) and is inconclusive. H2–H4 directional tests show Holm-adjusted decisions; supported comparison does not imply H4 overall support.",
        payload,
    )
    return _save(fig, "fig_5_3_hypothesis_forest")


def _failure_taxonomy(payload: dict[str, Any]) -> list[Path]:
    fig, axes = plt.subplots(2, 2, figsize=(7.25, 5.75), sharex=True)
    fig.subplots_adjust(top=0.88, bottom=0.18, left=0.16, right=0.985, hspace=0.34, wspace=0.19)
    for axis, failure in zip(axes.flat, FAILURE_LABELS, strict=True):
        panel = [row for row in payload["failures"] if row["failure_type"] == failure]
        values = np.array([next(row["proportion"] for row in panel if row["system"] == system) for system in SYSTEMS])
        counts = [next(row["count"] for row in panel if row["system"] == system) for system in SYSTEMS]
        lows = np.array([next(row["ci95"][0] for row in panel if row["system"] == system) for system in SYSTEMS])
        highs = np.array([next(row["ci95"][1] for row in panel if row["system"] == system) for system in SYSTEMS])
        y = np.arange(len(SYSTEMS))
        bars = axis.barh(y, values, color=[ACCENT if count else "#E2E2E2" for count in counts], alpha=0.85)
        axis.errorbar(values, y, xerr=[values - lows, highs - values], fmt="none", ecolor=INK, capsize=1.8, elinewidth=0.65)
        axis.set_yticks(y, [SHORT[system] for system in SYSTEMS])
        axis.invert_yaxis()
        axis.set_xlim(0, 1.02)
        axis.set_title(FAILURE_LABELS[failure])
        axis.grid(axis="x", alpha=0.7)
        for bar, count in zip(bars, counts, strict=True):
            axis.text(min(bar.get_width() + 0.025, 0.94), bar.get_y() + bar.get_height() / 2, f"{count}/34", va="center", fontsize=6.5)
    fig.suptitle("Rank-based failure taxonomy", y=0.945, fontsize=11)
    fig.supxlabel("Query proportion with 95% whole-query bootstrap CI")
    _caption(
        fig,
        "5.4",
        "Failure position separates top-five hits, ranks 6–10 near misses, ranks 11–50 ranking failures, and absence of pooled-relevant evidence from the returned list. Exact counts appear beside bars.",
        payload,
    )
    return _save(fig, "fig_5_4_failure_taxonomy")


def _h5(payload: dict[str, Any]) -> list[Path]:
    rows = payload["h5"]["correlations"]
    labels = ["MRR@10 ↔ faithfulness", "Complete-evidence recall@10 ↔ completeness"]
    effects = np.array([row["spearman_rho"] for row in rows], dtype=float)
    lows = np.array([row["ci95"][0] for row in rows], dtype=float)
    highs = np.array([row["ci95"][1] for row in rows], dtype=float)
    fig, axis = plt.subplots(figsize=(7.25, 3.5))
    fig.subplots_adjust(top=0.82, bottom=0.25, left=0.42, right=0.96)
    y = np.arange(2)[::-1]
    axis.errorbar(effects, y, xerr=[effects - lows, highs - effects], fmt="o", color=ACCENT, ecolor=INK, capsize=3, markersize=5)
    axis.axvline(0, color=INK, linewidth=0.75)
    axis.set_yticks(y, labels)
    axis.set_ylim(-0.25, 1.25)
    axis.set_xlim(-0.25, 0.62)
    axis.set_xlabel("Spearman ρ with 95% whole-query bootstrap CI")
    axis.set_title("H5: retrieval quality and generated-answer quality")
    axis.grid(axis="x", alpha=0.7)
    for x, yy, row in zip(effects, y, rows, strict=True):
        axis.text(x + 0.025, yy, f"ρ={x:+.3f}\n[{row['ci95'][0]:+.3f}, {row['ci95'][1]:+.3f}]", va="center", fontsize=7)
    mix = payload["h5"]["label_sources"]
    _caption(
        fig,
        "5.5",
        f"Real aggregate H5 statistics; no synthetic per-answer points. Label mix: {mix['human_owner']} human-owner records + {mix['offline_ai_knn']} offline-AI labels. Exploratory/descriptive only; association is not causation.",
        payload,
    )
    return _save(fig, "fig_5_5_h5_aggregate")


def _provenance(payload: dict[str, Any]) -> list[Path]:
    fig = plt.figure(figsize=(7.25, 4.0))
    axis = fig.add_axes([0.06, 0.18, 0.88, 0.66])
    axis.axis("off")
    title = "Methods and provenance"
    body = (
        "Study boundary\n"
        "22 documents · 140 chunks · 34 owner-approved questions · five systems · six categories\n"
        "Two documents supply 65/140 chunks: corpus concentration limits external validity.\n\n"
        "Comparison\n"
        "Vector-free strategies: BM25, Entity-Co-occurrence Graph, Hybrid RRF, Prompt-RAG reranker.\n"
        "Dense-vector baseline: FAISS windowed-max. Prompt-RAG reranks frozen BM25 top-50; it is not a generator.\n\n"
        "Evidence contract\n"
        "Primary qrels: final_pooled owner-adjudicated · bootstrap: 10,000 whole-query samples, seed 42.\n"
        "H1–H4 read from preregistered seed-42 results. H5 uses real aggregate correlations from frozen evaluation.\n"
        "Invalid seed-123 statistics and INVALID-seed123 qrels were blocked before read.\n\n"
        "Interpretation\n"
        "Exploratory pilot only. No composite metric, universal winner, deployed router, or causal H5 claim.\n"
        "Screen 1 is the citable record; Screen 2 is a viva exhibit and is not cited as evidence."
    )
    axis.text(0, 1, title, va="top", ha="left", fontsize=12, weight="bold", color=INK)
    axis.text(0, 0.90, body, va="top", ha="left", fontsize=8.2, linespacing=1.45, color=INK)
    _caption(
        fig,
        "5.6",
        "Frozen provenance block for every dashboard figure. Source hashes and exact reproduction commands are recorded in dashboards/data/gate1_reconciliation.json and dashboards/RESULTS_LOG.md.",
        payload,
    )
    return _save(fig, "fig_5_6_provenance")


def build() -> dict[str, str]:
    """Build all six figures and return stable artifact hashes."""

    payload = _load()
    _style()
    artifacts: list[Path] = []
    for builder in (_response_grid, _category_mrr, _forest, _failure_taxonomy, _h5, _provenance):
        artifacts.extend(builder(payload))
    hashes = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(artifacts)
    }
    MANIFEST.write_text(
        json.dumps(
            {
                "artifact_hashes": hashes,
                "evidence_commit": payload["evidence_commit"],
                "figure_n": 6,
                "formats": ["pdf", "png"],
                "png_dpi": 300,
                "qrels_base": payload["qrels_base"],
                "status": "gate2_passed",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return hashes


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
