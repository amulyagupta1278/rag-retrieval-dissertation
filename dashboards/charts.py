"""Shared analysis and dual-render chart functions for V2 pilot dashboard."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.colors import ListedColormap
from plotly.subplots import make_subplots


SYSTEMS = (
    "bm25",
    "faiss_windowed_max",
    "graph_v3_2",
    "hybrid_rrf",
    "prompt_rag_claude",
)
SYSTEM_LABELS = {
    "bm25": "BM25",
    "faiss_windowed_max": "FAISS windowed-max",
    "graph_v3_2": "Entity Graph",
    "hybrid_rrf": "Hybrid RRF",
    "prompt_rag_claude": "Prompt-RAG reranker",
}
CATEGORIES = (
    "exact_lookup",
    "terminology",
    "paraphrase",
    "entity_relation",
    "multi_hop",
    "synthesis",
)
CATEGORY_LABELS = {
    "exact_lookup": "Exact lookup",
    "terminology": "Terminology",
    "paraphrase": "Paraphrase",
    "entity_relation": "Entity relation",
    "multi_hop": "Multi-hop",
    "synthesis": "Synthesis",
}
METRICS = {
    "mrr_at_10": "MRR@10",
    "recall_at_10": "Recall@10",
    "ndcg_graded_at_10": "Graded nDCG@10",
}
PILOT_NOTE = "n=34 exploratory pilot · final_pooled owner-adjudicated qrels"
GARNET = "#7A0019"
SYSTEM_COLORS = {
    "bm25": "#7A0019",
    "faiss_windowed_max": "#2563A8",
    "graph_v3_2": "#5F6B3A",
    "hybrid_rrf": "#C46A1A",
    "prompt_rag_claude": "#6B4FA1",
}
CATEGORY_COLORS = {
    "exact_lookup": "#7A0019",
    "terminology": "#B14A5F",
    "paraphrase": "#2563A8",
    "entity_relation": "#5F6B3A",
    "multi_hop": "#C46A1A",
    "synthesis": "#6B4FA1",
}


def configure_matplotlib() -> None:
    """Apply submission-friendly restrained Matplotlib style."""

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "axes.linewidth": 0.6,
            "grid.linewidth": 0.4,
            "savefig.bbox": "tight",
        }
    )


def save_static(fig: plt.Figure, figures_dir: Path, stem: str) -> None:
    """Save one Matplotlib figure as 300-dpi PNG and vector PDF."""

    figures_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(figures_dir / f"{stem}.png", dpi=300, facecolor="white")
    fig.savefig(
        figures_dir / f"{stem}.pdf",
        dpi=300,
        facecolor="white",
        metadata={
            "CreationDate": None,
            "Creator": "rag-retrieval-dissertation dashboards",
            "ModDate": None,
            "Producer": "Matplotlib",
        },
    )
    plt.close(fig)


def bootstrap_category_intervals(
    frame: pd.DataFrame, *, samples: int = 10_000, seed: int = 42
) -> pd.DataFrame:
    """Compute deterministic whole-query percentile intervals per category/system/metric."""

    generator = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for category in CATEGORIES:
        for system in SYSTEMS:
            subset = frame.loc[
                (frame["category"] == category) & (frame["system"] == system)
            ].sort_values("query_id")
            query_n = len(subset)
            if query_n == 0:
                raise ValueError(f"empty category/system slice: {category}/{system}")
            indices = generator.integers(0, query_n, size=(samples, query_n))
            for metric in METRICS:
                values = subset[metric].to_numpy(dtype=float)
                means = values[indices].mean(axis=1)
                rows.append(
                    {
                        "category": category,
                        "system": system,
                        "metric": metric,
                        "query_n": query_n,
                        "mean": float(values.mean()),
                        "ci_low": float(np.percentile(means, 2.5)),
                        "ci_high": float(np.percentile(means, 97.5)),
                        "bootstrap_samples": samples,
                        "seed": seed,
                    }
                )
    return pd.DataFrame(rows)


def category_leader_figures(
    frame: pd.DataFrame, intervals: pd.DataFrame
) -> tuple[go.Figure, plt.Figure]:
    """Render switchable Plotly and static MRR category leader matrices."""

    plot = go.Figure()
    for metric_index, (metric, label) in enumerate(METRICS.items()):
        panel = intervals.loc[intervals["metric"] == metric]
        z: list[list[float]] = []
        text: list[list[str]] = []
        custom: list[list[list[float]]] = []
        for category in CATEGORIES:
            category_panel = panel.loc[panel["category"] == category].set_index("system")
            means = [float(category_panel.loc[system, "mean"]) for system in SYSTEMS]
            leader = max(means)
            z.append(means)
            row_text: list[str] = []
            row_custom: list[list[float]] = []
            for system, mean in zip(SYSTEMS, means, strict=True):
                low = float(category_panel.loc[system, "ci_low"])
                high = float(category_panel.loc[system, "ci_high"])
                prefix = "▣ " if abs(mean - leader) < 1e-12 else ""
                row_text.append(f"{prefix}{mean:.2f}")
                row_custom.append([low, high, int(category_panel.loc[system, "query_n"])])
            text.append(row_text)
            custom.append(row_custom)
        plot.add_trace(
            go.Heatmap(
                z=z,
                x=[SYSTEM_LABELS[system] for system in SYSTEMS],
                y=[CATEGORY_LABELS[category] for category in CATEGORIES],
                zmin=0,
                zmax=1,
                colorscale=[[0, "#F7F1F2"], [1, "#D58A97"]],
                text=text,
                texttemplate="%{text}",
                customdata=custom,
                hovertemplate=(
                    "%{y}<br>%{x}<br>mean=%{z:.3f}<br>95% CI=[%{customdata[0]:.3f}, "
                    "%{customdata[1]:.3f}]<br>N=%{customdata[2]}<extra></extra>"
                ),
                colorbar={"title": label},
                visible=metric_index == 0,
            )
        )
    buttons = []
    for index, label in enumerate(METRICS.values()):
        visible = [position == index for position in range(len(METRICS))]
        buttons.append(
            {
                "label": label,
                "method": "update",
                "args": [
                    {"visible": visible},
                    {"title": {"text": f"Category leaders — {label}<br><sup>{PILOT_NOTE}; ▣ row leader; category N=4–6</sup>"}},
                ],
            }
        )
    plot.update_layout(
        title={"text": f"Category leaders — MRR@10<br><sup>{PILOT_NOTE}; ▣ row leader; category N=4–6</sup>"},
        updatemenus=[{"buttons": buttons, "direction": "down", "x": 0, "y": 1.16}],
        margin={"l": 115, "r": 20, "t": 95, "b": 70},
        height=500,
    )

    mrr = intervals.loc[intervals["metric"] == "mrr_at_10"]
    matrix = np.array(
        [
            [float(mrr.loc[(mrr["category"] == category) & (mrr["system"] == system), "mean"].iloc[0]) for system in SYSTEMS]
            for category in CATEGORIES
        ]
    )
    low_matrix = np.array(
        [
            [float(mrr.loc[(mrr["category"] == category) & (mrr["system"] == system), "ci_low"].iloc[0]) for system in SYSTEMS]
            for category in CATEGORIES
        ]
    )
    high_matrix = np.array(
        [
            [float(mrr.loc[(mrr["category"] == category) & (mrr["system"] == system), "ci_high"].iloc[0]) for system in SYSTEMS]
            for category in CATEGORIES
        ]
    )
    static, axis = plt.subplots(figsize=(8.2, 4.5))
    image = axis.imshow(matrix, vmin=0, vmax=1, cmap="Reds", aspect="auto")
    for row in range(len(CATEGORIES)):
        for column in range(len(SYSTEMS)):
            text_color = "white" if matrix[row, column] >= 0.65 else "black"
            axis.text(
                column,
                row,
                f"{matrix[row, column]:.2f}\n[{low_matrix[row, column]:.2f}, {high_matrix[row, column]:.2f}]",
                ha="center",
                va="center",
                fontsize=7,
                color=text_color,
            )
            if abs(matrix[row, column] - matrix[row].max()) < 1e-12:
                axis.add_patch(
                    plt.Rectangle(
                        (column - 0.49, row - 0.49),
                        0.98,
                        0.98,
                        fill=False,
                        lw=1.8,
                        ec="#241D1F",
                    )
                )
    axis.set_xticks(range(len(SYSTEMS)), [SYSTEM_LABELS[system] for system in SYSTEMS], rotation=22, ha="right")
    axis.set_yticks(range(len(CATEGORIES)), [CATEGORY_LABELS[category] for category in CATEGORIES])
    axis.set_title(f"Category leaders — MRR@10\n{PILOT_NOTE}; category N=4–6")
    static.colorbar(image, ax=axis, fraction=0.035, pad=0.02, label="MRR@10")
    static.tight_layout()
    return plot, static


def discrimination_audit(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute small-N descriptive item discrimination across five systems."""

    ability = frame.groupby("system")["mrr_at_10"].mean().reindex(SYSTEMS)
    rows: list[dict[str, Any]] = []
    for query_id, query_panel in frame.groupby("query_id", sort=True):
        ordered = query_panel.set_index("system").reindex(SYSTEMS)
        hits = ordered["hit_at_5"].to_numpy(dtype=float)
        if np.std(hits) == 0:
            correlation = np.nan
            status = "undefined_all_same"
            flagged = True
        else:
            correlation = float(np.corrcoef(ability.to_numpy(dtype=float), hits)[0, 1])
            flagged = correlation <= 0.10
            status = "flag_negative_or_near_zero" if flagged else "positive"
        row: dict[str, Any] = {
            "query_id": query_id,
            "query_text": ordered["query_text"].iloc[0],
            "category": ordered["category"].iloc[0],
            "difficulty": float(ordered["difficulty"].iloc[0]),
            "point_biserial": correlation,
            "flagged": flagged,
            "status": status,
        }
        for system in SYSTEMS:
            row[f"{system}_gold_rank"] = int(ordered.loc[system, "gold_rank"])
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["flagged", "point_biserial", "query_id"], ascending=[False, True, True], na_position="first"
    )


