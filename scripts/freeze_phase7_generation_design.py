#!/usr/bin/env python3
"""Build deterministic, network-free Phase 7 Claude generation freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.phase7_context import serialize_context  # noqa: E402
from src.generation.phase7_freeze import (  # noqa: E402
    API_VERSION,
    CONTEXT_DEPTH,
    ENDPOINT,
    FAILURE_CLASSES,
    HARD_COST_CAP_USD,
    INPUT_USD_PER_MILLION,
    MAX_OUTPUT_TOKENS,
    MODEL,
    OUTPUT_USD_PER_MILLION,
    RETRY_N,
    RETURNED_MODEL_POLICY,
    SDK_NAME,
    SDK_VERSION,
    TEMPERATURE,
    TIMEOUT_SECONDS,
    TRACE_N,
    build_request,
    conservative_input_token_envelope,
    enforce_cost_cap,
    maximum_cost_usd,
    request_sha256,
    response_schema,
    select_trace,
    trace_hash,
)
from src.generation.phase7_gate import assert_phase7_ready  # noqa: E402
from src.generation.phase7_panel import (  # noqa: E402
    SYSTEM_IDS,
    build_panel,
    load_questions,
    load_rankings,
    read_jsonl,
    verify_hash,
)
from src.utils.atomic_io import write_bytes, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file, sha256_text  # noqa: E402


EXPECTED_HEAD = "c9af2cfbd0cc49fa0935611a71a7b64cf261a68d"
EXPECTED_QUESTION_SHA256 = (
    "0abd328ff639a05e80559202a018df0bd50aaf875f8d6b7753af925cc8a89c4b"
)
EXPECTED_CHUNK_SHA256 = (
    "70c1e3b8b0380809adea000654333a5921132ab7608ff328a9fa7934e8f43aa6"
)
EXPECTED_FINAL_LABEL_SHA256 = (
    "ee5f4c6731117001ff92be01489e859b43ab14a6bda6bcfc8b0bce16ca94f77c"
)
EXPECTED_FINAL_QRELS_SHA256 = (
    "c167689e5f0a1e7412d17baab56c6789e1612bb08121255fc0c153fecd1e077f"
)
EXPECTED_RANKING_SHA256 = {
    "bm25": "93b42dc121927561bf880cbe44ccf264c60bac1196adac08ce3d6d5e80d2db6a",
    "faiss_windowed_max": "7e419626d2e7d00efaedfa9f1ce0dda01760dbce5c901b214e992e32df597115",
    "graph_v3_2": "68ad05ff4b600fa549f957b4bd44579af7e9d6addc2ddebff3f71a4584adc59a",
    "hybrid_rrf": "6570030a1c12edb38ff5c4e33b5dedb5d2fa83a05aa9a01ecd768bcf4edce249",
    "prompt_rag_claude": "e665aa4dc80b468a0fc2af06173ab0e6963786a578653c9a9083e6ffa6b1e04f",
}
EXPECTED_CATEGORY_COUNTS = {
    "entity_relation": 6,
    "exact_lookup": 6,
    "multi_hop": 6,
    "paraphrase": 6,
    "synthesis": 4,
    "terminology": 6,
}
PRICING_VERIFIED_AT_UTC = "2026-07-28T16:43:15Z"
PRICING_SOURCE_URL = (
    "https://www-cdn.anthropic.com/files/4zrzovbb/website/"
    "5678bc2f5978e5bcd4f1fe7c14b2c72284dcf9f8.pdf"
)
MODEL_PAGE_URL = "https://www.anthropic.com/claude/haiku"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependency-gate", type=Path, required=True)
    parser.add_argument("--gate-result", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--bm25-ranking", type=Path, required=True)
    parser.add_argument("--faiss-ranking", type=Path, required=True)
    parser.add_argument("--graph-ranking", type=Path, required=True)
    parser.add_argument("--hybrid-ranking", type=Path, required=True)
    parser.add_argument("--prompt-ranking", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--generation-protocol", type=Path, required=True)
    parser.add_argument("--evaluation-protocol", type=Path, required=True)
    parser.add_argument("--h5-protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--git-head", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def load_qa_metadata(path: Path) -> dict[str, dict[str, str]]:
    rows = read_jsonl(path)
    metadata: dict[str, dict[str, str]] = {}
    for row in rows:
        query_id = row.get("question_id", row.get("query_id"))
        category = row.get("category")
        if not isinstance(query_id, str) or not isinstance(category, str):
            raise ValueError("R5 QA lacks query/category metadata")
        if query_id in metadata:
            raise ValueError(f"duplicate R5 query ID: {query_id}")
        metadata[query_id] = {"category": category}
    counts = Counter(value["category"] for value in metadata.values())
    if dict(sorted(counts.items())) != EXPECTED_CATEGORY_COUNTS:
        raise ValueError(f"R5 category counts differ: {counts}")
    return metadata


def load_chunks(path: Path) -> dict[str, str]:
    verify_hash(path, EXPECTED_CHUNK_SHA256)
    rows = read_jsonl(path)
    chunks: dict[str, str] = {}
    for row in rows:
        chunk_id = row.get("chunk_id")
        text = row.get("text")
        if not isinstance(chunk_id, str) or not isinstance(text, str) or not text.strip():
            raise ValueError("invalid chunk record")
        if chunk_id in chunks:
            raise ValueError(f"duplicate chunk ID: {chunk_id}")
        chunks[chunk_id] = text
    if len(chunks) != 140:
        raise ValueError(f"expected 140 frozen chunks, found {len(chunks)}")
    return chunks


def verify_dependencies(args: argparse.Namespace) -> dict[str, Any]:
    if args.git_head != EXPECTED_HEAD:
        raise ValueError("freeze must be based on approved Phase 6 commit")
    actual_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual_head != EXPECTED_HEAD:
        raise ValueError(f"working HEAD differs from approved commit: {actual_head}")
    gate = assert_phase7_ready(args.dependency_gate, ROOT)
    gate_result = json.loads(args.gate_result.read_text(encoding="utf-8"))
    if gate_result.get("dependency_gate") != "OPEN":
        raise ValueError("Phase 7 dependency gate is not OPEN")
    if gate_result.get("execution_authorized") is not False:
        raise ValueError("dependency gate must not pre-authorize generation")
    dependency = json.loads(args.dependency_gate.read_text(encoding="utf-8"))
    final_labels = dependency["dependencies"]["final_labels"]
    final_qrels = dependency["final_qrels"]
    if final_labels["sha256"] != EXPECTED_FINAL_LABEL_SHA256:
        raise ValueError("final-label SHA differs")
    if sha256_file(ROOT / final_labels["path"]) != EXPECTED_FINAL_LABEL_SHA256:
        raise ValueError("final-label artifact hash differs")
    if final_qrels["sha256"] != EXPECTED_FINAL_QRELS_SHA256:
        raise ValueError("final-qrels SHA differs")
    if sha256_file(ROOT / final_qrels["path"]) != EXPECTED_FINAL_QRELS_SHA256:
        raise ValueError("final-qrels artifact hash differs")
    if gate["final_qrels_sha256"] != EXPECTED_FINAL_QRELS_SHA256:
        raise ValueError("gate final-qrels SHA differs")
    if set(dependency["rankings"]) != set(SYSTEM_IDS):
        raise ValueError("dependency ranking systems differ")
    for system_id, expected in EXPECTED_RANKING_SHA256.items():
        if dependency["rankings"][system_id]["sha256"] != expected:
            raise ValueError(f"dependency ranking SHA differs: {system_id}")
    if version(SDK_NAME) != SDK_VERSION:
        raise ValueError(f"installed Anthropic SDK must equal {SDK_VERSION}")
    return {
        "approved_phase6_commit": EXPECTED_HEAD,
        "dependency_gate": "OPEN",
        "execution_authorized": False,
        "final_label_path": final_labels["path"],
        "final_label_sha256": EXPECTED_FINAL_LABEL_SHA256,
        "final_qrels_path": final_qrels["path"],
        "final_qrels_sha256": EXPECTED_FINAL_QRELS_SHA256,
        "ranking_sha256": EXPECTED_RANKING_SHA256,
        "sdk_version": SDK_VERSION,
        "status": "passed",
    }


def write_machine_protocols(
    *, output_root: Path, prompt_hash: str, schema_hash: str, overwrite: bool
) -> list[Path]:
    failure_path = output_root / "failure_contract.json"
    evaluation_path = output_root / "evaluator_protocol.json"
    h5_path = output_root / "h5_protocol.json"
    write_json(
        failure_path,
        {
            "ambiguous_dispatch_billing": "potentially_billed_and_reserved",
            "automatic_retries": RETRY_N,
            "completed_output_overwrite_allowed": False,
            "failure_classes": list(FAILURE_CLASSES),
            "fallback_model": None,
            "failed_output_replacement_allowed": False,
            "pre_dispatch_cost_rule": (
                "refuse when actual accumulated cost plus current request envelope plus "
                "unexecuted request envelopes plus ambiguous-dispatch reserve exceeds $0.95"
            ),
            "recovery": "separate output path and separate owner approval required",
            "status": "frozen",
        },
        overwrite=overwrite,
    )
    owner_audit_ids = sorted(
        (f"P7B{index:03d}" for index in range(1, 171)),
        key=lambda value: (
            hashlib.sha256(f"42:{value}".encode("utf-8")).hexdigest(),
            value,
        ),
    )[:26]
    write_json(
        evaluation_path,
        {
            "ai_judge_calls_authorized": False,
            "answer_quality_dimensions": [
                "correctness",
                "faithfulness",
                "completeness",
                "citation_accuracy",
                "unsupported_claim_severity",
                "abstention_quality",
            ],
            "automated_first_pass": "requires separate owner approval and remains AI evaluation",
            "mechanical_dimensions": [
                "schema_validity",
                "citation_id_validity",
                "citation_coverage",
                "abstention_rate",
                "response_failure_rate",
                "latency",
                "usage",
                "cost",
            ],
            "no_composite_score": True,
            "owner_audit": {
                "blinded_request_ids": owner_audit_ids,
                "blinded": True,
                "record_n": 26,
                "sample_fraction": 0.15,
                "selection_rule": (
                    "ascending SHA-256('42:' + blinded_request_id), tie blinded_request_id"
                ),
                "seed": 42,
            },
            "owner_adjudication_required_for_disagreement": True,
            "status": "frozen_before_outputs",
        },
        overwrite=overwrite,
    )
    write_json(
        h5_path,
        {
            "bootstrap": {"paired_whole_query": True, "samples": 10000, "seed": 42},
            "category_summaries": True,
            "causal_claim_allowed": False,
            "holm_correction": True,
            "missing_output_sensitivity": [
                "retain_as_failure_primary",
                "worst_quality_assignment",
                "complete_case_display",
            ],
            "outcomes": [
                "retrieval_relevance_vs_answer_correctness",
                "complete_evidence_recall_vs_answer_completeness",
                "retrieval_quality_vs_faithfulness",
                "citation_accuracy_by_system",
                "unsupported_claims_by_system",
                "abstention_quality_by_system",
            ],
            "paired_query_level": True,
            "prompt_sha256": prompt_hash,
            "retrieval_qrels_sha256": EXPECTED_FINAL_QRELS_SHA256,
            "response_schema_sha256": schema_hash,
            "status": "frozen_before_generation_results",
            "universal_winner_claim_allowed": False,
        },
        overwrite=overwrite,
    )
    return [failure_path, evaluation_path, h5_path]


def main() -> None:
    args = parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())

    dependency_validation = verify_dependencies(args)
    questions = load_questions(args.questions, EXPECTED_QUESTION_SHA256)
    if len(questions) != 34:
        raise ValueError(f"expected 34 questions, found {len(questions)}")
    qa_metadata = load_qa_metadata(args.questions)
    chunks = load_chunks(args.chunks)
    query_ids = {row["query_id"] for row in questions}
    ranking_paths = {
        "bm25": args.bm25_ranking,
        "faiss_windowed_max": args.faiss_ranking,
        "graph_v3_2": args.graph_ranking,
        "hybrid_rrf": args.hybrid_ranking,
        "prompt_rag_claude": args.prompt_ranking,
    }
    rankings: dict[str, dict[str, list[str]]] = {}
    for system_id in SYSTEM_IDS:
        rankings[system_id] = load_rankings(
            ranking_paths[system_id], EXPECTED_RANKING_SHA256[system_id], query_ids
        )
    panel = build_panel(questions, rankings)
    if len(panel) != 170:
        raise ValueError("generation panel must contain 170 pairs")

    prompt_text = args.prompt.read_text(encoding="utf-8")
    prompt_hash = sha256_text(prompt_text)
    schema = response_schema()
    schema_hash = sha256_text(json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    logical_order = sorted(
        (row["logical_request_id"] for row in panel),
        key=lambda value: (trace_hash(value), value),
    )
    blinded_ids = {
        logical_id: f"P7B{index:03d}"
        for index, logical_id in enumerate(logical_order, start=1)
    }
    context_rows: list[dict[str, Any]] = []
    payload_rows: list[dict[str, Any]] = []
    sealed_rows: list[dict[str, Any]] = []
    for row in panel:
        logical_id = row["logical_request_id"]
        blinded_id = blinded_ids[logical_id]
        serialized_context, evidence_map = serialize_context(
            row["question"], row["ranked_chunk_ids"], chunks, CONTEXT_DEPTH
        )
        context_hash = sha256_text(serialized_context)
        request = build_request(prompt=prompt_text, serialized_context=serialized_context, schema=schema)
        request_hash = request_sha256(request)
        envelope = conservative_input_token_envelope(request)
        context_byte_n = len(serialized_context.encode("utf-8"))
        context_rows.append(
            {
                "blinded_request_id": blinded_id,
                "context_sha256": context_hash,
                "evidence_count": len(evidence_map),
                "serialized_context": serialized_context,
                "serialized_context_utf8_bytes": context_byte_n,
            }
        )
        payload_rows.append(
            {
                "blinded_request_id": blinded_id,
                "request": request,
                "request_sha256": request_hash,
            }
        )
        sealed_rows.append(
            {
                "billing_ambiguity": False,
                "blinded_request_id": blinded_id,
                "category": qa_metadata[row["query_id"]]["category"],
                "context_sha256": context_hash,
                "cost_usd": None,
                "cumulative_cost_usd": None,
                "evidence_id_to_chunk_id": evidence_map,
                "execution_status": "frozen_not_executed",
                "failure_class": None,
                "input_tokens": None,
                "latency_seconds": None,
                "logical_request_id": logical_id,
                "output_tokens": None,
                "raw_response_path": None,
                "planned_input_token_envelope": envelope["token_envelope"],
                "query_id": row["query_id"],
                "request_hash": request_hash,
                "requested_model": MODEL,
                "response_id": None,
                "response_hash": None,
                "returned_model": None,
                "serialized_context_utf8_bytes": context_byte_n,
                "system_id": row["retrieval_system"],
                "timestamp": None,
                "usage_status": "not_executed",
            }
        )

    trace_rows = select_trace(sealed_rows)
    trace_ids = {row["logical_request_id"] for row in trace_rows}
    trace_plan = {
        "category_n": len({row["category"] for row in trace_rows}),
        "context_length_distinct_n": len(
            {row["serialized_context_utf8_bytes"] for row in trace_rows}
        ),
        "request_n": TRACE_N,
        "selected": [
            {
                "blinded_request_id": row["blinded_request_id"],
                "category": row["category"],
                "logical_request_id": row["logical_request_id"],
                "selection_sha256": trace_hash(row["logical_request_id"]),
                "serialized_context_utf8_bytes": row[
                    "serialized_context_utf8_bytes"
                ],
                "system_id": row["system_id"],
            }
            for row in trace_rows
        ],
        "selection_rule": (
            "ascending SHA-256(logical_request_id), tie logical_request_id; first 10"
        ),
        "system_n": len({row["system_id"] for row in trace_rows}),
    }

    trace_input = sum(
        row["planned_input_token_envelope"]
        for row in sealed_rows
        if row["logical_request_id"] in trace_ids
    )
    remaining_input = sum(
        row["planned_input_token_envelope"]
        for row in sealed_rows
        if row["logical_request_id"] not in trace_ids
    )
    full_input = trace_input + remaining_input
    largest_input = max(row["planned_input_token_envelope"] for row in sealed_rows)
    trace_cost = maximum_cost_usd(trace_input, TRACE_N)
    remaining_cost = maximum_cost_usd(remaining_input, 170 - TRACE_N)
    full_cost = maximum_cost_usd(full_input, 170)
    ambiguous_reserve = maximum_cost_usd(largest_input, 1)
    cumulative_worst = full_cost + ambiguous_reserve
    enforce_cost_cap(cumulative_worst)
    cost_plan = {
        "ambiguous_dispatch_reserve": {
            "basis": "one largest planned request at maximum output",
            "input_token_envelope": largest_input,
            "usd": ambiguous_reserve,
        },
        "cache_discount_assumed": False,
        "cumulative_worst_case_usd": cumulative_worst,
        "full_panel": {
            "input_token_envelope": full_input,
            "maximum_output_tokens": 170 * MAX_OUTPUT_TOKENS,
            "request_n": 170,
            "worst_case_usd": full_cost,
        },
        "hard_cap_pass": cumulative_worst <= HARD_COST_CAP_USD,
        "hard_cap_usd": HARD_COST_CAP_USD,
        "input_price_usd_per_million_tokens": INPUT_USD_PER_MILLION,
        "output_price_usd_per_million_tokens": OUTPUT_USD_PER_MILLION,
        "pricing": {
            "effective_date": "2026-05-12",
            "model_page_url": MODEL_PAGE_URL,
            "official_price_document_url": PRICING_SOURCE_URL,
            "status": "verified_from_official_Anthropic_sources",
            "verified_at_utc": PRICING_VERIFIED_AT_UTC,
        },
        "remaining_after_trace": {
            "input_token_envelope": remaining_input,
            "maximum_output_tokens": (170 - TRACE_N) * MAX_OUTPUT_TOKENS,
            "request_n": 170 - TRACE_N,
            "worst_case_usd": remaining_cost,
        },
        "token_counting": {
            "actual_provider_usage_authoritative": True,
            "installed_sdk": f"{SDK_NAME}=={SDK_VERSION}",
            "local_model_compatible_tokenizer_available": False,
            "method": "ceil(canonical_request_utf8_bytes/2)+256 per request",
            "network_token_count_endpoint_used": False,
            "status": "conservative_offline_envelope",
        },
        "trace": {
            "input_token_envelope": trace_input,
            "maximum_output_tokens": TRACE_N * MAX_OUTPUT_TOKENS,
            "request_n": TRACE_N,
            "worst_case_usd": trace_cost,
        },
    }

    output_paths = {
        "config": args.output_root / "execution_config.json",
        "prompt": args.output_root / "prompt.txt",
        "schema": args.output_root / "response_schema.json",
        "contexts": args.output_root / "blinded/serialized_contexts.jsonl",
        "payloads": args.output_root / "blinded/request_payloads.jsonl",
        "request_plan": args.output_root / "sealed/request_plan.jsonl",
        "trace_plan": args.output_root / "sealed/trace_plan.json",
        "cost_plan": args.output_root / "cost_plan.json",
        "dependency_manifest": args.output_root / "dependency_manifest.json",
    }
    write_bytes(
        output_paths["prompt"], prompt_text.encode("utf-8"), overwrite=args.overwrite
    )
    write_json(output_paths["schema"], schema, overwrite=args.overwrite)
    copied_schema_hash = sha256_file(output_paths["schema"])
    if copied_schema_hash != schema_hash:
        raise ValueError("response schema serialization hash differs")
    write_jsonl(
        output_paths["contexts"],
        context_rows,
        key="blinded_request_id",
        overwrite=args.overwrite,
    )
    write_jsonl(
        output_paths["payloads"],
        payload_rows,
        key="blinded_request_id",
        overwrite=args.overwrite,
    )
    write_jsonl(
        output_paths["request_plan"],
        sealed_rows,
        key="logical_request_id",
        overwrite=args.overwrite,
    )
    write_json(output_paths["trace_plan"], trace_plan, overwrite=args.overwrite)
    write_json(output_paths["cost_plan"], cost_plan, overwrite=args.overwrite)

    machine_protocols = write_machine_protocols(
        output_root=args.output_root,
        prompt_hash=prompt_hash,
        schema_hash=schema_hash,
        overwrite=args.overwrite,
    )
    dependency_manifest = {
        "approved_phase6_commit": EXPECTED_HEAD,
        "chunks": {"path": relative(args.chunks), "sha256": EXPECTED_CHUNK_SHA256},
        "dependency_gate": {
            "path": relative(args.dependency_gate),
            "sha256": sha256_file(args.dependency_gate),
            "status": "OPEN",
        },
        "final_label_sha256": EXPECTED_FINAL_LABEL_SHA256,
        "final_labels": {
            "path": dependency_validation["final_label_path"],
            "sha256": EXPECTED_FINAL_LABEL_SHA256,
        },
        "final_qrels": {
            "path": dependency_validation["final_qrels_path"],
            "sha256": EXPECTED_FINAL_QRELS_SHA256,
        },
        "final_qrels_sha256": EXPECTED_FINAL_QRELS_SHA256,
        "question_n": 34,
        "questions": {
            "path": relative(args.questions),
            "sha256": EXPECTED_QUESTION_SHA256,
        },
        "rankings": {
            system_id: {
                "path": relative(ranking_paths[system_id]),
                "sha256": EXPECTED_RANKING_SHA256[system_id],
            }
            for system_id in SYSTEM_IDS
        },
        "request_n": 170,
        "status": "verified",
        "system_n": 5,
    }
    write_json(
        output_paths["dependency_manifest"],
        dependency_manifest,
        overwrite=args.overwrite,
    )
    config = {
        "api": {
            "api_version": API_VERSION,
            "endpoint": ENDPOINT,
            "sdk": SDK_NAME,
            "sdk_version": SDK_VERSION,
            "stateless": True,
        },
        "context": {
            "depth": CONTEXT_DEPTH,
            "evidence_ids": ["E01", "E02", "E03"],
            "preserve_frozen_order": True,
            "silent_truncation": False,
        },
        "cost": cost_plan,
        "execution_enabled": False,
        "generation": {
            "best_of_n": 1,
            "fallback_model": None,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "prompt_caching_assumed": False,
            "response_replacement_allowed": False,
            "result_dependent_context_changes_allowed": False,
            "result_dependent_exclusions_allowed": False,
            "service_tier": "standard_only",
            "stream": False,
            "temperature": TEMPERATURE,
            "tools": [],
        },
        "hard_cap_usd": HARD_COST_CAP_USD,
        "model": MODEL,
        "output_root": relative(args.output_root),
        "panel": {"question_n": 34, "request_n": 170, "system_n": 5},
        "prompt": {"path": relative(output_paths["prompt"]), "sha256": prompt_hash},
        "response_schema": {
            "path": relative(output_paths["schema"]),
            "sha256": schema_hash,
        },
        "returned_model_policy": RETURNED_MODEL_POLICY,
        "retry_n": RETRY_N,
        "status": "offline_frozen_pending_owner_trace_approval",
        "timeout_seconds": TIMEOUT_SECONDS,
        "trace_request_n": TRACE_N,
    }
    write_json(output_paths["config"], config, overwrite=args.overwrite)

    args.audit_root.mkdir(parents=True, exist_ok=True)
    audit_paths = {
        "dependency": args.audit_root / "dependency_validation.json",
        "blinding": args.audit_root / "blinding_audit.json",
        "cost": args.audit_root / "token_and_cost_audit.json",
        "readiness": args.audit_root / "freeze_readiness.json",
    }
    write_json(audit_paths["dependency"], dependency_validation, overwrite=args.overwrite)
    forbidden_blind_keys = {
        "system_id",
        "retrieval_system",
        "rank",
        "score",
        "reference_answer",
        "category",
        "qrels",
        "grade",
        "metrics",
    }
    blind_serialized = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) for row in context_rows + payload_rows
    ).lower()
    leaked = sorted(key for key in forbidden_blind_keys if f'"{key}"' in blind_serialized)
    if leaked:
        raise ValueError(f"blinded artifacts contain forbidden keys: {leaked}")
    write_json(
        audit_paths["blinding"],
        {
            "blind_request_n": len(payload_rows),
            "forbidden_key_hits": leaked,
            "generator_visible_fields": [
                "question",
                "evidence.evidence_id",
                "evidence.text",
                "fixed_prompt",
                "response_schema",
            ],
            "reference_answer_exposed": False,
            "system_identity_exposed": False,
            "status": "passed",
        },
        overwrite=args.overwrite,
    )
    write_json(audit_paths["cost"], cost_plan, overwrite=args.overwrite)
    write_json(
        audit_paths["readiness"],
        {
            "api_calls_n": 0,
            "credential_access_n": 0,
            "dependency_validation": "passed",
            "execution_authorized": False,
            "generation_outputs_n": 0,
            "hard_cap_pass": cost_plan["hard_cap_pass"],
            "prompt_frozen": True,
            "request_n": 170,
            "schema_frozen": True,
            "status": "ready_for_owner_trace_approval",
            "trace_request_n": 10,
        },
        overwrite=args.overwrite,
    )

    artifact_paths = [
        *output_paths.values(),
        *machine_protocols,
        *audit_paths.values(),
        args.generation_protocol,
        args.evaluation_protocol,
        args.h5_protocol,
    ]
    artifact_paths = sorted(set(artifact_paths), key=lambda path: relative(path))
    freeze_manifest = {
        "artifacts": {relative(path): sha256_file(path) for path in artifact_paths},
        "code": {
            "scripts/freeze_phase7_generation_design.py": sha256_file(
                ROOT / "scripts/freeze_phase7_generation_design.py"
            ),
            "src/generation/phase7_context.py": sha256_file(
                ROOT / "src/generation/phase7_context.py"
            ),
            "src/generation/phase7_freeze.py": sha256_file(
                ROOT / "src/generation/phase7_freeze.py"
            ),
            "src/generation/phase7_gate.py": sha256_file(
                ROOT / "src/generation/phase7_gate.py"
            ),
            "src/generation/phase7_panel.py": sha256_file(
                ROOT / "src/generation/phase7_panel.py"
            ),
            "src/utils/atomic_io.py": sha256_file(ROOT / "src/utils/atomic_io.py"),
            "src/utils/hashing.py": sha256_file(ROOT / "src/utils/hashing.py"),
        },
        "dependency_hashes": {
            relative(args.dependency_gate): sha256_file(args.dependency_gate),
            relative(args.gate_result): sha256_file(args.gate_result),
            relative(args.questions): EXPECTED_QUESTION_SHA256,
            relative(args.chunks): EXPECTED_CHUNK_SHA256,
            relative(args.prompt): sha256_file(args.prompt),
            **{
                relative(ranking_paths[system_id]): EXPECTED_RANKING_SHA256[system_id]
                for system_id in SYSTEM_IDS
            },
        },
        "execution_authorized": False,
        "git_head_at_freeze": EXPECTED_HEAD,
        "live_api_calls_n": 0,
        "prompt_sha256": prompt_hash,
        "response_schema_sha256": schema_hash,
        "status": "frozen_offline_pending_owner_trace_approval",
    }
    freeze_path = args.output_root / "freeze_manifest.json"
    write_json(freeze_path, freeze_manifest, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "cumulative_worst_case_usd": cumulative_worst,
                "full_panel_worst_case_usd": full_cost,
                "hard_cap_pass": True,
                "prompt_sha256": prompt_hash,
                "request_n": 170,
                "schema_sha256": schema_hash,
                "trace_ids": [row["logical_request_id"] for row in trace_rows],
                "trace_worst_case_usd": trace_cost,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
