#!/usr/bin/env python3
"""Audit all scheme aliases from frozen corpus/source artifacts only."""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.entity_graph_v3 import normalize_text  # noqa: E402
from src.utils.atomic_io import stable_json, write_bytes, write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


OUTPUT = ROOT / "audits/phase3_graph_v3_2"
ACCEPTED_SPECS = (
    {
        "canonical_label": "Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana",
        "alias": "AB PM-JAY",
        "rule": "explicit_official_short_title_in_corpus",
    },
    {
        "canonical_label": "Pradhan Mantri Garib Kalyan Anna Yojana",
        "alias": "PMGKAY",
        "rule": "title_followed_by_acronym",
    },
    {
        "canonical_label": "PM-KISAN Operational Guidelines",
        "alias": "PM-KISAN",
        "rule": "repeated_official_short_title",
    },
    {
        "canonical_label": "Pradhan Mantri Ujjwala Yojana 2.0",
        "alias": "PMUY 2.0",
        "rule": "official_numbered_phase_name",
    },
    {
        "canonical_label": "Pradhan Mantri Ujjwala Yojana 2.0",
        "alias": "Ujjwala 2.0",
        "rule": "official_numbered_phase_name",
    },
)
REJECTED_SPECS = (
    {
        "canonical_label": "Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana",
        "alias": "PM-JAY",
        "reason": "alias already owned by separate accepted controlled entity; activation would map one alias to multiple canonical entity IDs",
    },
    {
        "canonical_label": "Pradhan Mantri Kisan Maan Dhan Yojana Operational Guidelines",
        "alias": "PM-KMY",
        "reason": "alias already owned by separate accepted controlled entity; no entity-identity repair authorized in v3.2",
    },
    {
        "canonical_label": "Pradhan Mantri Ujjwala Yojana 2.0",
        "alias": "PMUY",
        "reason": "ambiguous across predecessor PMUY scheme and numbered phase 2.0",
    },
    {
        "canonical_label": "Pradhan Mantri Awaas Yojana - Gramin",
        "alias": "PMAY",
        "reason": "ambiguous across PMAY-Gramin and PMAY-Urban variants",
    },
    {
        "canonical_label": "Pradhan Mantri Kaushal Vikas Yojana 4.0 - Recognition Of Prior Learning",
        "alias": "PMKVY 4.0",
        "reason": "ambiguous across three PMKVY 4.0 pathways",
    },
    {
        "canonical_label": "Pradhan Mantri Kaushal Vikas Yojana 4.0 - Recognition Of Prior Learning",
        "alias": "RPL",
        "reason": "component acronym already belongs to separate controlled entity and is not unique scheme identity",
    },
)


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def token_span(text: str, start: int, end: int) -> list[int]:
    tokens = list(re.finditer(r"\S+", text))
    starts = [match.start() for match in tokens]
    first = max(0, bisect.bisect_right(starts, start) - 1)
    while first < len(tokens) and tokens[first].end() <= start:
        first += 1
    last = first
    while last < len(tokens) and tokens[last].start() < end:
        last += 1
    return [first, last]


def occurrence(
    *,
    phrase: str,
    text: str,
    match: re.Match[str],
    artifact_path: Path,
    artifact_type: str,
    document_id: str,
    source_id: str,
    chunk_id: str | None,
    source_sha256: str,
    span_scope: str,
) -> dict[str, Any]:
    start, end = match.span()
    return {
        "artifact_path": str(artifact_path.relative_to(ROOT)),
        "artifact_type": artifact_type,
        "artifact_sha256": sha256_file(artifact_path),
        "source_artifact_sha256": source_sha256,
        "source_document_id": document_id,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "matched_text": text[start:end],
        "character_span": [start, end],
        "token_span": token_span(text, start, end),
        "span_scope": span_scope,
        "exact_excerpt": " ".join(text[max(0, start - 110) : min(len(text), end + 150)].split()),
        "searched_phrase": phrase,
    }


def find_in_text(
    phrase: str,
    text: str,
    *,
    artifact_path: Path,
    artifact_type: str,
    document_id: str,
    source_id: str,
    chunk_id: str | None,
    source_sha256: str,
    span_scope: str,
) -> list[dict[str, Any]]:
    pattern = re.compile(re.escape(phrase), re.IGNORECASE)
    return [
        occurrence(
            phrase=phrase, text=text, match=match, artifact_path=artifact_path,
            artifact_type=artifact_type, document_id=document_id, source_id=source_id,
            chunk_id=chunk_id, source_sha256=source_sha256, span_scope=span_scope,
        )
        for match in pattern.finditer(text)
    ]