def item_response_figures(frame: pd.DataFrame) -> tuple[go.Figure, plt.Figure]:
    """Render five-system hit matrix sorted by empirical query difficulty."""

    query_meta = (
        frame[["query_id", "query_text", "category", "difficulty"]]
        .drop_duplicates()
        .sort_values(["difficulty", "query_id"], ascending=[False, True])
    )
    query_order = query_meta["query_id"].tolist()
    system_order = (
        frame.groupby("system")["mrr_at_10"].mean().sort_values(ascending=False).index.tolist()
    )
    matrix = (
        frame.pivot(index="system", columns="query_id", values="hit_at_5")
        .reindex(index=system_order, columns=query_order)
        .to_numpy(dtype=float)
    )
    query_lookup = query_meta.set_index("query_id")
    categories = [query_lookup.loc[query_id, "category"] for query_id in query_order]
    category_codes = [[CATEGORIES.index(category) for category in categories]]
    hover = [
        [
            f"{query_id}<br>{query_lookup.loc[query_id, 'query_text']}<br>difficulty={query_lookup.loc[query_id, 'difficulty']:.2f}"
            for query_id in query_order
        ]
        for _ in system_order
    ]

    plot = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.10, 0.90], vertical_spacing=0.02)
    plot.add_trace(
        go.Heatmap(
            z=category_codes,
            x=query_order,
            y=["Category"],
            colorscale=[
                [index / 5, CATEGORY_COLORS[category]]
                for index, category in enumerate(CATEGORIES)
                for _ in (0, 1)
            ],
            showscale=False,
            hovertemplate="%{x}<extra>category band</extra>",
        ),
        row=1,
        col=1,
    )
    plot.add_trace(
        go.Heatmap(
            z=matrix,
            x=query_order,
            y=[SYSTEM_LABELS[system] for system in system_order],
            zmin=0,
            zmax=1,
            colorscale=[[0, "#B64A4A"], [1, "#3A8B5B"]],
            text=hover,
            hovertemplate="%{y}<br>%{text}<br>%{z}<extra>hit@5</extra>",
            colorbar={"title": "Hit@5", "tickvals": [0, 1], "ticktext": ["miss", "hit"]},
        ),
        row=2,
        col=1,
    )
    plot.update_layout(
        title={"text": f"Item-response matrix — hardest queries first<br><sup>{PILOT_NOTE}; descriptive only, no 2PL/3PL IRT</sup>"},
        height=470,
        margin={"l": 145, "r": 30, "t": 80, "b": 70},
    )
    plot.update_xaxes(tickangle=90, tickfont={"size": 8}, row=2, col=1)

    static, axes = plt.subplots(2, 1, figsize=(11, 4.8), gridspec_kw={"height_ratios": [0.12, 0.88]}, sharex=True)
    category_cmap = ListedColormap([CATEGORY_COLORS[category] for category in CATEGORIES])
    axes[0].imshow(category_codes, aspect="auto", cmap=category_cmap, vmin=0, vmax=5)
    axes[0].set_yticks([0], ["Category"])
    axes[1].imshow(matrix, aspect="auto", cmap=ListedColormap(["#B64A4A", "#3A8B5B"]), vmin=0, vmax=1)
    axes[1].set_yticks(range(len(system_order)), [SYSTEM_LABELS[system] for system in system_order])
    axes[1].set_xticks(range(len(query_order)), query_order, rotation=90)
    static.suptitle(f"Item-response matrix — hardest queries first\n{PILOT_NOTE}; no 2PL/3PL IRT")
    static.tight_layout()
    return plot, static


