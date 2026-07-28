#!/usr/bin/env python3
"""Build offline Phase 8 R4 corpus and retrieval improvement experiments."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/phase8_r4_improvements"
DOCS = ROOT / "releases/v3_clean/data/processed/documents.jsonl"
CHUNKS = ROOT / "releases/v3_clean/data/chunks/chunks_v3_clean.jsonl"
QA = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qa_dataset.jsonl"
QRELS = ROOT / "runs/phase8_exploratory_automated_r3/benchmark/qrels_gold.tsv"
RUNS = {
    "bm25": ROOT / "runs/phase8_exploratory_five_system/bm25_top50/retrieval/bm25_run.jsonl",
    "faiss": ROOT / "runs/phase8_exploratory_automated_r3/results/retrieval/faiss_run.jsonl",
    "graph": ROOT / "runs/phase8_exploratory_five_system/graph_top50/retrieval/graphrag_run.jsonl",
}
WORD_TARGET = 450
WORD_OVERLAP = 60
SPLIT_SEED = "phase8-r4-split-v1"
SYNTHESIS_SEED = "phase8-r4-synthesis-v1"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def shingles(text: str, n: int = 5) -> set[tuple[str, ...]]:
    words = normalized(text).split()
    return {tuple(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def corpus_audit(documents: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    exact: dict[str, list[str]] = defaultdict(list)
    for doc in documents:
        exact[hashlib.sha256(normalized(doc["cleaned_text"]).encode()).hexdigest()].append(doc["doc_id"])
    exact_groups = [ids for ids in exact.values() if len(ids) > 1]
    doc_shingles = {doc["doc_id"]: shingles(doc["cleaned_text"]) for doc in documents}
    near = []
    for i, left in enumerate(documents):
        a = doc_shingles[left["doc_id"]]
        for right in documents[i + 1 :]:
            b = doc_shingles[right["doc_id"]]
            if not a or not b:
                continue
            length_ratio = min(len(a), len(b)) / max(len(a), len(b))
            if length_ratio < 0.8:
                continue
            score = len(a & b) / len(a | b)
            if score >= 0.85:
                near.append({"left": left["doc_id"], "right": right["doc_id"], "jaccard_5gram": round(score, 6)})
    repeated_prefixes = Counter(normalized(row["text"])[:240] for row in chunks if len(normalized(row["text"])) >= 240)
    noisy = []
    for row in chunks:
        text = row["text"]
        words = text.split()
        alpha = sum(char.isalpha() for char in text)
        printable = sum(char.isprintable() for char in text)
        reasons = []
        if len(words) < 40:
            reasons.append("short")
        if text and alpha / len(text) < 0.55:
            reasons.append("low_alpha_ratio")
        if text and printable / len(text) < 0.98:
            reasons.append("non_printable")
        if repeated_prefixes[normalized(text)[:240]] >= 3:
            reasons.append("repeated_prefix")
        if reasons:
            noisy.append({"chunk_id": row["chunk_id"], "doc_id": row["doc_id"], "reasons": reasons})
    return {
        "document_n": len(documents),
        "chunk_n": len(chunks),
        "exact_duplicate_groups": exact_groups,
        "exact_duplicate_document_n": sum(len(group) - 1 for group in exact_groups),
        "near_duplicate_pairs": near,
        "near_duplicate_pair_n": len(near),
        "noise_candidate_n": len(noisy),
        "noise_candidates": noisy,
        "policy": "Exact normalized duplicates may be canonicalized. Near duplicates and noise candidates require review; R4 does not silently delete them.",
    }


def heading(line: str) -> bool:
    value = " ".join(line.split())
    if not 3 <= len(value) <= 100:
        return False
    words = value.split()
    return len(words) <= 12 and (value.isupper() or re.match(r"^(\d+(?:\.\d+)*)\s+\S", value) is not None or value.istitle())


def rechunk(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for doc in documents:
        lines = [" ".join(line.split()) for line in doc["cleaned_text"].splitlines()]
        current_heading = doc.get("title") or "Untitled"
        units: list[tuple[str, str]] = []
        paragraph: list[str] = []
        for line in lines + [""]:
            if heading(line):
                if paragraph:
                    units.append((current_heading, " ".join(paragraph)))
                    paragraph = []
                current_heading = line
            elif line:
                paragraph.append(line)
            elif paragraph:
                units.append((current_heading, " ".join(paragraph)))
                paragraph = []
        words: list[str] = []
        section = current_heading
        chunk_index = 0
        for unit_heading, text in units:
            unit_words = text.split()
            if words and (unit_heading != section or len(words) + len(unit_words) > WORD_TARGET):
                body = " ".join(words)
                chunk_id = "r4chunk_" + hashlib.sha256(f"{doc['doc_id']}:{chunk_index}:{section}:{body}".encode()).hexdigest()[:12]
                output.append({"chunk_id": chunk_id, "doc_id": doc["doc_id"], "document_id": doc["doc_id"], "chunk_index": chunk_index, "section_title": section, "text": f"{doc.get('title','')} — {section}\n{body}", "word_count": len(words), "source": doc.get("source"), "url": doc.get("url"), "ministry": doc.get("ministry"), "scheme_name": doc.get("scheme_name"), "document_type": doc.get("document_type")})
                chunk_index += 1
                words = words[-WORD_OVERLAP:]
            section = unit_heading
            while len(words) + len(unit_words) > WORD_TARGET:
                take = max(1, WORD_TARGET - len(words))
                words.extend(unit_words[:take])
                unit_words = unit_words[take:]
                body = " ".join(words)
                chunk_id = "r4chunk_" + hashlib.sha256(f"{doc['doc_id']}:{chunk_index}:{section}:{body}".encode()).hexdigest()[:12]
                output.append({"chunk_id": chunk_id, "doc_id": doc["doc_id"], "document_id": doc["doc_id"], "chunk_index": chunk_index, "section_title": section, "text": f"{doc.get('title','')} — {section}\n{body}", "word_count": len(words), "source": doc.get("source"), "url": doc.get("url"), "ministry": doc.get("ministry"), "scheme_name": doc.get("scheme_name"), "document_type": doc.get("document_type")})
                chunk_index += 1
                words = words[-WORD_OVERLAP:]
            words.extend(unit_words)
        if words:
            body = " ".join(words)
            chunk_id = "r4chunk_" + hashlib.sha256(f"{doc['doc_id']}:{chunk_index}:{section}:{body}".encode()).hexdigest()[:12]
            output.append({"chunk_id": chunk_id, "doc_id": doc["doc_id"], "document_id": doc["doc_id"], "chunk_index": chunk_index, "section_title": section, "text": f"{doc.get('title','')} — {section}\n{body}", "word_count": len(words), "source": doc.get("source"), "url": doc.get("url"), "ministry": doc.get("ministry"), "scheme_name": doc.get("scheme_name"), "document_type": doc.get("document_type")})
    return output


def rechunk_balanced(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create balanced windows while retaining section headings in text."""

    output = []
    step = WORD_TARGET - WORD_OVERLAP
    for doc in documents:
        title = " ".join((doc.get("title") or "Untitled").split())
        current_heading = title
        tokens: list[str] = []
        heading_at_token: list[tuple[int, str]] = [(0, title)]
        for raw_line in doc["cleaned_text"].splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            if heading(line):
                current_heading = line
                heading_at_token.append((len(tokens), current_heading))
                tokens.extend(["SECTION:", current_heading])
            else:
                tokens.extend(line.split())
        for chunk_index, start in enumerate(range(0, len(tokens), step)):
            body_tokens = tokens[start : start + WORD_TARGET]
            if not body_tokens:
                continue
            active_heading = title
            for position, value in heading_at_token:
                if position <= start:
                    active_heading = value
                else:
                    break
            body = " ".join(body_tokens)
            chunk_id = "r4chunk_" + hashlib.sha256(f"{doc['doc_id']}:{chunk_index}:{active_heading}:{body}".encode()).hexdigest()[:12]
            output.append({
                "chunk_id": chunk_id,
                "doc_id": doc["doc_id"],
                "document_id": doc["doc_id"],
                "chunk_index": chunk_index,
                "section_title": active_heading,
                "text": f"{title} — {active_heading}\n{body}",
                "word_count": len(body_tokens),
                "source": doc.get("source"),
                "url": doc.get("url"),
                "ministry": doc.get("ministry"),
                "scheme_name": doc.get("scheme_name"),
                "document_type": doc.get("document_type"),
            })
            if start + WORD_TARGET >= len(tokens):
                break
    return output


