#!/usr/bin/env python3
"""Build frozen Phase 5F blind contribution without relevance inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import stable_json, write_bytes, write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


BASE_COMMIT = "88c54c906e9ea4313a43664cd8b7b65e61ea5944"
RANKINGS = ROOT / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/complete_primary_rankings.jsonl"
PHASE5D_CHECKPOINT = ROOT / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/phase5d_v3_checkpoint.json"
PHASE5D_LEDGER = ROOT / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/control/ledger.json"
PHASE5D_MANIFEST = ROOT / "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full/artifact_manifest.json"
TRACE_MANIFEST = ROOT / "runs/v2/phase5d_prompt_rag_claude_v2/trace/artifact_manifest.json"
PHASE4_MANIFEST = ROOT / "runs/v2/phase4_hybrid/evaluation_manifest.json"
PHASE4_POOL_DESIGN = ROOT / "runs/v2/phase4_hybrid/pool/design.json"
EXISTING_BLIND = ROOT / "runs/v2/phase4_hybrid/pool/provisional_blind_top10_bm25_faiss_graph_hybrid.jsonl"
EXISTING_SEALED = ROOT / "runs/v2/phase4_hybrid/pool/sealed_provenance_bm25_faiss_graph_hybrid.jsonl"
OUTPUT = ROOT / "runs/v2/phase5f_prompt_rag_pool"
AUDIT = ROOT / "audits/phase5f"

EXPECTED = {
    RANKINGS: "e665aa4dc80b468a0fc2af06173ab0e6963786a578653c9a9083e6ffa6b1e04f",
    PHASE5D_CHECKPOINT: "a02ae09195e51e2a4b2b7c8d63b386dd629a4014aacb1fd8302bd2576dfc860b",
    PHASE5D_LEDGER: "c5fa15f454df97b1fb7c53080e67f00a36b7e3b034944c12f30cd0809c6d703b",
    PHASE5D_MANIFEST: "6baeb20dbff811eba17f510d7240a167d34d120b79e614379cfd93a7ddae4bc2",
    PHASE4_MANIFEST: "2fd98ead27a2eaa063776572187a19410c6b9dda3dca0ad692aee71bf1bfc498",
    PHASE4_POOL_DESIGN: "63ba9e89615396263da9d7515895f911f2d78fe750a6cc0bdbac7ce3215f4cbe",
    EXISTING_BLIND: "5c424b6a0bbca1343499621c5fd705a904eaf11c1109824c3ec6094c0dc643e2",
    EXISTING_SEALED: "f15084529a8def018747947f2d48ea14a626ddcb75e1930e19927b759bf3e1fa",
}
SYSTEM = "prompt_rag_claude_haiku_4_5_reranker"
BLIND_FIELDS = {
    "chunk_id",
    "chunk_text",
    "display_id",
    "query_id",
    "question",
    "relevance_judgment",
    "reviewer_notes",
}
FORBIDDEN_BLIND_FIELDS = {
    "contributions",
    "current_gold",
    "gold",
    "hashes",
    "lineage",
    "predicted_relevance",
    "rank",
    "score",
    "source_system",
    "system",
}
DISPLAY_RE = re.compile(r"^(v2q-\d{3})-candidate-(\d+)$")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"expected JSONL objects: {path}")
    return rows


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return "".join(stable_json(row) + "\n" for row in rows).encode("utf-8")


def verify_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    for path, digest in EXPECTED.items():
        if sha256_file(path) != digest:
            raise ValueError(f"frozen input hash mismatch: {path.relative_to(ROOT)}")
    checkpoint = load_json(PHASE5D_CHECKPOINT)
    ledger = load_json(PHASE5D_LEDGER)
    manifest = load_json(PHASE5D_MANIFEST)
    if checkpoint.get("status") != "phase5d_v3_recovery_complete_rankings_frozen":
        raise ValueError("Phase 5D completion checkpoint invalid")
    if checkpoint.get("complete_primary_rankings") != {
        "query_n": 34,
        "ranking_depth": 50,
        "trace_primary_n": 8,
        "v3_recovery_primary_n": 26,
    }:
        raise ValueError("Phase 5D ranking checkpoint counts invalid")
    if ledger.get("status") != "complete" or ledger.get("attempted_generation_request_n") != 26:
        raise ValueError("Phase 5D recovery ledger invalid")
    if len(ledger.get("completed_logical_request_ids", [])) != 26:
        raise ValueError("Phase 5D recovery completion count invalid")
    for relative, digest in manifest.get("artifact_hashes", {}).items():
        if sha256_file(ROOT / relative) != digest:
            raise ValueError(f"Phase 5D manifest mismatch: {relative}")
    design = load_json(PHASE4_POOL_DESIGN)
    if design.get("blind_sha256") != EXPECTED[EXISTING_BLIND]:
        raise ValueError("Phase 4 pool-design blind lineage invalid")
    if design.get("sealed_sha256") != EXPECTED[EXISTING_SEALED]:
        raise ValueError("Phase 4 pool-design sealed lineage invalid")
    if design.get("combined_pair_count") != 620 or design.get("owner_labels_completed") is not False:
        raise ValueError("Phase 4 pool design invalid")
    trace_hashes = load_json(TRACE_MANIFEST).get("artifact_hashes", {})
    return checkpoint, manifest, trace_hashes


def validate_rankings(
    manifest: dict[str, Any], trace_hashes: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]], dict[str, str]]:
    rows = load_jsonl(RANKINGS)
    if len(rows) != 34 or len({row.get("query_id") for row in rows}) != 34:
        raise ValueError("Prompt-RAG rankings must contain 34 unique queries")
    candidate_text: dict[str, dict[str, str]] = {}
    questions: dict[str, str] = {}
    manifest_hashes = manifest["artifact_hashes"]
    for row in rows:
        query_id = row["query_id"]
        ranking = row.get("ranking")
        if not isinstance(ranking, list) or len(ranking) != 50:
            raise ValueError(f"ranking depth invalid: {query_id}")
        if [item.get("rank") for item in ranking] != list(range(1, 51)):
            raise ValueError(f"ranking positions invalid: {query_id}")
        if len({item.get("chunk_id") for item in ranking}) != 50:
            raise ValueError(f"duplicate ranked chunk: {query_id}")
        if any(not isinstance(item.get("score"), int) or not 0 <= item["score"] <= 3 for item in ranking):
            raise ValueError(f"ranking score invalid: {query_id}")
        source_relative = row.get("source_record_path")
        if not isinstance(source_relative, str):
            raise ValueError(f"source path missing: {query_id}")
        expected_source_hash = manifest_hashes.get(source_relative) or trace_hashes.get(source_relative)
        source_path = (ROOT / source_relative).resolve()
        source_path.relative_to(ROOT.resolve())
        if expected_source_hash is None or sha256_file(source_path) != expected_source_hash:
            raise ValueError(f"source-record lineage invalid: {query_id}")
        source = load_json(source_path)
        if source.get("ranking") != ranking:
            raise ValueError(f"source ranking differs: {query_id}")
        request = source.get("raw_request", {})
        messages = request.get("messages", [])
        if len(messages) != 1 or not isinstance(messages[0].get("content"), str):
            raise ValueError(f"source request invalid: {query_id}")
        payload = json.loads(messages[0]["content"])
        if payload.get("query_id") != query_id or not isinstance(payload.get("question"), str):
            raise ValueError(f"source query differs: {query_id}")
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 50:
            raise ValueError(f"source candidates invalid: {query_id}")
        mapping = {item["chunk_id"]: item["text"] for item in candidates}
        if len(mapping) != 50 or set(mapping) != {item["chunk_id"] for item in ranking}:
            raise ValueError(f"source candidate set differs: {query_id}")
        candidate_text[query_id] = mapping
        questions[query_id] = payload["question"]
    return rows, candidate_text, questions


def build(*, overwrite: bool = False) -> dict[str, Any]:
    checkpoint, phase5d_manifest, trace_hashes = verify_inputs()
    rankings, candidate_text, source_questions = validate_rankings(
        phase5d_manifest, trace_hashes
    )
    existing_bytes = EXISTING_BLIND.read_bytes()
    sealed_bytes = EXISTING_SEALED.read_bytes()
    if not existing_bytes.endswith(b"\n") or not sealed_bytes.endswith(b"\n"):
        raise ValueError("existing pool files must end with newline")
    existing_lines = existing_bytes.splitlines(keepends=True)
    existing_sealed_lines = sealed_bytes.splitlines(keepends=True)
    existing = load_jsonl(EXISTING_BLIND)
    existing_sealed_index = load_jsonl(EXISTING_SEALED)
    if len(existing) != len(existing_lines) or len(existing) != 620:
        raise ValueError("existing blind pool must contain 620 rows")
    if len(existing_sealed_index) != len(existing_sealed_lines) or len(existing_sealed_index) != 620:
        raise ValueError("existing sealed pool must contain 620 rows")
    existing_pairs: set[tuple[str, str]] = set()
    questions: dict[str, str] = {}
    next_number: dict[str, int] = {}
    for row in existing:
        if set(row) != BLIND_FIELDS or set(row) & FORBIDDEN_BLIND_FIELDS:
            raise ValueError("existing blind row schema invalid")
        if row["relevance_judgment"] or row["reviewer_notes"]:
            raise ValueError("existing blind pool contains owner labels")
        pair = (row["query_id"], row["chunk_id"])
        if pair in existing_pairs:
            raise ValueError("existing blind pool contains duplicate pair")
        existing_pairs.add(pair)
        prior_question = questions.setdefault(row["query_id"], row["question"])
        if prior_question != row["question"]:
            raise ValueError("existing blind question text inconsistent")
        match = DISPLAY_RE.fullmatch(row["display_id"])
        if match is None or match.group(1) != row["query_id"]:
            raise ValueError("existing display ID invalid")
        next_number[row["query_id"]] = max(
            next_number.get(row["query_id"], 0), int(match.group(2))
        )
    if questions != source_questions:
        raise ValueError("existing blind questions differ from frozen requests")
    blind_row_by_id = {row["display_id"]: row for row in existing}
    blind_line_by_id = {
        row["display_id"]: line for row, line in zip(existing, existing_lines)
    }
    sealed_line_by_id = {
        row["display_id"]: line
        for row, line in zip(existing_sealed_index, existing_sealed_lines)
    }
    if set(blind_line_by_id) != set(sealed_line_by_id):
        raise ValueError("existing blind/sealed display IDs differ")
    for row in existing_sealed_index:
        blind_row = blind_row_by_id[row["display_id"]]
        if (row.get("query_id"), row.get("chunk_id")) != (
            blind_row["query_id"],
            blind_row["chunk_id"],
        ):
            raise ValueError("existing blind/sealed pair alignment differs")

    top10: list[tuple[str, dict[str, Any], str, str]] = []
    for row in rankings:
        source_path = ROOT / row["source_record_path"]
        source_hash = sha256_file(source_path)
        for item in row["ranking"][:10]:
            top10.append((row["query_id"], item, row["source_record_path"], source_hash))
    top10_pairs = {(query_id, item["chunk_id"]) for query_id, item, _, _ in top10}
    if len(top10) != 340 or len(top10_pairs) != 340:
        raise ValueError("Prompt-RAG top-10 must contain 340 unique pairs")
    unseen = [row for row in top10 if (row[0], row[1]["chunk_id"]) not in existing_pairs]
    unseen.sort(
        key=lambda row: (
            row[0],
            hashlib.sha256(
                f"phase5f-blind-v1\0{row[0]}\0{row[1]['chunk_id']}".encode()
            ).hexdigest(),
        )
    )

    new_blind: list[dict[str, Any]] = []
    new_sealed: list[dict[str, Any]] = []
    for query_id, item, source_relative, source_hash in unseen:
        next_number[query_id] += 1
        display_id = f"{query_id}-candidate-{next_number[query_id]:02d}"
        new_blind.append(
            {
                "chunk_id": item["chunk_id"],
                "chunk_text": candidate_text[query_id][item["chunk_id"]],
                "display_id": display_id,
                "query_id": query_id,
                "question": questions[query_id],
                "relevance_judgment": "",
                "reviewer_notes": "",
            }
        )
        new_sealed.append(
            {
                "chunk_id": item["chunk_id"],
                "contribution": {
                    "rank": item["rank"],
                    "score": item["score"],
                    "source_system": SYSTEM,
                },
                "display_id": display_id,
                "lineage": {
                    "phase5d_commit": BASE_COMMIT,
                    "phase5d_manifest_path": str(PHASE5D_MANIFEST.relative_to(ROOT)),
                    "phase5d_manifest_sha256": EXPECTED[PHASE5D_MANIFEST],
                    "ranking_path": str(RANKINGS.relative_to(ROOT)),
                    "ranking_sha256": EXPECTED[RANKINGS],
                    "source_record_path": source_relative,
                    "source_record_sha256": source_hash,
                },
                "query_id": query_id,
            }
        )
    new_blind.sort(key=lambda row: row["display_id"])
    new_sealed.sort(key=lambda row: row["display_id"])
    blind_contribution = jsonl_bytes(new_blind)
    sealed_contribution = jsonl_bytes(new_sealed)
    blind_line_by_id.update(
        {
            row["display_id"]: (stable_json(row) + "\n").encode("utf-8")
            for row in new_blind
        }
    )
    sealed_line_by_id.update(
        {
            row["display_id"]: (stable_json(row) + "\n").encode("utf-8")
            for row in new_sealed
        }
    )
    final_order = sorted(
        blind_line_by_id,
        key=lambda display_id: hashlib.sha256(
            f"phase6-blind-order-v1\0{display_id}".encode()
        ).hexdigest(),
    )
    final_blind_bytes = b"".join(blind_line_by_id[display_id] for display_id in final_order)
    final_sealed_bytes = b"".join(sealed_line_by_id[display_id] for display_id in final_order)
    paths = {
        "blind_contribution": OUTPUT / "blind/prompt_rag_unseen_contribution.jsonl",
        "final_blind": OUTPUT / "blind/provisional_all_systems_pool.jsonl",
        "sealed_contribution": OUTPUT / "sealed/prompt_rag_unseen_provenance.jsonl",
        "final_sealed": OUTPUT / "sealed/provisional_all_systems_provenance.jsonl",
        "design": OUTPUT / "pool_design.json",
        "integrity": OUTPUT / "integrity_audit.json",
        "commands": OUTPUT / "commands.json",
    }
    write_bytes(paths["blind_contribution"], blind_contribution, overwrite=overwrite)
    write_bytes(paths["sealed_contribution"], sealed_contribution, overwrite=overwrite)
    write_bytes(paths["final_blind"], final_blind_bytes, overwrite=overwrite)
    write_bytes(paths["final_sealed"], final_sealed_bytes, overwrite=overwrite)
    final_pairs = existing_pairs | {(row["query_id"], row["chunk_id"]) for row in new_blind}
    design = {
        "candidate_cutoff": 10,
        "deduplication_key": ["query_id", "chunk_id"],
        "existing_pair_count": len(existing_pairs),
        "final_pair_count": len(final_pairs),
        "final_qrels": False,
        "owner_judging_completed": False,
        "prompt_rag_top10_pair_count": len(top10_pairs),
        "prompt_rag_unseen_pair_count": len(new_blind),
        "schema_version": 1,
        "status": "phase5f_frozen_pending_phase6_owner_package_approval",
    }
    integrity = {
        "checks": {
            "blind_contribution_has_no_forbidden_fields": all(
                set(row) == BLIND_FIELDS and not set(row) & FORBIDDEN_BLIND_FIELDS
                for row in new_blind
            ),
            "blind_owner_fields_blank": all(
                not row["relevance_judgment"] and not row["reviewer_notes"]
                for row in new_blind
            ),
            "existing_blind_rows_preserved_byte_identically": set(existing_lines).issubset(
                set(paths["final_blind"].read_bytes().splitlines(keepends=True))
            ),
            "existing_sealed_rows_preserved_byte_identically": set(existing_sealed_lines).issubset(
                set(paths["final_sealed"].read_bytes().splitlines(keepends=True))
            ),
            "final_pairs_unique": len(final_pairs) == len(existing_pairs) + len(new_blind),
            "new_pairs_all_from_frozen_top10": all(
                (row["query_id"], row["chunk_id"]) in top10_pairs for row in new_blind
            ),
            "sealed_maps_each_new_row_once": {
                row["display_id"] for row in new_blind
            }
            == {row["display_id"] for row in new_sealed},
            "owner_pool_order_independent_of_system_rank_and_score": len(final_order)
            == len(blind_line_by_id),
        },
        "construction_inputs": [
            str(PHASE4_MANIFEST.relative_to(ROOT)),
            str(PHASE4_POOL_DESIGN.relative_to(ROOT)),
            str(EXISTING_BLIND.relative_to(ROOT)),
            str(EXISTING_SEALED.relative_to(ROOT)),
            str(PHASE5D_CHECKPOINT.relative_to(ROOT)),
            str(PHASE5D_LEDGER.relative_to(ROOT)),
            str(PHASE5D_MANIFEST.relative_to(ROOT)),
            str(RANKINGS.relative_to(ROOT)),
            str(TRACE_MANIFEST.relative_to(ROOT)),
            "frozen source records named by complete_primary_rankings.jsonl",
        ],
        "forbidden_inputs_read": [],
        "network_or_api_calls": 0,
        "preserved_execution_evidence_modified": False,
        "relevance_metrics_calculated": False,
        "schema_version": 1,
        "status": "passed",
        "wrapper_correction": {
            "active_committed_wrapper_found": False,
            "safe_exit_variable_for_documented_command": "run_exit",
            "zsh_reserved_status_variable_used": False,
        },
    }
    if not all(integrity["checks"].values()):
        raise ValueError("Phase 5F integrity check failed")
    commands = {
        "deterministic_rebuild": [
            "python",
            "scripts/build_phase5f_prompt_rag_pool.py",
            "--overwrite",
        ],
        "safe_zsh_wrapper": "python scripts/build_phase5f_prompt_rag_pool.py --overwrite; run_exit=$?; exit $run_exit",
        "schema_version": 1,
    }
    write_json(paths["design"], design, overwrite=overwrite)
    write_json(paths["integrity"], integrity, overwrite=overwrite)
    write_json(paths["commands"], commands, overwrite=overwrite)

    manifest_paths = sorted(
        list(paths.values())
        + list(EXPECTED)
        + [
            ROOT / "docs/PHASE5F_PROMPT_RAG_POOL_PROTOCOL.md",
            ROOT / "scripts/build_phase5f_prompt_rag_pool.py",
            ROOT / "tests/test_phase5f_prompt_rag_pool.py",
            TRACE_MANIFEST,
        ]
    )
    freeze_manifest = {
        "artifact_hashes": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in manifest_paths
        },
        "artifact_n": len(manifest_paths),
        "base_commit": BASE_COMMIT,
        "credentials_stored": False,
        "generation_performed": False,
        "manifest_self_hash_excluded": True,
        "owner_judging_performed": False,
        "pool_counts": design,
        "relevance_metrics_included": False,
        "schema_version": 1,
        "status": "phase5f_offline_artifacts_frozen",
    }
    write_json(AUDIT / "freeze_manifest.json", freeze_manifest, overwrite=overwrite)
    return design


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(stable_json(build(overwrite=args.overwrite)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