def forest_rows(statistics: dict[str, Any]) -> pd.DataFrame:
    """Extract preregistered MRR@10 effect rows without recomputation."""

    rows: list[dict[str, Any]] = []
    h1 = statistics["h1_equivalence"]["primary_result"]
    rows.append(
        {
            "hypothesis": "H1",
            "comparison": "BM25 − FAISS · exact+terminology",
            "effect": h1["effect_left_minus_right"],
            "ci_low": h1["ci95"][0],
            "ci_high": h1["ci95"][1],
            "verdict": statistics["h1_equivalence"]["verdict"],
        }
    )
    labels = {
        "faiss_windowed_max_minus_bm25": "FAISS − BM25",
        "graph_v3_2_minus_bm25": "Graph − BM25",
        "graph_v3_2_minus_faiss_windowed_max": "Graph − FAISS",
        "hybrid_rrf_minus_bm25": "Hybrid − BM25",
        "hybrid_rrf_minus_faiss_windowed_max": "Hybrid − FAISS",
        "hybrid_rrf_minus_graph_v3_2": "Hybrid − Graph",
        "hybrid_rrf_minus_prompt_rag_claude": "Hybrid − Prompt-RAG",
    }
    for record in statistics["holm_directional_tests"]:
        if record["metric"] != "mrr_at_10":
            continue
        bootstrap = record["bootstrap"]
        rows.append(
            {
                "hypothesis": record["hypothesis"],
                "comparison": f"{labels[record['comparison']]} · {record['slice']}",
                "effect": bootstrap["effect_left_minus_right"],
                "ci_low": bootstrap["ci95"][0],
                "ci_high": bootstrap["ci95"][1],
                "verdict": "supported" if record["holm_reject_at_0_05"] else "not supported",
            }
        )
    return pd.DataFrame(rows)


