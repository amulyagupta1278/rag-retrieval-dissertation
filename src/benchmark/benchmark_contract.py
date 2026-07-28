"""Validation contract for reviewed development and holdout benchmarks."""

from __future__ import annotations

import re
from collections import Counter, defaultdict

CATEGORIES = (
    "exact_match", "terminology_heavy", "paraphrase", "entity_relation", "multi_hop",
)
CROSS_SCHEME_CATEGORIES = {"entity_relation", "multi_hop"}
_TOKEN = re.compile(r"[a-z0-9]+")
_ARTIFACT = re.compile(
    r"[{}\[\]]|\b(?:answer_md|chunk_id|doc_id|scheme_id|children|list_item|align_justify)\b",
    re.I,
)
_SCHEMA_LABEL = re.compile(
    r"\b(?:scheme|ministry|department|implementing agency|scheme type|target beneficiaries|level)\s*:",
    re.I,
)
_BOILERPLATE = re.compile(
    r"\b(?:expenditure incurred during the quarter|signature of|annexure|in quarter i/ii|"
    r"cumulative up to the quarter)\b",
    re.I,
)


def normalize(value: str) -> str:
    return " ".join(_TOKEN.findall(str(value).lower()))


def support_ratio(answer: str, evidence: str) -> float:
    """Token containment used only as automatic rejection gate."""
    target = normalize(answer).split()
    source = set(normalize(evidence).split())
    if not target:
        return 0.0
    return sum(token in source for token in target) / len(target)


def answer_supported(answer: str, evidence: str, threshold: float = 0.85) -> bool:
    target, source = normalize(answer), normalize(evidence)
    return bool(target) and (target in source or support_ratio(target, source) >= threshold)


def _acronym_matches(question: str, answer: str) -> bool:
    match = re.search(r"\b([A-Z][A-Z0-9-]{1,9})\b", question)
    if not match:
        return False
    acronym = re.sub(r"[^A-Z0-9]", "", match.group(1))
    initials = "".join(
        word[0].upper() for word in re.findall(r"[A-Za-z]+", answer)
        if word.lower() not in {"a", "an", "and", "for", "of", "the", "to"}
    )
    return acronym == initials


def validate_question(item: dict, chunks: dict[str, dict]) -> list[str]:
    """Return discrete contract violations for one QA record."""
    errors: list[str] = []
    qid = item.get("question_id", "<missing>")
    question = str(item.get("question") or "")
    answer = str(item.get("reference_answer") or "")
    category = item.get("category")
    gold = list(item.get("gold_evidence_ids") or [])
    source_docs = list(item.get("source_doc_ids") or [])
    evidence = [chunks.get(chunk_id) for chunk_id in gold]
    if category not in CATEGORIES:
        errors.append(f"{qid}: unknown category {category}")
    if len(normalize(question).split()) < 4 or len(question) > 240:
        errors.append(f"{qid}: invalid question length")
    if _ARTIFACT.search(question) or _ARTIFACT.search(answer) or _SCHEMA_LABEL.search(answer):
        errors.append(f"{qid}: schema/JSON leakage")
    if category == "exact_match" and question.lower().startswith("what is") and _BOILERPLATE.search(answer):
        errors.append(f"{qid}: definition answer is administrative boilerplate")
    if not gold or any(chunk is None for chunk in evidence):
        errors.append(f"{qid}: unresolved gold evidence")
        return errors
    actual_docs = [chunk.get("doc_id") for chunk in evidence if chunk]
    if source_docs != actual_docs:
        errors.append(f"{qid}: source document IDs do not align with gold order")
    if category in CROSS_SCHEME_CATEGORIES:
        schemes = [normalize(chunk.get("scheme_name", "")) for chunk in evidence]
        if len(gold) != 2 or len(set(actual_docs)) != 2 or len(set(schemes)) != 2 or not all(schemes):
            errors.append(f"{qid}: cross-scheme cardinality/document/scheme failure")
        bridge = normalize(item.get("extra_meta", {}).get("bridge_entity", ""))
        if not bridge or any(bridge not in normalize(chunk.get("text", "")) for chunk in evidence):
            errors.append(f"{qid}: bridge absent from one or both gold chunks")
        clauses = [part.strip() for part in answer.split(" Additionally, ") if part.strip()]
        if len(clauses) != 2 or any(
            not answer_supported(clause, chunk.get("text", ""))
            for clause, chunk in zip(clauses, evidence)
        ):
            errors.append(f"{qid}: two answer clauses do not map to assigned chunks")
    else:
        if len(gold) != 1:
            errors.append(f"{qid}: single-hop category must have one gold chunk")
        elif not answer_supported(answer, evidence[0].get("text", "")):
            errors.append(f"{qid}: answer unsupported by gold chunk")
    if category == "terminology_heavy" and not _acronym_matches(question, answer):
        errors.append(f"{qid}: acronym and expansion do not match")
    return errors


