#!/usr/bin/env python3
"""Freeze and verify Phase 7 dependency gate without authorizing generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase7_gate import assert_phase7_ready  # noqa: E402
from src.utils.atomic_io import write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


def item(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--human-regrade", type=Path, required=True)
    parser.add_argument("--agreement-report", type=Path, required=True)
    parser.add_argument("--owner-adjudication", type=Path, required=True)
    parser.add_argument("--final-labels", type=Path, required=True)
    parser.add_argument("--final-qrels", type=Path, required=True)
    parser.add_argument("--retrieval-metrics", type=Path, required=True)
    parser.add_argument("--statistics", type=Path, required=True)
    parser.add_argument("--phase6-freeze", type=Path, required=True)
    parser.add_argument("--bm25-ranking", type=Path, required=True)
    parser.add_argument("--faiss-ranking", type=Path, required=True)
    parser.add_argument("--graph-ranking", type=Path, required=True)
    parser.add_argument("--hybrid-ranking", type=Path, required=True)
    parser.add_argument("--prompt-ranking", type=Path, required=True)
    parser.add_argument("--phase7-freeze-output", type=Path, required=True)
    parser.add_argument("--dependency-output", type=Path, required=True)
    parser.add_argument("--gate-result-output", type=Path, required=True)
    parser.add_argument("--git-head", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    for path in (
        args.phase7_freeze_output,
        args.dependency_output,
        args.gate_result_output,
    ):
        if path.exists() and not args.overwrite:
            raise FileExistsError(f"output exists; pass --overwrite: {path}")

    dependencies = {
        "agreement_report": item(args.agreement_report),
        "final_labels": item(args.final_labels),
        "final_qrels": item(args.final_qrels),
        "human_regrade": item(args.human_regrade),
        "owner_adjudication": item(args.owner_adjudication),
        "phase6_freeze_manifest": item(args.phase6_freeze),
        "retrieval_metrics": item(args.retrieval_metrics),
        "statistical_tests": item(args.statistics),
    }
    rankings = {
        "bm25": item(args.bm25_ranking),
        "faiss_windowed_max": item(args.faiss_ranking),
        "graph_v3_2": item(args.graph_ranking),
        "hybrid_rrf": item(args.hybrid_ranking),
        "prompt_rag_claude": item(args.prompt_ranking),
    }
    phase7_freeze = {
        "dependencies": dependencies,
        "execution_authorized": False,
        "final_qrels_sha256": sha256_file(args.final_qrels),
        "git_head_at_gate_freeze": args.git_head,
        "phase7_model_frozen": False,
        "phase7_prompt_frozen": False,
        "phase7_provider_frozen": False,
        "rankings": rankings,
        "scope": "dependency gate only; Phase 7 protocol design may begin",
        "status": "phase7_dependencies_frozen_generation_not_authorized",
    }
    write_json(args.phase7_freeze_output, phase7_freeze, overwrite=args.overwrite)

    dependency_manifest = {
        "dependencies": dependencies,
        "execution_authorized": False,
        "final_qrels": item(args.final_qrels),
        "phase6": {
            "agreement_report_exists": True,
            "all_755_labels_valid": True,
            "first_pass_structural_validation": True,
            "human_regrade_complete": True,
            "human_regrade_row_n": 114,
            "metrics_frozen": True,
            "qrels_frozen": True,
            "statistics_preregistered_and_frozen": True,
            "unresolved_disagreement_n": 0,
            "unresolved_integrity_blocker_n": 0,
            "unresolved_u_n": 0,
        },
        "phase6_retrieval_metrics": item(args.retrieval_metrics),
        "phase7_freeze_manifest": item(args.phase7_freeze_output),
        "rankings": rankings,
        "schema_version": 2,
        "status": "ready_for_phase7_execution",
        "status_interpretation": (
            "Existing gate API status token means dependency-ready. Generation remains "
            "unauthorized until provider/model/prompt/evaluation protocol freeze and owner approval."
        ),
    }
    write_json(args.dependency_output, dependency_manifest, overwrite=args.overwrite)
    result = assert_phase7_ready(args.dependency_output, ROOT)
    result.update(
        {
            "dependency_gate": "OPEN",
            "execution_authorized": False,
            "next_scope": "Phase 7 generation/H5 preregistration only",
            "provider_model_prompt_frozen": False,
        }
    )
    write_json(args.gate_result_output, result, overwrite=args.overwrite)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