def hypothesis_forest_figures(rows: pd.DataFrame) -> tuple[go.Figure, plt.Figure]:
    """Render authoritative preregistered effect/interval forest."""

    ordered = rows.iloc[::-1].reset_index(drop=True)
    labels = [f"{row.hypothesis}: {row.comparison}" for row in ordered.itertuples()]
    plot = go.Figure(
        go.Scatter(
            x=ordered["effect"],
            y=labels,
            mode="markers+text",
            text=ordered["verdict"],
            textposition="middle right",
            marker={"color": GARNET, "size": 9},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": ordered["ci_high"] - ordered["effect"],
                "arrayminus": ordered["effect"] - ordered["ci_low"],
                "color": "#555555",
            },
            customdata=np.stack([ordered["ci_low"], ordered["ci_high"]], axis=1),
            hovertemplate="%{y}<br>effect=%{x:.3f}<br>95% CI=[%{customdata[0]:.3f}, %{customdata[1]:.3f}]<extra></extra>",
        )
    )
    plot.add_vline(x=0, line_width=1, line_color="#333333")
    plot.update_layout(
        title={"text": f"Preregistered H1–H4 MRR@10 effects<br><sup>{PILOT_NOTE}; seed 42; Holm directional family where applicable</sup>"},
        xaxis_title="Left system minus right system",
        height=600,
        margin={"l": 260, "r": 115, "t": 80, "b": 55},
    )

    static, axis = plt.subplots(figsize=(9, 5.4))
    y = np.arange(len(ordered))
    axis.errorbar(
        ordered["effect"],
        y,
        xerr=[ordered["effect"] - ordered["ci_low"], ordered["ci_high"] - ordered["effect"]],
        fmt="o",
        color=GARNET,
        ecolor="#555555",
        capsize=2,
    )
    axis.axvline(0, color="#333333", lw=0.8)
    axis.set_yticks(y, labels)
    axis.set_xlabel("Left system minus right system")
    axis.set_title(f"Preregistered H1–H4 MRR@10 effects\n{PILOT_NOTE}; seed 42")
    axis.grid(axis="x", alpha=0.3)
    static.tight_layout()
    return plot, static