def validate_benchmark(
    items: list[dict], chunks: list[dict], *, expected_per_category: int = 20,
    max_gold_reuse: int = 2, require_reviewed: bool = False,
    expected_version: str | None = None,
) -> list[str]:
    """Validate balance, diversity, evidence, review state, and fold assignment."""
    errors: list[str] = []
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}
    counts = Counter(item.get("category") for item in items)
    expected = Counter({category: expected_per_category for category in CATEGORIES})
    if len(items) != expected_per_category * len(CATEGORIES) or counts != expected:
        errors.append(f"benchmark balance mismatch: rows={len(items)} categories={dict(counts)}")
    question_ids = [item.get("question_id") for item in items]
    if len(question_ids) != len(set(question_ids)):
        errors.append("duplicate question IDs")
    normalized_questions = [normalize(item.get("question", "")) for item in items]
    if len(normalized_questions) != len(set(normalized_questions)):
        errors.append("duplicate normalized question intent")
    gold_reuse = Counter(
        chunk_id for item in items for chunk_id in item.get("gold_evidence_ids", [])
    )
    overused = {chunk_id: count for chunk_id, count in gold_reuse.items() if count > max_gold_reuse}
    if overused:
        errors.append(f"gold chunk reuse exceeds {max_gold_reuse}: {overused}")
    pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    folds: dict[str, Counter] = defaultdict(Counter)
    for item in items:
        errors.extend(validate_question(item, chunk_map))
        category = item.get("category")
        fold_id = item.get("fold_id")
        if fold_id not in range(5):
            errors.append(f"{item.get('question_id')}: missing/invalid fold_id")
        else:
            folds[category][fold_id] += 1
        if expected_version and item.get("benchmark_version") != expected_version:
            errors.append(f"{item.get('question_id')}: benchmark version mismatch")
        if require_reviewed and (
            item.get("review_status") != "complete" or int(item.get("review_revision", 0)) < 1
        ):
            errors.append(f"{item.get('question_id')}: review incomplete")
        if category in CROSS_SCHEME_CATEGORIES:
            names = [normalize(value) for value in item.get("extra_meta", {}).get("scheme_names", [])]
            if len(names) == 2:
                pair = tuple(sorted(names))
                if pair in pairs[category]:
                    errors.append(f"{item.get('question_id')}: duplicate scheme pair in {category}")
                pairs[category].add(pair)
    for category in CATEGORIES:
        if folds[category] != Counter({fold: expected_per_category // 5 for fold in range(5)}):
            errors.append(f"{category}: folds not balanced: {dict(folds[category])}")
    return errors


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    if not pairs:
        return None
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_true = sum(left for left, _ in pairs) / len(pairs)
    right_true = sum(right for _, right in pairs) / len(pairs)
    expected = left_true * right_true + (1 - left_true) * (1 - right_true)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0
