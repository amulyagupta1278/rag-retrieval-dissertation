"""Validation for genuine cross-document graph-path benchmark items."""

from __future__ import annotations

from typing import Any

GENERIC_STOP_ENTITIES = {"government", "support", "welfare", "scheme", "programme", "rural", "urban", "india"}
ALLOWED_BRIDGE_TYPES = {
    "ministry", "department", "implementing_agency", "beneficiary_group", "legislation",
    "financial_institution", "delivery_mechanism", "programme_phase", "administrative_relationship",
}


class GraphPathError(ValueError):
    """Raised when graph-path evidence is disconnected or shortcut-prone."""


def _present(entity: str, text: str) -> bool:
    return entity.casefold() in text.casefold()


def validate_graph_path_item(
    item: dict[str, Any], chunk_map: dict[str, dict[str, Any]], corpus_entities: set[str],
) -> None:
    """Fail closed unless item represents auditable two-document traversal."""
    path = item.get("graph_path")
    if not isinstance(path, dict):
        raise GraphPathError("graph_path missing")
    gold_ids = path.get("gold_evidence_ids")
    if not isinstance(gold_ids, list) or len(gold_ids) < 2 or any(x not in chunk_map for x in gold_ids):
        raise GraphPathError("at least two resolving gold evidence IDs required")
    chunks = [chunk_map[x] for x in gold_ids]
    if len({x["document_id"] for x in chunks}) < 2:
        raise GraphPathError("target documents must be distinct")
    bridge = path.get("bridge_entity", "").strip()
    bridge_aliases = path.get("bridge_aliases", [])
    if not bridge or bridge.casefold() in GENERIC_STOP_ENTITIES:
        raise GraphPathError("bridge missing or generic stop-entity")
    if path.get("bridge_type") not in ALLOWED_BRIDGE_TYPES:
        raise GraphPathError("unsupported bridge type")
    forms = [bridge, *bridge_aliases]
    if any(not any(_present(form, chunk["text"]) for form in forms) for chunk in chunks):
        raise GraphPathError("bridge missing from one or more evidence chunks")
    all_text = " ".join(x["text"] for x in chunks)
    for alias in path.get("seed_aliases", []):
        if not (_present(alias, item["question"]) or _present(alias, all_text)):
            raise GraphPathError(f"unsupported seed alias: {alias}")
    targets = path.get("target_entities")
    if not isinstance(targets, list) or len(targets) != 2 or targets[0] == targets[1]:
        raise GraphPathError("exactly two distinct target entities required")
    if all(_present(target, item["question"]) for target in targets):
        raise GraphPathError("question names both target schemes")
    gold_path = path.get("gold_path")
    if not isinstance(gold_path, list) or len(gold_path) != 3:
        raise GraphPathError("gold path must contain target-bridge-target nodes")
    nodes = [x.get("node") for x in gold_path]
    if nodes != [targets[0], bridge, targets[1]]:
        raise GraphPathError("gold path is disconnected")
    required_entities = {path.get("seed_entity"), bridge, *targets}
    if any(not entity or not any(_present(entity, candidate) for candidate in corpus_entities | {all_text}) for entity in required_entities):
        raise GraphPathError("referenced graph entity absent from corpus")
    clauses = item.get("answer_clause_map")
    if not isinstance(clauses, list) or len(clauses) < 2:
        raise GraphPathError("answer clauses are not mapped")
    mapped_ids = {x.get("evidence_id") for x in clauses}
    if mapped_ids != set(gold_ids):
        raise GraphPathError("answer clauses must map across every gold chunk")
    if any(not x.get("clause") or x["clause"] not in item["reference_answer"] for x in clauses):
        raise GraphPathError("mapped answer clause absent from reference answer")
    if path.get("single_chunk_sufficient") is not False:
        raise GraphPathError("single_chunk_sufficient must be false")
    for chunk in chunks:
        mapped_elsewhere = [x for x in clauses if x["evidence_id"] != chunk["chunk_id"]]
        if all(_present(x["clause"], chunk["text"]) for x in mapped_elsewhere):
            raise GraphPathError("one chunk alone contains full answer")