def rank_failure_figures(frame: pd.DataFrame) -> tuple[go.Figure, plt.Figure]:
    """Render gold-rank drilldown and failure taxonomy."""

    query_order = (
        frame[["query_id", "difficulty"]]
        .drop_duplicates()
        .sort_values(["difficulty", "query_id"], ascending=[False, True])["query_id"]
        .tolist()
    )
    failures = (
        frame.groupby(["system", "failure_type"]).size().unstack(fill_value=0).reindex(SYSTEMS)
    )
    failure_order = ["hit", "near_miss", "ranking_failure", "missing_evidence"]
    for failure in failure_order:
        if failure not in failures:
            failures[failure] = 0

    plot = make_subplots(rows=1, cols=2, column_widths=[0.68, 0.32], subplot_titles=("First relevant rank", "Failure taxonomy"))
    x_positions = {query_id: index for index, query_id in enumerate(query_order)}
    for system in SYSTEMS:
        subset = frame.loc[frame["system"] == system].set_index("query_id").loc[query_order]
        y = subset["gold_rank"].replace(999, 55)
        plot.add_trace(
            go.Scatter(
                x=[x_positions[query_id] for query_id in query_order],
                y=y,
                mode="markers",
                name=SYSTEM_LABELS[system],
                marker={"color": SYSTEM_COLORS[system], "size": 7},
                text=query_order,
                hovertemplate="%{text}<br>rank=%{y}<extra>%{fullData.name}</extra>",
            ),
            row=1,
            col=1,
        )
    failure_colors = {"hit": "#3A8B5B", "near_miss": "#D2A23C", "ranking_failure": "#C46A1A", "missing_evidence": "#B64A4A"}
    for failure in failure_order:
        plot.add_trace(
            go.Bar(
                x=[SYSTEM_LABELS[system] for system in SYSTEMS],
                y=failures[failure],
                name=failure.replace("_", " "),
                marker_color=failure_colors[failure],
                legendgroup="failure",
            ),
            row=1,
            col=2,
        )
    plot.add_hline(y=5.5, line_dash="dot", line_color="#555555", row=1, col=1)
    plot.add_hline(y=10.5, line_dash="dot", line_color="#888888", row=1, col=1)
    plot.update_yaxes(autorange="reversed", title="Gold rank (55 = not retrieved)", row=1, col=1)
    plot.update_xaxes(tickvals=list(x_positions.values()), ticktext=query_order, tickangle=90, row=1, col=1)
    plot.update_layout(
        barmode="stack",
        title={"text": f"Rank-position drilldown and failure taxonomy<br><sup>{PILOT_NOTE}</sup>"},
        height=560,
        margin={"l": 70, "r": 20, "t": 80, "b": 115},
    )

    static, axes = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [2.2, 1]})
    for system in SYSTEMS:
        subset = frame.loc[frame["system"] == system].set_index("query_id").loc[query_order]
        axes[0].scatter(range(len(query_order)), subset["gold_rank"].replace(999, 55), s=14, label=SYSTEM_LABELS[system], color=SYSTEM_COLORS[system])
    axes[0].axhline(5.5, color="#555555", lw=0.6, ls="--")
    axes[0].axhline(10.5, color="#888888", lw=0.6, ls="--")
    axes[0].invert_yaxis()
    axes[0].set_xticks(range(len(query_order)), query_order, rotation=90)
    axes[0].set_ylabel("Gold rank (55 = not retrieved)")
    bottom = np.zeros(len(SYSTEMS))
    for failure in failure_order:
        values = failures[failure].to_numpy()
        axes[1].bar([SYSTEM_LABELS[system] for system in SYSTEMS], values, bottom=bottom, label=failure.replace("_", " "), color=failure_colors[failure])
        bottom += values
    axes[1].tick_params(axis="x", rotation=70)
    axes[1].set_ylabel("Queries")
    axes[1].legend(fontsize=7)
    static.suptitle(f"Rank-position drilldown and failure taxonomy\n{PILOT_NOTE}")
    static.tight_layout()
    return plot, static


