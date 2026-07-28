#!/usr/bin/env python3
"""Generate deterministic Phase 1 validation evidence and hashes."""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from collections import Counter
from dataclasses import MISSING, fields
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.v2_validator import validate_benchmark
from src.contracts.artifact import ArtifactManifest, ArtifactRecord
from src.contracts import ChunkV2, CorpusManifest, ExtractedDocument, QAItemV2, QrelsJudgment, RawSourceRecord
from src.ingestion.v2_pipeline import FORBIDDEN, LABEL_LINE, chunk_document_v2
from src.utils.atomic_io import write_json, write_jsonl
from src.utils.hashing import sha256_file, sha256_text


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    pilot = args.pilot_root.resolve()
    audit = args.audit_root.resolve()
    if pilot != (ROOT / "data/v2/pilot").resolve() or audit != (ROOT / "audits/phase1").resolve():
        raise ValueError("paths must be data/v2/pilot and audits/phase1")
    sources = rows(pilot / "manifests/raw_sources.jsonl")
    documents = rows(pilot / "extracted/documents.jsonl")
    chunks = rows(pilot / "chunks/chunks.jsonl")
    qa = rows(pilot / "qa/qa_draft.jsonl")
    qrels = rows(pilot / "qrels/qrels_draft.jsonl")
    source_map = {x["source_id"]: x for x in sources}
    chunk_map = {x["chunk_id"]: x for x in chunks}

    renderer = {
        "documents": len(documents), "raw_json_leaks": 0, "schema_label_leaks": 0,
        "html_or_script_leaks": 0, "placeholder_or_empty_documents": 0,
        "text_hash_mismatches": 0, "pdfs": [],
    }
    for doc in documents:
        text = doc["text"]
        if FORBIDDEN.search(text): renderer["raw_json_leaks"] += 1
        if LABEL_LINE.search(text): renderer["schema_label_leaks"] += 1
        if re.search(r"<[A-Za-z/!]", text): renderer["html_or_script_leaks"] += 1
        if not text.strip(): renderer["placeholder_or_empty_documents"] += 1
        if sha256_text(text) != doc["text_sha256"]: renderer["text_hash_mismatches"] += 1
        if doc["page_count"] is not None:
            renderer["pdfs"].append({k: doc[k] for k in ("document_id", "page_count", "pages_extracted", "empty_page_count", "extraction_warnings", "ocr_used", "renderer_version")})
    if any(renderer[key] for key in ("raw_json_leaks", "schema_label_leaks", "html_or_script_leaks", "placeholder_or_empty_documents", "text_hash_mismatches")):
        raise RuntimeError(f"renderer audit failed: {renderer}")

    overlap_failures = offset_failures = lineage_failures = max_size_failures = 0
    reconstructed: list[dict] = []
    for doc in documents:
        expected = chunk_document_v2(document_id=doc["document_id"], source_id=doc["source_id"], text=doc["text"],
                                     source_sha256=doc["source_sha256"], renderer_version=doc["renderer_version"])
        reconstructed.extend(x.to_dict() for x in expected)
    expected_map = {x["chunk_id"]: x for x in reconstructed}
    for chunk in chunks:
        doc = next(x for x in documents if x["document_id"] == chunk["document_id"])
        if doc["text"][chunk["start_char"]:chunk["end_char"]] != chunk["text"]: offset_failures += 1
        if chunk["word_count"] > 300: max_size_failures += 1
        if chunk["source_sha256"] != source_map[chunk["source_id"]]["raw_sha256"]: lineage_failures += 1
        if chunk["chunk_index"] and chunk["previous_overlap"] != 60: overlap_failures += 1
    if expected_map != chunk_map or any((overlap_failures, offset_failures, lineage_failures, max_size_failures)):
        raise RuntimeError("chunk determinism/offset/overlap/lineage audit failed")
    chunking = {
        "chunk_count": len(chunks), "maximum_word_count": max(x["word_count"] for x in chunks),
        "minimum_word_count": min(x["word_count"] for x in chunks),
        "noninitial_overlap_values": sorted({x["previous_overlap"] for x in chunks if x["chunk_index"]}),
        "overlap_failures": 0, "offset_failures": 0, "lineage_failures": 0,
        "maximum_size_failures": 0, "deterministic_reconstruction": True,
    }
    benchmark = validate_benchmark(qa, qrels, chunks)

    document_list = [{"document_id": x["document_id"], "title": x["title"], "ministry": x["ministry"],
                      "source_id": x["source_id"], "official_url": source_map[x["source_id"]]["official_url"]} for x in documents]
    write_json(audit / "acquisition/document_list.json", document_list, overwrite=args.overwrite)
    write_json(audit / "acquisition/failures.json", json.loads((pilot / "audits/acquisition_failures.json").read_text()), overwrite=args.overwrite)
    write_json(audit / "renderer/audit.json", renderer, overwrite=args.overwrite)
    write_json(audit / "chunking/audit.json", chunking, overwrite=args.overwrite)
    write_json(audit / "qa/audit.json", benchmark, overwrite=args.overwrite)
    multi = [x for x in qa if x["category"] == "multi_hop"]
    write_json(audit / "qa/multi_hop_structure.json", [{
        "question_id": x["question_id"], "bridge_entity": x["bridge_entity"],
        "gold_evidence_count": len(x["gold_evidence_ids"]),
        "distinct_source_documents": len(set(x["source_document_ids"])),
    } for x in multi], overwrite=args.overwrite)
    title_by_doc = {x["document_id"]: x["title"] for x in documents}
    write_json(audit / "qa/multi_hop_lexical_shortcuts.json", [{
        "question_id": x["question_id"],
        "target_titles_present_verbatim": [title for title in (title_by_doc[d] for d in x["source_document_ids"]) if title.lower() in x["question"].lower()],
        "status": "mechanically checked; human semantic review pending",
    } for x in multi], overwrite=args.overwrite)
    synthesis = [x for x in qa if x["category"] == "synthesis"]
    write_json(audit / "qa/synthesis.json", [{
        "question_id": x["question_id"], "gold_evidence_count": len(x["gold_evidence_ids"]),
        "distinct_source_documents": len(set(x["source_document_ids"])),
        "answer_clause_review": "pending_human_review",
    } for x in synthesis], overwrite=args.overwrite)
    examples = []
    for qid in ("v2q-001", "v2q-007", "v2q-013", "v2q-025", "v2q-031"):
        item = next(x for x in qa if x["question_id"] == qid)
        examples.append({"qa_item": item, "full_gold_chunks": [chunk_map[cid] for cid in item["gold_evidence_ids"]]})
    write_json(audit / "qa/five_examples_with_gold.json", examples, overwrite=args.overwrite)
    contract_types = (RawSourceRecord, ExtractedDocument, CorpusManifest, ChunkV2, QAItemV2, QrelsJudgment, ArtifactManifest)
    write_json(audit / "contracts/contracts.json", {
        "schema_version": "2.0",
        "contracts": {cls.__name__: [{"name": f.name, "type": str(f.type), "required": f.default is MISSING and f.default_factory is MISSING} for f in fields(cls)] for cls in contract_types},
        "validation": "fail closed; executable validation in src/contracts; focused tests in tests/test_v2_contracts.py",
    }, overwrite=args.overwrite)
    write_json(audit / "environment.json", {"python": platform.python_version(), "platform": platform.platform()}, overwrite=args.overwrite)
    changed = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    write_json(audit / "changed_files.json", changed, overwrite=args.overwrite)
    findings = {
        "status": "Phase 1 diagnostic/development pilot; not final inferential evidence",
        "documents": len(documents), "structured_records": sum(x["acquisition_method"] == "myscheme_public_structured_api" for x in sources),
        "official_pdfs": sum(x["mime_type"] == "application/pdf" for x in sources),
        "ministries": len({x["ministry"] for x in documents}), "chunks": len(chunks), "qa_items": len(qa),
        "qrels_by_grade": dict(sorted(Counter(str(x["relevance"]) for x in qrels).items())),
        "remaining_unverified": ["human QA acceptance", "human qrel review", "semantic correctness beyond extractive alignment", "source publisher authenticity beyond official-domain and MyScheme records"],
    }
    write_json(audit / "findings.json", findings, overwrite=args.overwrite)

    artifact_specs = [
        ("raw-source-manifest", pilot / "manifests/raw_sources.jsonl", ()),
        ("extracted-documents", pilot / "extracted/documents.jsonl", ("raw-source-manifest",)),
        ("chunks", pilot / "chunks/chunks.jsonl", ("extracted-documents",)),
        ("qa-draft", pilot / "qa/qa_draft.jsonl", ("chunks",)),
        ("qrels-draft", pilot / "qrels/qrels_draft.jsonl", ("qa-draft", "chunks")),
        ("corpus-manifest", pilot / "manifests/corpus.json", ("raw-source-manifest", "extracted-documents", "chunks")),
    ]
    records = tuple(ArtifactRecord(item_id, str(path.relative_to(ROOT)), sha256_file(path), path.stat().st_size,
                                   "Phase 1 V2 pipeline", parents) for item_id, path, parents in artifact_specs)
    manifest = ArtifactManifest("2.0", "phase1-pilot-artifacts", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), records)
    write_json(pilot / "manifests/artifacts.json", manifest.to_dict(), overwrite=args.overwrite)
    hash_paths = [path for _, path, _ in artifact_specs] + [pilot / "manifests/artifacts.json",
        audit / "acquisition/document_list.json", audit / "acquisition/failures.json", audit / "renderer/audit.json",
        audit / "chunking/audit.json", audit / "qa/audit.json", audit / "qa/multi_hop_structure.json",
        audit / "qa/multi_hop_lexical_shortcuts.json", audit / "qa/synthesis.json", audit / "qa/five_examples_with_gold.json",
        audit / "contracts/contracts.json", audit / "environment.json", audit / "changed_files.json",
        audit / "findings.json", audit / "commands/commands.txt"]
    hash_rows = [{"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path), "byte_size": path.stat().st_size} for path in hash_paths]
    write_jsonl(audit / "hashes/artifacts.jsonl", hash_rows, key="path", overwrite=args.overwrite)
    print(json.dumps(findings, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