def qrels() -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for line in QRELS.read_text().splitlines():
        query_id, _, chunk_id, relevance = line.split("\t")
        if int(relevance) > 0:
            result[query_id].add(chunk_id)
    return result


def crosswalk(old_chunks: list[dict[str, Any]], new_chunks: list[dict[str, Any]], gold: dict[str, set[str]], qa_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    old = {row["chunk_id"]: row for row in old_chunks}
    qa = {row["question_id"]: row for row in qa_rows}
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in new_chunks:
        by_doc[row["doc_id"]].append(row)
    rows, mapped = [], defaultdict(set)
    for query_id, ids in sorted(gold.items()):
        for old_id in sorted(ids):
            source = old[old_id]
            source_tokens = set(normalized(source["text"]).split())
            answer_tokens = set(normalized(qa[query_id]["reference_answer"]).split())
            candidates = []
            for candidate in by_doc[source["doc_id"]]:
                target_tokens = set(normalized(candidate["text"]).split())
                source_score = len(source_tokens & target_tokens) / max(1, min(len(source_tokens), len(target_tokens)))
                answer_score = len(answer_tokens & target_tokens) / max(1, len(answer_tokens))
                score = 0.8 * answer_score + 0.2 * source_score
                candidates.append((score, answer_score, source_score, candidate["chunk_id"]))
            score, answer_score, source_score, new_id = max(candidates, key=lambda item: (item[0], item[1], item[2], item[3]))
            mapped[query_id].add(new_id)
            rows.append({"query_id": query_id, "old_chunk_id": old_id, "new_chunk_id": new_id, "combined_score": round(score, 6), "reference_answer_coverage": round(answer_score, 6), "source_chunk_containment": round(source_score, 6), "status": "automatic_pending_human_validation"})
    return rows, dict(mapped)


def split_queries(qa_rows: list[dict[str, Any]]) -> dict[str, str]:
    by_category: dict[str, list[str]] = defaultdict(list)
    for row in qa_rows:
        by_category[row["category"]].append(row["question_id"])
    split = {}
    for category, ids in sorted(by_category.items()):
        ordered = sorted(ids, key=lambda qid: (hashlib.sha256(f"{SPLIT_SEED}:{qid}".encode()).hexdigest(), qid))
        for index, qid in enumerate(ordered):
            split[qid] = "dev" if index < 12 else "test"
    return split


def synthesis_candidates(qa_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(qa_rows, key=lambda row: (hashlib.sha256(f"{SYNTHESIS_SEED}:{row['question_id']}".encode()).hexdigest(), row["question_id"]))
    used: set[str] = set()
    output = []
    for left in ordered:
        if left["question_id"] in used:
            continue
        choices = [right for right in ordered if right["question_id"] not in used and right["question_id"] != left["question_id"] and set(right["source_doc_ids"]).isdisjoint(left["source_doc_ids"]) and right["category"] != left["category"]]
        if not choices:
            continue
        right = choices[0]
        used.update((left["question_id"], right["question_id"]))
        index = len(output) + 1
        output.append({
            "question_id": f"r4_syn_{index:03d}",
            "question": f"Using evidence from both programmes, answer these two parts: (1) {left['question']} (2) {right['question']}",
            "category": "synthesis",
            "difficulty": "hard",
            "reference_answer": f"Part 1: {left['reference_answer']} Part 2: {right['reference_answer']}",
            "gold_evidence_ids": sorted(set(left["gold_evidence_ids"]) | set(right["gold_evidence_ids"])),
            "source_doc_ids": sorted(set(left["source_doc_ids"]) | set(right["source_doc_ids"])),
            "component_query_ids": [left["question_id"], right["question_id"]],
            "split": "candidate",
            "review_status": "automated_candidate_pending_human_validation",
        })
        if len(output) == 20:
            break
    if len(output) != 20:
        raise RuntimeError("could not construct 20 cross-document synthesis candidates")
    return output


def indexed_runs() -> dict[str, dict[str, dict[str, Any]]]:
    return {name: {row["query_id"]: row for row in load_jsonl(path)} for name, path in RUNS.items()}


def fuse(inputs: list[tuple[dict[str, Any], float]], k: int, top_n: int = 50, graph_only_factor: float = 1.0) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    membership: Counter[str] = Counter()
    for run, weight in inputs:
        for result in run["results"][:50]:
            scores[result["chunk_id"]] += weight / (k + result["rank"])
            membership[result["chunk_id"]] += 1
    if graph_only_factor < 1 and inputs:
        graph_ids = {row["chunk_id"] for row in inputs[-1][0]["results"][:50]}
        for chunk_id in graph_ids:
            if membership[chunk_id] == 1:
                scores[chunk_id] *= graph_only_factor
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:top_n]


def query_metrics(ranking: list[str], relevant: set[str], cutoff: int = 10) -> dict[str, float]:
    top = ranking[:cutoff]
    ranks = [index for index, chunk_id in enumerate(top, 1) if chunk_id in relevant]
    mrr = 1 / ranks[0] if ranks else 0.0
    recall = len(set(top) & relevant) / len(relevant)
    dcg = sum(1 / math.log2(index + 1) for index, chunk_id in enumerate(top, 1) if chunk_id in relevant)
    ideal = sum(1 / math.log2(index + 1) for index in range(1, min(cutoff, len(relevant)) + 1))
    return {"mrr@10": mrr, "recall@10": recall, "ndcg@10": dcg / ideal if ideal else 0.0}


def aggregate(rankings: dict[str, list[str]], gold: dict[str, set[str]], ids: list[str]) -> dict[str, float]:
    values = [query_metrics(rankings[qid], gold[qid]) for qid in ids]
    return {key: round(sum(row[key] for row in values) / len(values), 6) for key in values[0]}


def retrieval_experiments(qa_rows: list[dict[str, Any]], gold: dict[str, set[str]], split: dict[str, str]) -> dict[str, Any]:
    runs = indexed_runs()
    dev = sorted(qid for qid, value in split.items() if value == "dev")
    test = sorted(qid for qid, value in split.items() if value == "test")
    baseline = {name: {qid: [item["chunk_id"] for item in rows[qid]["results"]] for qid in split} for name, rows in runs.items()}
    candidates = []
    for k in (10, 30, 60):
        for faiss_weight in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
            rankings = {qid: fuse([(runs["bm25"][qid], 1.0), (runs["faiss"][qid], faiss_weight)], k) for qid in split}
            candidates.append({"k": k, "faiss_weight": faiss_weight, "dev": aggregate(rankings, gold, dev), "rankings": rankings})
    best = max(candidates, key=lambda row: (row["dev"]["ndcg@10"], row["dev"]["mrr@10"], -abs(row["faiss_weight"] - 1), -row["k"]))

    graph_candidates = []
    for k in (30, 60):
        for graph_weight in (0.05, 0.1, 0.25, 0.5):
            for graph_only_factor in (0.0, 0.1, 0.25):
                rankings = {qid: fuse([(runs["bm25"][qid], 1.0), (runs["graph"][qid], graph_weight)], k, graph_only_factor=graph_only_factor) for qid in split}
                graph_candidates.append({"k": k, "graph_weight": graph_weight, "graph_only_factor": graph_only_factor, "dev": aggregate(rankings, gold, dev), "rankings": rankings})
    best_graph = max(graph_candidates, key=lambda row: (row["dev"]["ndcg@10"], row["dev"]["mrr@10"], -row["graph_weight"], -row["graph_only_factor"]))

    union_recall = {}
    for depth in (10, 25):
        per_query = []
        for qid in split:
            union = {item["chunk_id"] for item in runs["bm25"][qid]["results"][:depth]} | {item["chunk_id"] for item in runs["faiss"][qid]["results"][:depth]}
            per_query.append(len(union & gold[qid]) / len(gold[qid]))
        union_recall[f"bm25_faiss_union_top{depth}_candidate_recall"] = round(sum(per_query) / len(per_query), 6)

    return {
        "split_counts": Counter(split.values()),
        "selection_policy": "Hyperparameters selected on 60-query category-stratified dev split; reported confirmation uses untouched 40-query test split.",
        "baseline_test": {name: aggregate(rankings, gold, test) for name, rankings in baseline.items()},
        "weighted_bm25_faiss": {"selected": {k: v for k, v in best.items() if k != "rankings"}, "test": aggregate(best["rankings"], gold, test)},
        "graph_guarded": {"selected": {k: v for k, v in best_graph.items() if k != "rankings"}, "test": aggregate(best_graph["rankings"], gold, test)},
        "prompt_rag_candidate_pool": union_recall,
    }


def rechunked_bm25_experiment(
    qa_rows: list[dict[str, Any]],
    synthesis: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    mapped_gold: dict[str, set[str]],
    split: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from rank_bm25 import BM25Okapi

    tokenized = [normalized(row["text"]).split() for row in chunks]
    chunk_ids = [row["chunk_id"] for row in chunks]
    questions = {row["question_id"]: row["question"] for row in qa_rows}
    dev = sorted(qid for qid, value in split.items() if value == "dev")
    test = sorted(qid for qid, value in split.items() if value == "test")
    candidates = []
    for k1 in (0.9, 1.2, 1.5, 1.8):
        for b in (0.3, 0.5, 0.75):
            model = BM25Okapi(tokenized, k1=k1, b=b)
            rankings = {}
            for query_id, question in questions.items():
                scores = model.get_scores(normalized(question).split())
                order = sorted(range(len(scores)), key=lambda index: (-float(scores[index]), chunk_ids[index]))[:50]
                rankings[query_id] = [chunk_ids[index] for index in order]
            candidates.append({"k1": k1, "b": b, "dev": aggregate(rankings, mapped_gold, dev), "rankings": rankings})
    best = max(candidates, key=lambda row: (row["dev"]["ndcg@10"], row["dev"]["mrr@10"], -abs(row["k1"] - 1.5), -abs(row["b"] - 0.75)))
    model = BM25Okapi(tokenized, k1=best["k1"], b=best["b"])
    synthesis_gold = {
        row["question_id"]: set().union(*(mapped_gold[qid] for qid in row["component_query_ids"]))
        for row in synthesis
    }
    all_questions = {**questions, **{row["question_id"]: row["question"] for row in synthesis}}
    all_rankings = dict(best["rankings"])
    output_rows = []
    for query_id, question in all_questions.items():
        if query_id not in all_rankings:
            scores = model.get_scores(normalized(question).split())
            order = sorted(range(len(scores)), key=lambda index: (-float(scores[index]), chunk_ids[index]))[:50]
            all_rankings[query_id] = [chunk_ids[index] for index in order]
        output_rows.append({
            "query_id": query_id,
            "query_text": question,
            "retriever": "bm25_section_aware_r4",
            "top_k": 50,
            "results": [{"chunk_id": chunk_id, "rank": rank} for rank, chunk_id in enumerate(all_rankings[query_id], 1)],
            "config_snapshot": {"k1": best["k1"], "b": best["b"], "chunk_words": WORD_TARGET, "overlap_words": WORD_OVERLAP},
        })
    synthesis_ids = sorted(synthesis_gold)
    return {
        "selection": {"k1": best["k1"], "b": best["b"], "dev": best["dev"]},
        "test": aggregate(all_rankings, mapped_gold, test),
        "synthesis_candidate_metrics": aggregate(all_rankings, synthesis_gold, synthesis_ids),
        "synthesis_warning": "Automated candidate questions and automatic old-to-new qrel crosswalk; not final human-validated evidence.",
    }, output_rows


def main() -> int:
    documents, old_chunks, qa_rows = load_jsonl(DOCS), load_jsonl(CHUNKS), load_jsonl(QA)
    gold = qrels()
    audit = corpus_audit(documents, old_chunks)
    new_chunks = rechunk_balanced(documents)
    crosswalk_rows, mapped = crosswalk(old_chunks, new_chunks, gold, qa_rows)
    split = split_queries(qa_rows)
    qa_split = [{**row, "split": split[row["question_id"]], "r4_split_seed": SPLIT_SEED} for row in qa_rows]
    synth = synthesis_candidates(qa_rows)
    experiments = retrieval_experiments(qa_rows, gold, split)
    rechunk_bm25, rechunk_bm25_run = rechunked_bm25_experiment(qa_rows, synth, new_chunks, mapped, split)
    experiments["section_aware_bm25"] = rechunk_bm25

    write_json(OUT / "corpus/corpus_quality_audit.json", audit)
    write_jsonl(OUT / "corpus/chunks_section_aware_450w.jsonl", new_chunks)
    write_jsonl(OUT / "corpus/gold_chunk_crosswalk.jsonl", crosswalk_rows)
    write_jsonl(OUT / "benchmark/qa_dev_test.jsonl", qa_split)
    write_json(OUT / "benchmark/query_split.json", split)
    write_jsonl(OUT / "benchmark/synthesis_candidates_20.jsonl", synth)
    write_json(OUT / "retrieval/offline_experiments.json", experiments)
    write_jsonl(OUT / "retrieval/bm25_section_aware_run.jsonl", rechunk_bm25_run)
    mixed_plan = []
    runs = indexed_runs()
    for row in qa_rows:
        qid = row["question_id"]
        ids = []
        for system in ("bm25", "faiss"):
            for item in runs[system][qid]["results"][:25]:
                if item["chunk_id"] not in ids:
                    ids.append(item["chunk_id"])
        mixed_plan.append({"query_id": qid, "candidate_chunk_ids": ids, "candidate_n": len(ids), "source": "stable union of BM25 top25 then FAISS top25; pending Prompt-RAG cost freeze"})
    write_jsonl(OUT / "retrieval/prompt_rag_mixed_top25_plan.jsonl", mixed_plan)

    outputs = sorted(path for path in OUT.rglob("*") if path.is_file() and path.name != "manifest.json")
    manifest = {
        "status": "offline_r4_improvements_complete_pending_new_index_runs_and_human_validation",
        "baseline_preserved": True,
        "inputs": {str(path.relative_to(ROOT)): sha(path) for path in [DOCS, CHUNKS, QA, QRELS, *RUNS.values()]},
        "outputs": {str(path.relative_to(ROOT)): sha(path) for path in outputs},
        "counts": {"documents": len(documents), "old_chunks": len(old_chunks), "new_section_aware_chunks": len(new_chunks), "queries": len(qa_rows), "synthesis_candidates": len(synth), "mapped_qrels": sum(len(ids) for ids in mapped.values())},
        "code": {
            "scripts/build_phase8_r4_improvements.py": sha(ROOT / "scripts/build_phase8_r4_improvements.py"),
            "scripts/run_phase8_r4_faiss.py": sha(ROOT / "scripts/run_phase8_r4_faiss.py"),
        },
        "gates": {"human_validation_complete": False, "new_faiss_index_run": (OUT / "retrieval/faiss_cosine/metrics.json").is_file(), "new_graph_index_run": False, "prompt_rag_api_calls": 0, "final_test_claim_authorized": False},
    }
    write_json(OUT / "manifest.json", manifest)
    print(json.dumps({"counts": manifest["counts"], "audit": {k: audit[k] for k in ("exact_duplicate_document_n", "near_duplicate_pair_n", "noise_candidate_n")}, "experiments": experiments}, indent=2, default=dict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