def complementarity_figures(frame: pd.DataFrame) -> tuple[go.Figure, plt.Figure, pd.DataFrame]:
    """Render exploratory Jaccard matrix and unique-correct counts."""

    correct = {
        system: set(frame.loc[(frame["system"] == system) & (frame["hit_at_5"] == 1), "query_id"])
        for system in SYSTEMS
    }
    matrix = np.zeros((len(SYSTEMS), len(SYSTEMS)))
    for row, left in enumerate(SYSTEMS):
        for column, right in enumerate(SYSTEMS):
            union = correct[left] | correct[right]
            matrix[row, column] = len(correct[left] & correct[right]) / len(union) if union else 1.0
    unique = []
    for system in SYSTEMS:
        other = set().union(*(correct[other_system] for other_system in SYSTEMS if other_system != system))
        unique.append({"system": system, "unique_correct_at_5": len(correct[system] - other)})
    unique_frame = pd.DataFrame(unique)

    plot = make_subplots(rows=1, cols=2, column_widths=[0.67, 0.33], subplot_titles=("Jaccard of hit@5 query sets", "Unique hit@5"))
    plot.add_trace(
        go.Heatmap(
            z=matrix,
            x=[SYSTEM_LABELS[system] for system in SYSTEMS],
            y=[SYSTEM_LABELS[system] for system in SYSTEMS],
            zmin=0,
            zmax=1,
            colorscale="Blues",
            text=np.vectorize(lambda value: f"{value:.2f}")(matrix),
            texttemplate="%{text}",
            hovertemplate="%{y} / %{x}<br>Jaccard=%{z:.3f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    plot.add_trace(
        go.Bar(
            x=[SYSTEM_LABELS[system] for system in SYSTEMS],
            y=unique_frame["unique_correct_at_5"],
            marker_color=[SYSTEM_COLORS[system] for system in SYSTEMS],
            showlegend=False,
        ),
        row=1,
        col=2,
    )
    plot.update_layout(
        title={"text": f"Exploratory complementarity — future-work motivation only<br><sup>{PILOT_NOTE}; no router was built or claimed</sup>"},
        height=520,
        margin={"l": 125, "r": 25, "t": 80, "b": 100},
    )
    plot.update_xaxes(tickangle=50)

    static, axes = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw={"width_ratios": [1.5, 1]})
    image = axes[0].imshow(matrix, vmin=0, vmax=1, cmap="Blues")
    for row in range(len(SYSTEMS)):
        for column in range(len(SYSTEMS)):
            axes[0].text(column, row, f"{matrix[row, column]:.2f}", ha="center", va="center")
    axes[0].set_xticks(range(len(SYSTEMS)), [SYSTEM_LABELS[system] for system in SYSTEMS], rotation=55, ha="right")
    axes[0].set_yticks(range(len(SYSTEMS)), [SYSTEM_LABELS[system] for system in SYSTEMS])
    static.colorbar(image, ax=axes[0], fraction=0.04, pad=0.03)
    axes[1].bar([SYSTEM_LABELS[system] for system in SYSTEMS], unique_frame["unique_correct_at_5"], color=[SYSTEM_COLORS[system] for system in SYSTEMS])
    axes[1].tick_params(axis="x", rotation=65)
    axes[1].set_ylabel("Unique hit@5 queries")
    static.suptitle(f"Exploratory complementarity — no router built\n{PILOT_NOTE}")
    static.tight_layout()
    return plot, static, unique_frame