def corpus_occurrences(
    phrase: str,
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    documents_path = ROOT / "data/v2/pilot/extracted/documents.jsonl"
    chunks_path = ROOT / "data/v2/pilot/chunks/chunks.jsonl"
    doc_by_source = {str(row["source_id"]): row for row in documents}
    findings: list[dict[str, Any]] = []
    for row in documents:
        findings.extend(find_in_text(
            phrase, str(row["text"]), artifact_path=documents_path, artifact_type="extracted_document_text",
            document_id=str(row["document_id"]), source_id=str(row["source_id"]), chunk_id=None,
            source_sha256=str(row["source_sha256"]), span_scope="document.text",
        ))
    for row in chunks:
        findings.extend(find_in_text(
            phrase, str(row["text"]), artifact_path=chunks_path, artifact_type="frozen_chunk_text",
            document_id=str(row["document_id"]), source_id=str(row["source_id"]), chunk_id=str(row["chunk_id"]),
            source_sha256=str(row["source_sha256"]), span_scope="chunk.text",
        ))
    for row in manifest:
        raw_path = ROOT / str(row["raw_snapshot_path"])
        if raw_path.suffix != ".json":
            continue
        raw_text = raw_path.read_text(encoding="utf-8")
        document = doc_by_source[str(row["source_id"])]
        findings.extend(find_in_text(
            phrase, raw_text, artifact_path=raw_path, artifact_type="raw_source_snapshot",
            document_id=str(document["document_id"]), source_id=str(row["source_id"]), chunk_id=None,
            source_sha256=str(row["raw_sha256"]), span_scope="raw artifact UTF-8 text",
        ))
    return sorted(findings, key=lambda row: (row["artifact_path"], row["span_scope"], row["character_span"][0], row["chunk_id"] or ""))


def candidate_view(phrase: str, findings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "artifact_path": row["artifact_path"],
            "document_id": row["source_document_id"],
            "source_id": row["source_id"],
            "chunk_id": row["chunk_id"],
            "matched_text": row["matched_text"],
            "exact_excerpt": row["exact_excerpt"],
            "character_span": row["character_span"],
            "token_span": row["token_span"],
            "source_artifact_sha256": row["source_artifact_sha256"],
        }
        for row in findings
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-v3-1", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    paths = {name: getattr(args, name).resolve() for name in ("registry_v3_1", "chunks", "documents", "source_manifest", "output")}
    approved = {
        "registry_v3_1": (ROOT / "data/v2/pilot/graph/entity_registry_v3_1.jsonl").resolve(),
        "chunks": (ROOT / "data/v2/pilot/chunks/chunks.jsonl").resolve(),
        "documents": (ROOT / "data/v2/pilot/extracted/documents.jsonl").resolve(),
        "source_manifest": (ROOT / "data/v2/pilot/manifests/raw_sources.jsonl").resolve(),
        "output": OUTPUT.resolve(),
    }
    if paths != approved:
        raise ValueError("alias audit requires approved frozen corpus-only paths")
    output_files = [
        paths["output"] / "ujjwala_alias_evidence.json",
        paths["output"] / "scheme_alias_completeness_audit.json",
        paths["output"] / "scheme_alias_completeness_audit.md",
        paths["output"] / "accepted_alias_additions.json",
        paths["output"] / "rejected_alias_candidates.json",
    ]
    if not args.overwrite and any(path.exists() for path in output_files):
        raise FileExistsError("alias audit outputs exist; pass --overwrite explicitly")
    registry = parse_jsonl(paths["registry_v3_1"])
    chunks = parse_jsonl(paths["chunks"])
    documents = parse_jsonl(paths["documents"])
    manifest = parse_jsonl(paths["source_manifest"])
    schemes = sorted(
        (row for row in registry if row["status"] == "accepted" and row["entity_type"] == "scheme"),
        key=lambda row: str(row["canonical_label"]),
    )
    if len(schemes) != 22:
        raise ValueError(f"expected 22 accepted canonical schemes, got {len(schemes)}")
    scheme_by_label = {normalize_text(str(row["canonical_label"])): row for row in schemes}
    document_by_id = {str(row["document_id"]): row for row in documents}
    manifest_by_source = {str(row["source_id"]): row for row in manifest}

    occurrence_cache: dict[str, list[dict[str, Any]]] = {}
    for spec in (*ACCEPTED_SPECS, *REJECTED_SPECS):
        occurrence_cache.setdefault(str(spec["alias"]), corpus_occurrences(str(spec["alias"]), documents, chunks, manifest))
    accepted: list[dict[str, Any]] = []
    for spec in ACCEPTED_SPECS:
        canonical = str(spec["canonical_label"])
        alias = str(spec["alias"])
        scheme = scheme_by_label.get(normalize_text(canonical))
        if not scheme:
            raise ValueError(f"accepted alias canonical scheme missing: {canonical}")
        findings = occurrence_cache[alias]
        scheme_documents = set(map(str, scheme["source_document_ids"]))
        same_scheme_findings = [row for row in findings if row["source_document_id"] in scheme_documents]
        if not same_scheme_findings:
            raise ValueError(f"accepted alias lacks exact occurrence in canonical source document: {alias}")
        if normalize_text(alias) in {normalize_text(value) for value in [scheme["canonical_label"], *scheme["aliases"]]}:
            raise ValueError(f"accepted addition already present: {canonical} -> {alias}")
        accepted.append({
            "canonical_entity_id_v3_1": scheme["entity_id"],
            "canonical_label": canonical,
            "alias": alias,
            "normalized_alias": normalize_text(alias),
            "extraction_rule": spec["rule"],
            "evidence_document_ids": sorted({row["source_document_id"] for row in same_scheme_findings}),
            "evidence_chunk_ids": sorted({row["chunk_id"] for row in same_scheme_findings if row["chunk_id"]}),
            "evidence_source_ids": sorted({row["source_id"] for row in same_scheme_findings}),
            "evidence": candidate_view(alias, same_scheme_findings),
            "acceptance_basis": "exact frozen-corpus phrase; unambiguous existing canonical scheme; missing from v3.1 aliases",
        })
    normalized_additions = [row["normalized_alias"] for row in accepted]
    if len(normalized_additions) != len(set(normalized_additions)):
        raise ValueError("accepted alias additions collide after normalization")

    rejected: list[dict[str, Any]] = []
    for spec in REJECTED_SPECS:
        canonical, alias = str(spec["canonical_label"]), str(spec["alias"])
        findings = occurrence_cache[alias]
        rejected.append({
            "canonical_label": canonical,
            "alias": alias,
            "normalized_alias": normalize_text(alias),
            "reason": spec["reason"],
            "corpus_occurrence_count": len(findings),
            "sample_evidence": candidate_view(alias, findings[:8]),
            "activated": False,
        })

    audits: list[dict[str, Any]] = []
    accepted_by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected_by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in accepted:
        accepted_by_canonical[normalize_text(row["canonical_label"])].append(row)
    for row in rejected:
        rejected_by_canonical[normalize_text(row["canonical_label"])].append(row)
    acronym_pattern = re.compile(r"\((?P<alias>[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,2})\)")
    numbered_pattern = re.compile(r"\b(?:PM[A-Z][A-Z0-9-]*|Ujjwala|PMKVY)\s+\d+\.\d+\b", re.IGNORECASE)
    popular_pattern = re.compile(r"\b(?:or|as)\s+([A-Z][A-Z0-9-]{1,14})\s+as\s+it\s+is\s+popularly\s+known", re.IGNORECASE)
    for scheme in schemes:
        key = normalize_text(str(scheme["canonical_label"]))
        doc_ids = list(map(str, scheme["source_document_ids"]))
        scheme_docs = [document_by_id[doc_id] for doc_id in doc_ids]
        source_rows = [manifest_by_source[str(row["source_id"])] for row in scheme_docs]
        structured_shorts: list[str] = []
        for source_row in source_rows:
            raw_path = ROOT / str(source_row["raw_snapshot_path"])
            if raw_path.suffix == ".json":
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
                basic = (((payload.get("data") or {}).get("en") or {}).get("basicDetails") or {})
                short = str(basic.get("schemeShortTitle") or "").strip()
                if short:
                    structured_shorts.append(short)
        combined = "\n".join(str(row["text"]) for row in scheme_docs)
        parenthetical = sorted({match.group("alias") for match in acronym_pattern.finditer(combined)})
        numbered = sorted({match.group(0) for match in numbered_pattern.finditer(combined)}, key=lambda value: (normalize_text(value), value))
        popular = sorted({match.group(1) for match in popular_pattern.finditer(combined)})
        additions = accepted_by_canonical[key]
        rejections = rejected_by_canonical[key]
        evidence_phrases = sorted({*map(str, scheme["aliases"]), *structured_shorts, *(row["alias"] for row in additions)})
        excerpts: list[dict[str, Any]] = []
        for phrase in evidence_phrases:
            matches = corpus_occurrences(phrase, scheme_docs, [row for row in chunks if row["document_id"] in doc_ids], source_rows)
            excerpts.extend(candidate_view(phrase, matches[:3]))
        audits.append({
            "canonical_entity_id_v3_1": scheme["entity_id"],
            "canonical_title": scheme["canonical_label"],
            "source_document_ids": doc_ids,
            "existing_aliases": scheme["aliases"],
            "structured_source_short_titles": sorted(set(structured_shorts)),
            "explicit_parenthetical_acronyms": parenthetical,
            "explicit_popularly_known_as_names": popular,
            "explicit_numbered_phase_names": numbered,
            "exact_corpus_excerpts": sorted(excerpts, key=lambda row: (row["artifact_path"], row["character_span"][0], row["matched_text"])),
            "accepted_corpus_backed_alias_additions": [row["alias"] for row in additions],
            "accepted_aliases_after_v3_2": sorted({*map(str, scheme["aliases"]), *(row["alias"] for row in additions)}, key=lambda value: (normalize_text(value), value)),
            "ambiguous_alias_candidates": [row["alias"] for row in rejections if "ambiguous" in row["reason"] or "multiple" in row["reason"]],
            "rejected_candidates": [{"alias": row["alias"], "reason": row["reason"]} for row in rejections],
        })

    ujjwala_findings = occurrence_cache["Ujjwala 2.0"]
    ujjwala_evidence = {
        "alias": "Ujjwala 2.0",
        "canonical_mapping": "Pradhan Mantri Ujjwala Yojana 2.0",
        "evidence_source": "frozen corpus/document/source artifacts only",
        "forbidden_evidence_read": False,
        "proof": "Exact numbered-phase phrase occurs in PMUY/PMUY2 corpus artifacts; PMUY2 source text explicitly uses both full canonical title and 'Ujjwala 2.0' for same numbered phase.",
        "occurrence_count": len(ujjwala_findings),
        "occurrences": ujjwala_findings,
        "input_hashes": {
            str(paths["chunks"].relative_to(ROOT)): sha256_file(paths["chunks"]),
            str(paths["documents"].relative_to(ROOT)): sha256_file(paths["documents"]),
            str(paths["source_manifest"].relative_to(ROOT)): sha256_file(paths["source_manifest"]),
            str(paths["registry_v3_1"].relative_to(ROOT)): sha256_file(paths["registry_v3_1"]),
        },
    }
    completeness = {
        "status": "corpus_only_complete_before_v3_2_registry_change",
        "scheme_count": len(audits),
        "allowed_evidence_rules": [
            "title followed by acronym in parentheses",
            "acronym followed by long form",
            "explicit popularly-known-as phrase",
            "repeated official short title",
            "official numbered phase name",
            "structured source short title",
        ],
        "forbidden_inputs_read": [],
        "accepted_addition_count": len(accepted),
        "rejected_candidate_count": len(rejected),
        "schemes": audits,
    }
    accepted_output = {
        "status": "approved_by_corpus_evidence_not_retrieval_performance",
        "registry_source_version": "entity-registry-v3.1",
        "target_registry_version": "entity-registry-v3.2",
        "additions": sorted(accepted, key=lambda row: (row["canonical_label"], row["normalized_alias"])),
        "input_hashes": ujjwala_evidence["input_hashes"],
    }
    rejected_output = {
        "status": "not_activated",
        "candidates": sorted(rejected, key=lambda row: (row["canonical_label"], row["normalized_alias"])),
        "query_or_performance_evidence_used": False,
    }
    md = [
        "# Scheme Alias Completeness Audit — entity-registry-v3.2\n",
        "Corpus-only audit. QA, qrels, graph paths, rankings, traces, and metrics were not inputs.\n",
        f"- Schemes audited: {len(audits)}\n",
        f"- Accepted additions: {len(accepted)}\n",
        f"- Rejected candidates: {len(rejected)}\n",
        "\n## Accepted additions\n",
    ]
    md.extend(f"- `{row['alias']}` → `{row['canonical_label']}` ({row['extraction_rule']})\n" for row in accepted_output["additions"])
    md.append("\n## Rejected candidates\n")
    md.extend(f"- `{row['alias']}` → `{row['canonical_label']}`: {row['reason']}\n" for row in rejected_output["candidates"])
    md.append("\n## All 22 schemes\n")
    for row in audits:
        md.extend([
            f"\n### {row['canonical_title']}\n",
            f"- Existing aliases: {', '.join(row['existing_aliases']) or 'none'}\n",
            f"- Accepted additions: {', '.join(row['accepted_corpus_backed_alias_additions']) or 'none'}\n",
            f"- Rejected: {', '.join(item['alias'] for item in row['rejected_candidates']) or 'none'}\n",
        ])
    write_json(output_files[0], ujjwala_evidence, overwrite=args.overwrite)
    write_json(output_files[1], completeness, overwrite=args.overwrite)
    write_bytes(output_files[2], "".join(md).encode("utf-8"), overwrite=args.overwrite)
    write_json(output_files[3], accepted_output, overwrite=args.overwrite)
    write_json(output_files[4], rejected_output, overwrite=args.overwrite)
    print(stable_json({
        "schemes": len(audits),
        "ujjwala_occurrences": len(ujjwala_findings),
        "accepted_additions": [{"alias": row["alias"], "canonical_label": row["canonical_label"]} for row in accepted_output["additions"]],
        "rejected_candidates": len(rejected),
    }))


if __name__ == "__main__":
    main()
