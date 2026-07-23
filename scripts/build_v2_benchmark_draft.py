#!/usr/bin/env python3
"""Build auditable, pending-review Phase 1 QA and qrels draft."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.v2_validator import validate_benchmark
from src.contracts.benchmark import QAItemV2, QrelsJudgment
from src.utils.atomic_io import write_json, write_jsonl

SINGLE = {
    "exact_lookup": ["pmay-g", "pmfby", "pmjdy", "pmmy", "mgnrega", "ab-pmjay"],
    "terminology": ["pmjjby", "pmsby", "apy", "pm-poshan", "pm-janman", "pm-svanidhi"],
    "paraphrase": ["pmuy", "pm-gkay", "pmegp", "pmkvy-rpl", "pmkvy-stt", "pmay-u"],
    "entity_relation": ["pmuy2", "pmkvy-sp", "pmfby", "pmmy", "mgnrega", "ab-pmjay"],
}
MULTI = [
    ("pmay-g", "pmay-u", "housing setting"), ("pmjjby", "pmsby", "insurance coverage"),
    ("pmkvy-rpl", "pmkvy-stt", "skills pathway"), ("pmuy", "pmuy2", "clean-cooking access"),
    ("pmfby", "pm-kisan-guidelines", "farmer support"), ("pmmy", "pmegp", "enterprise finance"),
]
SYNTHESIS = [
    (("pmjdy", "pmjjby", "pmsby"), "financial inclusion and insurance"),
    (("pmfby", "pm-kisan-guidelines", "pm-kmy-guidelines"), "farmer risk, income, and pension support"),
    (("pmmy", "pmegp", "pm-svanidhi"), "small-enterprise livelihood support"),
    (("pmay-g", "pmuy", "pm-gkay"), "household housing, cooking, and food support"),
]


def quote(chunk: dict) -> str:
    text = chunk["text"]
    stop = min(len(text), 420)
    sentence = text[:stop]
    if ". " in sentence[100:]:
        sentence = sentence[:sentence.rfind(". ") + 1]
    return sentence.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    root = args.pilot_root.resolve()
    if root != (ROOT / "data/v2/pilot").resolve():
        raise ValueError("pilot-root must be data/v2/pilot")
    documents = [json.loads(x) for x in (root / "extracted/documents.jsonl").read_text().splitlines()]
    chunks = [json.loads(x) for x in (root / "chunks/chunks.jsonl").read_text().splitlines()]
    docs = {x["scheme_id"]: x for x in documents}
    first = {}
    for chunk in sorted(chunks, key=lambda x: (x["document_id"], x["chunk_index"])):
        first.setdefault(chunk["document_id"], chunk)
    items: list[QAItemV2] = []

    def add(category: str, schemes: tuple[str, ...], question: str, bridge: str = "") -> None:
        evidence = [first[docs[scheme]["document_id"]] for scheme in schemes]
        quotes = tuple(quote(x) for x in evidence)
        items.append(QAItemV2(
            "2.0", f"v2q-{len(items)+1:03d}", "pilot-qa-v2-draft", category,
            "hard" if category in {"multi_hop", "synthesis"} else "medium", question,
            " ".join(quotes), tuple(x["chunk_id"] for x in evidence),
            tuple(x["document_id"] for x in evidence), quotes, "curated_template_extractive_draft",
            "pending_human_review", 0, "dev", "Diagnostic/development item; human acceptance pending.", bridge,
        ))

    for category, schemes in SINGLE.items():
        for scheme in schemes:
            title = docs[scheme]["title"]
            ministry = docs[scheme]["ministry"]
            if category == "exact_lookup":
                question = f"What official purpose and beneficiary support are stated for {title}?"
            elif category == "terminology":
                question = f"What programme does official term “{title}” identify, and what support does it provide?"
            elif category == "paraphrase":
                question = f"How does {title} help its intended participants under published conditions?"
            else:
                question = f"What relationship does {ministry} have with {title}, and what programme function is described?"
            add(category, (scheme,), question)
    for left, right, bridge in MULTI:
        add("multi_hop", (left, right),
            f"Which two official programmes address distinct sides of {bridge}, and how does each programme contribute?",
            bridge)
    for schemes, theme in SYNTHESIS:
        add("synthesis", schemes,
            f"How do three official programmes collectively cover {theme}, and what separate role does each play?")

    qa = [x.to_dict() for x in items]
    qrels = []
    for item in items:
        for chunk_id in item.gold_evidence_ids:
            row = QrelsJudgment("2.0", item.question_id, chunk_id, 2, "explicit_gold_evidence",
                                "pending_human_review", "Direct extractive support; human review pending.").to_dict()
            row["judgment_id"] = f"{item.question_id}:{chunk_id}"
            qrels.append(row)
    audit = validate_benchmark(qa, qrels, chunks)
    audit["multi_hop"] = {"count": 6, "all_cross_document": True, "lexical_shortcut_review": "pending_human_review",
                          "target_scheme_names_omitted_from_question_templates": True}
    audit["synthesis"] = {"count": 4, "minimum_gold_chunks": 3, "all_clause_mapping_review": "pending_human_review"}
    audit["ground_truth_status"] = "development draft; not final ground truth"
    write_jsonl(root / "qa/qa_draft.jsonl", qa, key="question_id", overwrite=args.overwrite)
    write_jsonl(root / "qrels/qrels_draft.jsonl", qrels, key="judgment_id", overwrite=args.overwrite)
    write_json(root / "audits/qa_validation.json", audit, overwrite=args.overwrite)
    print(json.dumps({"qa": len(qa), "qrels": len(qrels), **audit["category_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