def oracle_figures(frame: pd.DataFrame) -> tuple[go.Figure, plt.Figure, pd.DataFrame]:
    """Render hypothetical per-query oracle ceiling against fixed systems."""

    fixed = frame.groupby("system")["mrr_at_10"].mean().reindex(SYSTEMS)
    query_matrix = frame.pivot(index="query_id", columns="system", values="mrr_at_10").reindex(columns=SYSTEMS)
    oracle_values = query_matrix.max(axis=1).to_numpy(dtype=float)
    oracle = float(oracle_values.mean())
    generator = np.random.default_rng(42)
    indices = generator.integers(0, len(query_matrix), size=(10_000, len(query_matrix)))
    fixed_intervals: dict[str, tuple[float, float]] = {}
    for system in SYSTEMS:
        values = query_matrix[system].to_numpy(dtype=float)
        means = values[indices].mean(axis=1)
        fixed_intervals[system] = (
            float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)),
        )
    oracle_means = oracle_values[indices].mean(axis=1)
    oracle_interval = (
        float(np.percentile(oracle_means, 2.5)),
        float(np.percentile(oracle_means, 97.5)),
    )
    summary = pd.DataFrame(
        [
            {
                "system": system,
                "mrr_at_10": float(fixed[system]),
                "ci_low": fixed_intervals[system][0],
                "ci_high": fixed_intervals[system][1],
                "kind": "fixed",
            }
            for system in SYSTEMS
        ]
        + [
            {
                "system": "oracle",
                "mrr_at_10": oracle,
                "ci_low": oracle_interval[0],
                "ci_high": oracle_interval[1],
                "kind": "hypothetical",
            }
        ]
    )
    labels = [SYSTEM_LABELS.get(system, "Per-query oracle") for system in summary["system"]]
    colors = [SYSTEM_COLORS.get(system, "#555555") for system in summary["system"]]
    plot = go.Figure(
        go.Bar(
            x=labels,
            y=summary["mrr_at_10"],
            marker_color=colors,
            text=[f"{value:.3f}" for value in summary["mrr_at_10"]],
            textposition="outside",
            customdata=summary["kind"],
            error_y={
                "type": "data",
                "symmetric": False,
                "array": summary["ci_high"] - summary["mrr_at_10"],
                "arrayminus": summary["mrr_at_10"] - summary["ci_low"],
            },
            hovertemplate="%{x}<br>MRR@10=%{y:.3f}<br>%{customdata}<extra></extra>",
        )
    )
    plot.update_layout(
        title={"text": f"ORACLE upper bound — hypothetical future work<br><sup>{PILOT_NOTE}; no router was built or claimed</sup>"},
        yaxis={"title": "MRR@10", "range": [0, 1.08]},
        height=460,
        margin={"l": 60, "r": 20, "t": 80, "b": 100},
    )
    plot.update_xaxes(tickangle=35)

    static, axis = plt.subplots(figsize=(8, 4.3))
    axis.bar(
        labels,
        summary["mrr_at_10"],
        color=colors,
        yerr=[
            summary["mrr_at_10"] - summary["ci_low"],
            summary["ci_high"] - summary["mrr_at_10"],
        ],
        capsize=2,
    )
    axis.set_ylim(0, 1.08)
    axis.set_ylabel("MRR@10")
    axis.tick_params(axis="x", rotation=35)
    axis.set_title(f"ORACLE upper bound — hypothetical; no router built\n{PILOT_NOTE}")
    for index, value in enumerate(summary["mrr_at_10"]):
        axis.text(index, value + 0.02, f"{value:.3f}", ha="center")
    static.tight_layout()
    return plot, static, summary


def all_system_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Return dashboard aggregate table from primary dataframe only."""

    return (
        frame.groupby("system", sort=False)[
            ["mrr_at_10", "recall_at_10", "ndcg_graded_at_10", "ce_recall_at_10"]
        ]
        .mean()
        .reindex(SYSTEMS)
        .reset_index()
    )


def ensure_exact_systems(values: Iterable[str]) -> None:
    """Fail if a chart input does not contain exact frozen five-system panel."""

    if set(values) != set(SYSTEMS):
        raise ValueError("chart input does not contain exact five-system panel")
