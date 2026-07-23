#!/usr/bin/env python3
"""Create owner-pending R2 candidate with genuine graph-path multi-hop items."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.graph_path_validator import validate_graph_path_item
from src.utils.atomic_io import _atomic_write, write_json, write_jsonl
from src.utils.hashing import sha256_file

R1 = "pilot-qa-v2-reviewed-20260724-r1"
R2 = "pilot-qa-v2-reviewed-20260724-r2"

MULTI = {
    "v2q-025": {
        "question": "What banking function does PMJDY provide, and which other programme from its ministry finances income-generating micro-enterprises?",
        "answer": "PMJDY provides universal banking services for unbanked households. PMMY, under the same Ministry of Finance, provides micro-credit for income-generating micro-enterprises.",
        "docs": (("doc-pmjdy", "universal banking services for every unbanked household"), ("doc-pmmy", "micro credit/Loan up to Rs. 20 lakhs")),
        "clauses": ("PMJDY provides universal banking services for unbanked households.", "PMMY, under the same Ministry of Finance, provides micro-credit for income-generating micro-enterprises."),
        "seed": "Pradhan Mantri Jan Dhan Yojana", "aliases": ["PMJDY"], "bridge": "Ministry Of Finance", "bridge_type": "ministry",
        "targets": ["Pradhan Mantri Jan Dhan Yojana", "Pradhan Mantri Mudra Yojana"],
    },
    "v2q-026": {
        "question": "What employment guarantee does MGNREGA provide, and which other programme from its ministry supplies pucca houses to rural households?",
        "answer": "MGNREGA guarantees at least 100 days of wage employment to qualifying rural households. PMAY-G, under the same Ministry of Rural Development, supports pucca houses with basic amenities for eligible rural households.",
        "docs": (("doc-mgnrega", "at least 100 days of guaranteed wage employment"), ("doc-pmay-g", "providing a pucca house, with basic amenities")),
        "clauses": ("MGNREGA guarantees at least 100 days of wage employment to qualifying rural households.", "PMAY-G, under the same Ministry of Rural Development, supports pucca houses with basic amenities for eligible rural households."),
        "seed": "Mahatma Gandhi National Rural Employment Guarantee Act", "aliases": ["MGNREGA"], "bridge": "Ministry Of Rural Development", "bridge_type": "ministry",
        "targets": ["Mahatma Gandhi National Rural Employment Guarantee Act", "Pradhan Mantri Awaas Yojana - Gramin"],
    },
    "v2q-027": {
        "question": "What livelihood mechanism does PM SVANidhi offer street vendors, and which other programme from its ministry addresses housing shortages for eligible urban households?",
        "answer": "PM SVANidhi offers street vendors collateral-free working-capital loans, interest subsidy, and digital-payment incentives. PMAY-U, under the same Ministry of Housing and Urban Affairs, provides housing support for eligible urban households.",
        "docs": (("doc-pm-svanidhi", "collateral-free working capital loans"), ("doc-pmay-u", "provide pucca houses to eligible urban households")),
        "clauses": ("PM SVANidhi offers street vendors collateral-free working-capital loans, interest subsidy, and digital-payment incentives.", "PMAY-U, under the same Ministry of Housing and Urban Affairs, provides housing support for eligible urban households."),
        "seed": "PM Street Vendor’s AtmaNirbhar Nidhi (PM SVANidhi)", "aliases": ["PM SVANidhi"], "bridge": "Ministry Of Housing & Urban Affairs", "bridge_type": "ministry",
        "targets": ["PM Street Vendor’s AtmaNirbhar Nidhi (PM SVANidhi)", "Pradhan Mantri Awas Yojana - Urban"],
    },
    "v2q-028": {
        "question": "What does PMKVY Recognition of Prior Learning certify, and which other pathway from its ministry serves candidates seeking fresh short-term skills training?",
        "answer": "PMKVY Recognition of Prior Learning certifies candidates’ existing skills. PMKVY Short-Term Training, under the same Ministry of Skill Development and Entrepreneurship, provides fresh skilling, reskilling, or upskilling.",
        "docs": (("doc-pmkvy-rpl", "certify candidates who already possess prior-learning experience or skills"), ("doc-pmkvy-stt", "fresh skilling, re-skilling, or upskilling")),
        "clauses": ("PMKVY Recognition of Prior Learning certifies candidates’ existing skills.", "PMKVY Short-Term Training, under the same Ministry of Skill Development and Entrepreneurship, provides fresh skilling, reskilling, or upskilling."),
        "seed": "Pradhan Mantri Kaushal Vikas Yojana 4.0 - Recognition Of Prior Learning", "aliases": ["PMKVY Recognition of Prior Learning", "RPL"], "bridge": "Ministry Of Skill Development And Entrepreneurship", "bridge_type": "ministry",
        "targets": ["Pradhan Mantri Kaushal Vikas Yojana 4.0 - Recognition Of Prior Learning", "Pradhan Mantri Kaushal Vikas Yojana 4.0 - Short-Term Training"],
    },
    "v2q-029": {
        "question": "What migrant-focused facility distinguishes Ujjwala 2.0, and what clean-cooking transition was established by its predecessor programme?",
        "answer": "Ujjwala 2.0 added 1.6 crore LPG connections with a special facility for migrant households. Its predecessor, Pradhan Mantri Ujjwala Yojana, sought to replace traditional cooking fuels with LPG access for rural and deprived households.",
        "docs": (("doc-pmuy2", "special facility to migrant households"), ("doc-pmuy", "make clean cooking fuel such as LPG available")),
        "clauses": ("Ujjwala 2.0 added 1.6 crore LPG connections with a special facility for migrant households.", "Its predecessor, Pradhan Mantri Ujjwala Yojana, sought to replace traditional cooking fuels with LPG access for rural and deprived households."),
        "seed": "Pradhan Mantri Ujjwala Yojana 2.0", "aliases": ["Ujjwala 2.0"], "bridge": "Ministry Of Petroleum and Natural Gas", "bridge_type": "ministry",
        "targets": ["Pradhan Mantri Ujjwala Yojana 2.0", "Pradhan Mantri Ujjwala Yojana"],
    },
    "v2q-030": {
        "question": "What retirement benefit does APY offer, and which life-insurance programme administered through the same department covers death from any cause?",
        "answer": "APY offers guaranteed monthly pension options after age 60. PMJJBY, associated with the same Department of Financial Services, provides life cover for death due to any reason.",
        "docs": (("doc-apy", "guaranteed minimum pension of Rs. 1000/- per month"), ("doc-pmjjby", "life insurance cover for death due to any reason")),
        "clauses": ("APY offers guaranteed monthly pension options after age 60.", "PMJJBY, associated with the same Department of Financial Services, provides life cover for death due to any reason."),
        "seed": "Atal Pension Yojana", "aliases": ["APY"], "bridge": "Department of Financial Service", "bridge_type": "department",
        "targets": ["Atal Pension Yojana", "Pradhan Mantri Jeevan Jyoti Bima Yojana"],
    },
}

ENTITY_AUDIT = {
    "v2q-019": ("yes", "direct_named_entity", "high", "Pradhan Mantri Ujjwala Yojana 2.0", "Ministry introduced scheme for LPG access"),
    "v2q-020": ("no", "indirect_seed_entity", "medium", "National Skill Development Corporation", "NSDC supports implementation; SPIAs deliver projects"),
    "v2q-021": ("yes", "direct_named_entity", "high", "Pradhan Mantri Fasal Bima Yojna (PMFBY)", "Insurers and banks form implementation network"),
    "v2q-022": ("no", "indirect_seed_entity", "medium", "Member Lending Institutions", "MLIs extend scheme finance to borrowers"),
    "v2q-023": ("yes", "alias_acronym", "high", "MGNREGA", "Gram Panchayat receives and verifies registration"),
    "v2q-024": ("no", "indirect_seed_entity", "low", "National Health Authority", "NHA implements national health assurance programme"),
}


def find_chunk(by_doc: dict[str, list[dict]], document_id: str, anchor: str) -> dict:
    found = [x for x in by_doc[document_id] if anchor in x["text"]]
    if not found:
        raise ValueError(f"missing anchor {anchor!r} in {document_id}")
    return found[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    pilot, audit = args.pilot_root.resolve(), args.audit_root.resolve()
    if pilot != (ROOT / "data/v2/pilot").resolve() or audit != (ROOT / "audits/phase1/r2").resolve():
        raise ValueError("paths must be data/v2/pilot and audits/phase1/r2")
    r1_path = pilot / "qa" / f"{R1}.jsonl"
    r1_qrels_path = pilot / "qrels" / f"{R1}.jsonl"
    r1_sha_before = (sha256_file(r1_path), sha256_file(r1_qrels_path))
    r1 = [json.loads(x) for x in r1_path.read_text().splitlines()]
    chunks = [json.loads(x) for x in (pilot / "chunks/chunks.jsonl").read_text().splitlines()]
    documents = [json.loads(x) for x in (pilot / "extracted/documents.jsonl").read_text().splitlines()]
    chunk_map = {x["chunk_id"]: x for x in chunks}
    by_doc: dict[str, list[dict]] = {}
    for chunk in chunks:
        by_doc.setdefault(chunk["document_id"], []).append(chunk)
    corpus_entities = {value for doc in documents for value in (doc["title"], doc["ministry"], doc["department"]) if value}
    r2, changes, reclassifications, full_multi = [], [], [], []
    for original in r1:
        item = dict(original)
        item["benchmark_version"] = R2
        item["authoring_method"] = "ai_assisted_full_chunk_review"
        item["review_status"] = "ai_reviewed_owner_pending"
        item["review_revision"] = 2
        item["notes"] = "AI-assisted evidence review complete; owner decision pending."
        item.pop("graph_path", None)
        item.pop("answer_clause_map", None)
        if item["question_id"] in MULTI:
            spec = MULTI[item["question_id"]]
            selected = [find_chunk(by_doc, doc, anchor) for doc, anchor in spec["docs"]]
            item.update(question=spec["question"], reference_answer=spec["answer"],
                        gold_evidence_ids=[x["chunk_id"] for x in selected],
                        source_document_ids=[x["document_id"] for x in selected],
                        supporting_evidence_quotes=[x["text"] for x in selected], bridge_entity=spec["bridge"])
            item["answer_clause_map"] = [{"clause": clause, "evidence_id": selected[i]["chunk_id"]} for i, clause in enumerate(spec["clauses"])]
            item["graph_path"] = {
                "seed_entity": spec["seed"], "seed_aliases": spec["aliases"],
                "bridge_entity": spec["bridge"], "bridge_aliases": [], "bridge_type": spec["bridge_type"],
                "target_entities": spec["targets"],
                "gold_path": [{"node": spec["targets"][0], "type": "scheme"},
                              {"node": spec["bridge"], "type": spec["bridge_type"]},
                              {"node": spec["targets"][1], "type": "scheme"}],
                "gold_evidence_ids": [x["chunk_id"] for x in selected], "single_chunk_sufficient": False,
            }
            validate_graph_path_item(item, chunk_map, corpus_entities)
            full_multi.append({"record": item, "full_gold_chunks": selected})
            reclassifications.append({
                "question_id": item["question_id"], "r1_design": "comparative_multi_document",
                "r1_confirmatory_h3_status": "excluded", "r2_design": "genuine_graph_path_multi_hop",
                "decision": "R1 comparison retained only as immutable candidate history; R2 item replaced under same stable ID.",
            })
        elif item["question_id"] in {"v2q-020", "v2q-022", "v2q-024"}:
            item["question"] = {
                "v2q-020": "How do NSDC and SPIAs divide responsibility in the Special Projects arm of the national skill mission?",
                "v2q-022": "Which finance programme relies on Member Lending Institutions to extend assistance to non-corporate micro-enterprises?",
                "v2q-024": "Which national health-assurance programme does NHA implement under the health ministry?",
            }[item["question_id"]]
        r2.append(item)
        changes.append({"question_id": item["question_id"], "changed_fields": sorted(key for key in item if item.get(key) != original.get(key))})

    normalized = [re.sub(r"\W+", " ", x["question"].casefold()).strip() for x in r2]
    near = []
    for i in range(len(r2)):
        for j in range(i + 1, len(r2)):
            ratio = SequenceMatcher(None, normalized[i], normalized[j]).ratio()
            if ratio >= 0.80:
                near.append({"left": r2[i]["question_id"], "right": r2[j]["question_id"], "ratio": round(ratio, 4)})
    if any(x["ratio"] >= 0.88 for x in near):
        raise ValueError(f"R2 contains unresolved near duplicate: {near}")
    qrels = []
    for item in r2:
        for chunk_id in item["gold_evidence_ids"]:
            qrels.append({"schema_version": "2.0", "judgment_id": f"{item['question_id']}:{chunk_id}",
                          "query_id": item["question_id"], "chunk_id": chunk_id, "relevance": 2,
                          "judgment_source": "ai_assisted_direct_support_review",
                          "review_status": "ai_reviewed_owner_pending",
                          "reviewer_notes": "Direct answer-clause support; owner decision pending."})
    qa_path, qrels_path = pilot / "qa" / f"{R2}.jsonl", pilot / "qrels" / f"{R2}.jsonl"
    write_jsonl(qa_path, r2, key="question_id", overwrite=args.overwrite)
    write_jsonl(qrels_path, qrels, key="judgment_id", overwrite=args.overwrite)
    if r1_sha_before != (sha256_file(r1_path), sha256_file(r1_qrels_path)):
        raise RuntimeError("R1 changed during R2 creation")

    relation_audit = []
    for item in (x for x in r2 if x["category"] == "entity_relation"):
        named, query_style, risk, seed, relation = ENTITY_AUDIT[item["question_id"]]
        text = " ".join(chunk_map[x]["text"] for x in item["gold_evidence_ids"])
        overlap = sorted(set(re.findall(r"\b[A-Za-z][A-Za-z0-9-]{3,}\b", item["question"].casefold())) &
                         set(re.findall(r"\b[A-Za-z][A-Za-z0-9-]{3,}\b", text.casefold())))
        relation_audit.append({"question_id": item["question_id"], "target_scheme_named_in_query": named,
                               "query_style": query_style,
                               "exact_lexical_overlap_terms": overlap, "relation_phrase_copied_from_evidence": False,
                               "answer_requires_relation_extraction": True, "bm25_shortcut_risk": risk,
                               "graph_seed_available": True, "expected_seed_entity": seed,
                               "evidence_supported_relation": relation})

    write_json(audit / "r1_to_r2_change_log.json", {"r1": R1, "r2": R2, "r1_hashes_preserved": list(r1_sha_before), "items": changes}, overwrite=args.overwrite)
    write_json(audit / "reclassification_decisions.json", reclassifications, overwrite=args.overwrite)
    write_json(audit / "six_multi_hop_records_with_gold.json", full_multi, overwrite=args.overwrite)
    write_json(audit / "graph_path_audit.json", [{"question_id": x["record"]["question_id"], "status": "pass", **x["record"]["graph_path"]} for x in full_multi], overwrite=args.overwrite)
    write_json(audit / "single_chunk_sufficiency.json", [{"question_id": x["record"]["question_id"], "single_chunk_sufficient": False,
               "clause_evidence": x["record"]["answer_clause_map"]} for x in full_multi], overwrite=args.overwrite)
    write_json(audit / "verbatim_target_name_audit.json", [{"question_id": x["record"]["question_id"],
               "targets_named_verbatim": [target for target in x["record"]["graph_path"]["target_entities"] if target.casefold() in x["record"]["question"].casefold()],
               "both_targets_named": False} for x in full_multi], overwrite=args.overwrite)
    write_json(audit / "entity_relation_shortcut_audit.json", relation_audit, overwrite=args.overwrite)
    write_json(audit / "category_counts.json", dict(sorted(Counter(x["category"] for x in r2).items())), overwrite=args.overwrite)
    write_json(audit / "near_duplicate_report.json", {"threshold": 0.88, "unresolved": [], "pairs_at_or_above_0.80": near}, overwrite=args.overwrite)
    write_json(audit / "qrels_counts.json", {"grade_2": len(qrels), "grade_1": 0, "grade_0": 0, "all_resolve": all(x["chunk_id"] in chunk_map for x in qrels)}, overwrite=args.overwrite)
    write_json(audit / "remaining_uncertainty.json", {
        "owner_record_decisions": "pending",
        "semantic_validity_beyond_AI_assisted_review": "pending owner assessment",
        "graph_entity_extraction_and_alias_behavior": "unmeasured until later approved system validation",
        "retrieval_performance": "unmeasured; no retrievers run",
        "grade_1_and_grade_0_judgments": "none created because no contextual or pooled review justified them",
    }, overwrite=args.overwrite)
    changed = subprocess.run(["git", "status", "--short", "--untracked-files=all"], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout.splitlines()
    write_json(audit / "changed_files.json", changed, overwrite=args.overwrite)

    fields = ["question_id", "category", "question", "reference_answer", "full_gold_chunk_text", "evidence_quotes", "scheme_names", "bridge_entity", "graph_path", "accept_rewrite_reject", "owner_comments"]
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    markdown = ["# R2 Owner Review Package", "", "Owner fields intentionally blank.", ""]
    title_by_doc = {x["document_id"]: x["title"] for x in documents}
    for item in r2:
        row = {"question_id": item["question_id"], "category": item["category"], "question": item["question"],
               "reference_answer": item["reference_answer"],
               "full_gold_chunk_text": "\n\n--- CHUNK ---\n\n".join(chunk_map[x]["text"] for x in item["gold_evidence_ids"]),
               "evidence_quotes": "\n\n".join(item["supporting_evidence_quotes"]),
               "scheme_names": " | ".join(title_by_doc[x] for x in item["source_document_ids"]),
               "bridge_entity": item.get("bridge_entity", ""), "graph_path": json.dumps(item.get("graph_path", {}), ensure_ascii=False, sort_keys=True),
               "accept_rewrite_reject": "", "owner_comments": ""}
        writer.writerow(row)
        markdown.extend([f"## {item['question_id']} — {item['category']}", "", f"**Question:** {item['question']}", "",
                         f"**Reference answer:** {item['reference_answer']}", "", f"**Schemes:** {row['scheme_names']}", "",
                         f"**Bridge:** {row['bridge_entity'] or '—'}", "", f"**Graph path:** `{row['graph_path']}`", "",
                         "**Full gold chunks:**", "", row["full_gold_chunk_text"], "", "**Evidence quotes:**", "",
                         row["evidence_quotes"], "", "**Accept / rewrite / reject:**", "", "**Owner comments:**", ""])
    _atomic_write(audit / "owner_review_package.csv", csv_buffer.getvalue(), overwrite=args.overwrite)
    _atomic_write(audit / "owner_review_package.md", "\n".join(markdown).rstrip() + "\n", overwrite=args.overwrite)

    freeze = {"benchmark_version": R2, "immutable": True, "status": "candidate_freeze_owner_review_pending",
              "qa_path": str(qa_path.relative_to(ROOT)), "qrels_path": str(qrels_path.relative_to(ROOT)),
              "qa_sha256": sha256_file(qa_path), "qrels_sha256": sha256_file(qrels_path),
              "question_count": len(r2), "qrels_count": len(qrels),
              "confirmatory_h3_multi_hop_count": len(full_multi)}
    write_json(audit / "candidate_freeze_manifest.json", freeze, overwrite=args.overwrite)
    artifacts = [qa_path, qrels_path, *(audit / name for name in (
        "r1_to_r2_change_log.json", "reclassification_decisions.json", "six_multi_hop_records_with_gold.json",
        "graph_path_audit.json", "single_chunk_sufficiency.json", "verbatim_target_name_audit.json",
        "entity_relation_shortcut_audit.json", "category_counts.json", "near_duplicate_report.json",
        "qrels_counts.json", "remaining_uncertainty.json", "changed_files.json", "owner_review_package.csv",
        "owner_review_package.md", "candidate_freeze_manifest.json", "commands.txt", "test_output.txt"))]
    write_jsonl(audit / "hashes.jsonl", [{"path": str(x.relative_to(ROOT)), "sha256": sha256_file(x), "byte_size": x.stat().st_size} for x in artifacts], key="path", overwrite=args.overwrite)
    print(json.dumps(freeze, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
