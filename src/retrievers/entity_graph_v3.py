"""Corpus-only entity graph primitives for the corrected Phase 3 candidate.

This module deliberately has no benchmark, qrels, or ranking inputs.  Index
construction consumes corpus chunks, document/source metadata, and a frozen
configuration only.  Query matching and traversal are separate, pure steps.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, Sequence


REGISTRY_VERSION = "entity-registry-v3-candidate"
REGISTRY_VERSION_3_1 = "entity-registry-v3.1"
REGISTRY_VERSION_3_2 = "entity-registry-v3.2"
ALLOWED_ENTITY_TYPES = {
    "scheme",
    "scheme_alias",
    "ministry",
    "department",
    "implementing_agency",
    "beneficiary_group",
    "law_or_policy",
    "delivery_institution",
    "controlled_acronym",
}
TYPE_PRIORITY = {
    "scheme": 0,
    "ministry": 1,
    "department": 2,
    "implementing_agency": 3,
    "law_or_policy": 4,
    "delivery_institution": 5,
    "beneficiary_group": 6,
    "controlled_acronym": 7,
    "scheme_alias": 8,
}
UPPER_TOKEN = re.compile(r"(?<![\w-])[A-Z][A-Z0-9-]{1,14}(?![\w-])")
PAREN_PAIR = re.compile(
    r"(?P<long>[A-Z][A-Za-z0-9&’'/-]*(?:\s+(?:[A-Z][A-Za-z0-9&’'/-]*|of|and|the|for)){1,10})"
    r"\s*\((?P<short>[A-Z][A-Za-z0-9-]{1,14})\)"
)
LAW_POLICY = re.compile(
    r"\b(?P<label>[A-Z][A-Za-z0-9’'-]*(?:\s+(?:[A-Z][A-Za-z0-9’'-]*|of|and|the|for)){1,8}"
    r"\s+(?:Act|Policy)(?:\s*,?\s*\d{4})?)\b"
)
ROMAN_NUMERAL = re.compile(r"(?i)^[ivxlcdm]+$")


def normalize_text(value: str) -> str:
    """NFKC/casefold text, replace punctuation with spaces, and collapse."""
    folded = unicodedata.normalize("NFKC", value).casefold()
    spaced = "".join(character if character.isalnum() else " " for character in folded)
    return " ".join(spaced.split())


def normalized_tokens(value: str) -> tuple[str, ...]:
    """Return the stable exact-match token sequence for *value*."""
    normalized = normalize_text(value)
    return tuple(normalized.split()) if normalized else ()


def organization_key(value: str) -> str:
    """Normalize organization identity without stemming or fuzzy rewriting."""
    normalized = unicodedata.normalize("NFKC", value).replace("&", " and ").casefold()
    spaced = "".join(character if character.isalnum() else " " for character in normalized)
    return " ".join(spaced.split())


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _excerpt(text: str, needle: str, width: int = 220) -> str:
    normalized = " ".join(text.split())
    offset = normalized.casefold().find(needle.casefold())
    if offset < 0:
        return normalized[:width]
    start = max(0, offset - width // 3)
    return normalized[start : start + width]


def _acronym_matches(long_form: str, short_form: str) -> bool:
    short = "".join(character for character in short_form.casefold() if character.isalnum())
    words = normalized_tokens(long_form)
    if len(words) < 2 or len(short) < 2:
        return False
    initials = "".join(word[0] for word in words)
    variants = {initials, initials.rstrip("s"), initials + "s"}
    if short in variants or short.rstrip("s") in variants:
        return True
    iterator = iter(initials)
    return all(any(character == candidate for candidate in iterator) for character in short.rstrip("s"))


def _candidate(
    *,
    label: str,
    entity_type: str,
    document_id: str,
    source_field: str,
    extraction_rule: str,
    evidence: str,
    aliases: Iterable[str] = (),
    trusted_metadata: bool = False,
) -> dict[str, Any]:
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise ValueError(f"unsupported entity type: {entity_type}")
    return {
        "label": " ".join(label.split()),
        "entity_type": entity_type,
        "document_id": document_id,
        "source_field": source_field,
        "extraction_rule": extraction_rule,
        "evidence": " ".join(evidence.split()),
        "aliases": tuple(" ".join(alias.split()) for alias in aliases if alias and alias.strip()),
        "trusted_metadata": trusted_metadata,
    }


def extract_candidates(
    documents: Sequence[Mapping[str, Any]],
    source_metadata: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Extract auditable typed candidates from corpus/source metadata only."""
    candidates: list[dict[str, Any]] = []
    source_by_id = {str(row["source_id"]): row for row in source_metadata}
    for document in sorted(documents, key=lambda row: str(row["document_id"])):
        document_id = str(document["document_id"])
        text = str(document["text"])
        title = str(document["title"])
        source = source_by_id.get(str(document["source_id"]), {})
        short_title = str(source.get("scheme_short_title") or "").strip()
        title_aliases = [short_title] if short_title else []
        parenthetical_title = re.fullmatch(r"(?P<long>.+?)\s*\((?P<short>[A-Z][A-Za-z0-9 -]{1,20})\)", title)
        canonical_title = parenthetical_title.group("long").strip() if parenthetical_title else title
        if parenthetical_title:
            title_aliases.extend((parenthetical_title.group("short"), title))
        candidates.append(_candidate(
            label=canonical_title, entity_type="scheme", document_id=document_id,
            source_field="document.title", extraction_rule="structured_scheme_title",
            evidence=title, aliases=title_aliases, trusted_metadata=True,
        ))
        for field, entity_type in (("ministry", "ministry"), ("department", "department")):
            value = str(document.get(field) or "").strip()
            if value:
                candidates.append(_candidate(
                    label=value, entity_type=entity_type, document_id=document_id,
                    source_field=f"document.{field}", extraction_rule=f"structured_{field}",
                    evidence=value, trusted_metadata=True,
                ))
        agency = str(source.get("implementing_agency") or "").strip()
        if agency:
            paired_agency = PAREN_PAIR.fullmatch(agency)
            candidates.append(_candidate(
                label=paired_agency.group("long") if paired_agency else agency,
                entity_type="implementing_agency", document_id=document_id,
                source_field="source.basicDetails.implementingAgency",
                extraction_rule="structured_implementing_agency", evidence=agency,
                aliases=(paired_agency.group("short"), agency) if paired_agency else (),
                trusted_metadata=True,
            ))
        for group in source.get("target_beneficiaries") or ():
            if str(group).strip():
                candidates.append(_candidate(
                    label=str(group), entity_type="beneficiary_group", document_id=document_id,
                    source_field="source.basicDetails.targetBeneficiaries.label",
                    extraction_rule="structured_beneficiary_group", evidence=str(group),
                    trusted_metadata=True,
                ))

        for match in PAREN_PAIR.finditer(text):
            long_form, short_form = match.group("long", "short")
            if _acronym_matches(long_form, short_form):
                candidates.append(_candidate(
                    label=long_form, entity_type="controlled_acronym", document_id=document_id,
                    source_field="document.text", extraction_rule="paired_long_form_acronym",
                    evidence=_excerpt(text, match.group(0)), aliases=(short_form,),
                ))
        for match in LAW_POLICY.finditer(text):
            label = match.group("label")
            candidates.append(_candidate(
                label=label, entity_type="law_or_policy", document_id=document_id,
                source_field="document.text", extraction_rule="explicit_law_or_policy_phrase",
                evidence=_excerpt(text, label),
            ))
    return candidates


def _exact_contains(text: str, phrase: str) -> bool:
    haystack, needle = normalized_tokens(text), normalized_tokens(phrase)
    if not needle or len(needle) > len(haystack):
        return False
    return any(haystack[index : index + len(needle)] == needle for index in range(len(haystack) - len(needle) + 1))


def build_entity_registry(
    *,
    chunks: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
    source_metadata: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a deterministic accepted/rejected corpus-only entity registry."""
    banned = {normalize_text(value) for value in config["banned_entity_labels"]}
    generic = {normalize_text(value) for value in config["generic_entity_labels"]}
    stopwords = {normalize_text(value) for value in config["stopwords"]}
    documents_by_id = {str(row["document_id"]): row for row in documents}
    candidates = extract_candidates(documents, source_metadata)

    paired_or_official_aliases: set[str] = set()
    for candidate in candidates:
        if candidate["extraction_rule"] in {"paired_long_form_acronym", "structured_scheme_title"}:
            paired_or_official_aliases.update(normalize_text(alias) for alias in candidate["aliases"])
    for document in documents:
        text = str(document["text"])
        for match in UPPER_TOKEN.finditer(text):
            label = match.group(0)
            if normalize_text(label) not in paired_or_official_aliases:
                candidates.append(_candidate(
                    label=label, entity_type="controlled_acronym", document_id=str(document["document_id"]),
                    source_field="document.text", extraction_rule="uppercase_token_audit",
                    evidence=_excerpt(text, label),
                ))

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        normalized = normalize_text(candidate["label"])
        if normalized:
            grouped[(candidate["entity_type"], normalized)].append(candidate)

    provisional: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for (entity_type, normalized), rows in sorted(grouped.items()):
        labels = sorted({row["label"] for row in rows}, key=lambda value: (len(value), value.casefold(), value))
        label = labels[0]
        tokens = normalized.split()
        raw_aliases = sorted({alias for row in rows for alias in row["aliases"] if normalize_text(alias) != normalized}, key=lambda value: (normalize_text(value), value))
        banned_aliases = sorted(alias for alias in raw_aliases if normalize_text(alias) in banned)
        reason = ""
        if normalized in banned:
            reason = "banned_entity"
        elif entity_type == "controlled_acronym" and banned_aliases:
            reason = "banned_alias"
        elif normalized in generic:
            reason = "generic_entity"
        elif len(tokens) == 1 and ROMAN_NUMERAL.fullmatch(normalized):
            reason = "roman_numeral"
        elif len(normalized) == 1:
            reason = "single_character"
        elif rows[0]["extraction_rule"] == "uppercase_token_audit":
            reason = "unpaired_uppercase_token"
        elif (tokens[0] in stopwords or tokens[-1] in stopwords) and not any(row["trusted_metadata"] for row in rows):
            reason = "stopword_boundary"

        aliases = [alias for alias in raw_aliases if normalize_text(alias) not in banned]
        source_document_ids = sorted({row["document_id"] for row in rows})
        evidence = sorted(
            {
                (row["document_id"], row["source_field"], row["extraction_rule"], row["evidence"])
                for row in rows
            }
        )
        record = {
            "entity_id": _stable_id("entity", entity_type, normalized),
            "canonical_label": label,
            "normalized_label": normalized,
            "entity_type": entity_type,
            "aliases": aliases,
            "rejected_aliases": [{"alias": alias, "reason": "banned_alias"} for alias in banned_aliases],
            "source_document_ids": source_document_ids,
            "source_field": sorted({row["source_field"] for row in rows}),
            "extraction_rule": sorted({row["extraction_rule"] for row in rows}),
            "corpus_evidence": [
                {"document_id": item[0], "source_field": item[1], "extraction_rule": item[2], "excerpt": item[3]}
                for item in evidence
            ],
            "document_frequency": 0,
            "status": "rejected" if reason else "accepted",
            "rejection_reason": reason,
            "registry_version": REGISTRY_VERSION,
            "trusted_metadata_document_ids": sorted({row["document_id"] for row in rows if row["trusted_metadata"]}),
        }
        (rejected if reason else provisional).append(record)

    # A normalized label is one canonical node.  Preserve lower-priority candidates
    # as rejected audit rows rather than silently merging incompatible types.
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in provisional:
        by_label[record["normalized_label"]].append(record)
    accepted: list[dict[str, Any]] = []
    normalization_collisions: list[dict[str, Any]] = []
    for normalized, records in sorted(by_label.items()):
        records.sort(key=lambda row: (TYPE_PRIORITY[row["entity_type"]], row["entity_id"]))
        winner, losers = records[0], records[1:]
        accepted.append(winner)
        if losers:
            normalization_collisions.append({
                "normalized_label": normalized,
                "accepted_entity_id": winner["entity_id"],
                "rejected_entity_ids": [row["entity_id"] for row in losers],
            })
        for loser in losers:
            loser["status"] = "rejected"
            loser["rejection_reason"] = f"normalization_collision_with:{winner['entity_id']}"
            rejected.append(loser)

    # Ambiguous aliases cannot seed multiple canonical entities.
    alias_targets: dict[str, set[str]] = defaultdict(set)
    for record in accepted:
        for alias in record["aliases"]:
            alias_targets[normalize_text(alias)].add(record["entity_id"])
    ambiguous_aliases = {alias: sorted(targets) for alias, targets in alias_targets.items() if len(targets) > 1}
    alias_collision_resolutions: dict[str, dict[str, Any]] = {}
    if ambiguous_aliases:
        lookup = {record["entity_id"]: record for record in accepted}
        for alias, target_ids in ambiguous_aliases.items():
            best_priority = min(TYPE_PRIORITY[lookup[target_id]["entity_type"]] for target_id in target_ids)
            winners = [target_id for target_id in target_ids if TYPE_PRIORITY[lookup[target_id]["entity_type"]] == best_priority]
            kept = winners[0] if len(winners) == 1 else None
            alias_collision_resolutions[alias] = {
                "candidate_entity_ids": target_ids,
                "kept_entity_id": kept,
                "resolution": "unique_higher_priority_entity_kept" if kept else "equal_priority_ambiguity_removed_from_all",
            }
            for target_id in target_ids:
                if target_id == kept:
                    continue
                lookup[target_id]["aliases"] = [
                    value for value in lookup[target_id]["aliases"] if normalize_text(value) != alias
                ]

    for record in accepted:
        labels = [record["canonical_label"], *record["aliases"]]
        exact_documents = {
            document_id
            for document_id, document in documents_by_id.items()
            if any(_exact_contains(str(document["text"]), label) for label in labels)
        }
        linked = set(record["trusted_metadata_document_ids"])
        record["document_frequency"] = len(exact_documents | linked)
        if record["document_frequency"] == 0:
            record["status"] = "rejected"
            record["rejection_reason"] = "no_corpus_occurrence"
            rejected.append(record)
    accepted = [record for record in accepted if record["status"] == "accepted"]

    accepted_names = {
        normalize_text(name)
        for record in accepted
        for name in [record["canonical_label"], *record["aliases"]]
    }
    surviving_banned = sorted(accepted_names & banned)
    if surviving_banned:
        raise ValueError(f"banned entities survived registry filtering: {surviving_banned}")

    registry = sorted([*accepted, *rejected], key=lambda row: row["entity_id"])
    if len({row["entity_id"] for row in registry}) != len(registry):
        # Multiple rejection causes for the same typed normalized candidate are
        # merged above; duplicate IDs indicate a programming/configuration error.
        raise ValueError("duplicate entity IDs in registry")
    accepted_by_type = Counter(row["entity_type"] for row in accepted)
    rejected_by_reason = Counter(row["rejection_reason"] for row in rejected)
    df_distribution = Counter(str(row["document_frequency"]) for row in accepted)
    samples: dict[str, dict[str, Any]] = {}
    for row in registry:
        for rule in row["extraction_rule"]:
            sample = {**row["corpus_evidence"][0], "entity_status": row["status"]}
            samples.setdefault(rule, sample)
    audit = {
        "registry_version": REGISTRY_VERSION,
        "accepted_entity_count": len(accepted),
        "accepted_by_type": {entity_type: accepted_by_type.get(entity_type, 0) for entity_type in sorted(ALLOWED_ENTITY_TYPES)},
        "rejected_entity_count": len(rejected),
        "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
        "document_frequency_distribution": dict(sorted(df_distribution.items(), key=lambda item: int(item[0]))),
        "top_50_highest_df": [
            {"entity_id": row["entity_id"], "canonical_label": row["canonical_label"], "entity_type": row["entity_type"], "document_frequency": row["document_frequency"]}
            for row in sorted(accepted, key=lambda row: (-row["document_frequency"], row["entity_id"]))[:50]
        ],
        "entities_shorter_than_four_characters": [
            {"entity_id": row["entity_id"], "canonical_label": row["canonical_label"], "aliases": row["aliases"]}
            for row in accepted if len(row["normalized_label"].replace(" ", "")) < 4
        ],
        "aliases_mapping_to_multiple_canonical_entities": ambiguous_aliases,
        "alias_collision_resolutions": alias_collision_resolutions,
        "normalization_collisions": normalization_collisions,
        "sample_evidence_by_extraction_rule": dict(sorted(samples.items())),
        "banned_token_audit": {
            "configured": sorted(banned),
            "surviving_accepted": surviving_banned,
            "passed": not surviving_banned,
        },
    }
    return registry, audit


def canonicalize_organization_entities(
    *,
    registry: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
    equivalences: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge only exact-normalized and explicitly approved organization identities."""
    organization_types = {"ministry", "department", "implementing_agency"}
    type_priority = {"ministry": 0, "department": 1, "implementing_agency": 2, "controlled_acronym": 3}
    accepted = [dict(row) for row in registry if row["status"] == "accepted"]
    rejected = [dict(row) for row in registry if row["status"] == "rejected"]
    documents_by_id = {str(row["document_id"]): row for row in documents}

    groups: list[dict[str, Any]] = []
    variant_to_group: dict[str, int] = {}
    for index, raw_group in enumerate(equivalences):
        canonical = str(raw_group["canonical_label"])
        variants = sorted({canonical, *map(str, raw_group["variants"])}, key=lambda value: (organization_key(value), value))
        keys = {organization_key(value) for value in variants}
        if not keys or any(key in variant_to_group for key in keys):
            raise ValueError("organization equivalence groups overlap or contain empty labels")
        group = {
            "canonical_label": canonical,
            "variants": variants,
            "keys": keys,
            "reason": str(raw_group["reason"]),
        }
        groups.append(group)
        for key in keys:
            variant_to_group[key] = index

    # Include semantic organization records plus controlled acronym records only
    # when their label is an explicitly approved organization variant.
    candidates = [
        row
        for row in accepted
        if row["entity_type"] in organization_types
        or organization_key(str(row["canonical_label"])) in variant_to_group
    ]
    parent = {str(row["entity_id"]): str(row["entity_id"]) for row in candidates}

    def find(entity_id: str) -> str:
        while parent[entity_id] != entity_id:
            parent[entity_id] = parent[parent[entity_id]]
            entity_id = parent[entity_id]
        return entity_id

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        winner, loser = sorted((left_root, right_root))
        parent[loser] = winner

    by_exact_key: dict[str, list[str]] = defaultdict(list)
    by_explicit_group: dict[int, list[str]] = defaultdict(list)
    for row in candidates:
        entity_id = str(row["entity_id"])
        keys = {organization_key(str(row["canonical_label"])), *(organization_key(str(alias)) for alias in row["aliases"])}
        for key in keys:
            by_exact_key[key].append(entity_id)
            if key in variant_to_group:
                by_explicit_group[variant_to_group[key]].append(entity_id)
    for entity_ids in [*by_exact_key.values(), *by_explicit_group.values()]:
        for entity_id in entity_ids[1:]:
            union(entity_ids[0], entity_id)

    components: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        components[find(str(row["entity_id"]))].append(row)
    merged_member_ids = {str(row["entity_id"]) for rows in components.values() if len(rows) > 1 for row in rows}
    output_accepted = [row for row in accepted if str(row["entity_id"]) not in merged_member_ids]
    merge_map: list[dict[str, Any]] = []

    for rows in sorted((rows for rows in components.values() if len(rows) > 1), key=lambda values: sorted(str(row["entity_id"]) for row in values)):
        rows.sort(key=lambda row: (type_priority.get(str(row["entity_type"]), 99), str(row["entity_id"])))
        semantic_rows = [row for row in rows if row["entity_type"] in organization_types]
        if not semantic_rows:
            raise ValueError("organization merge lacks semantic organization type")
        strongest_type = str(semantic_rows[0]["entity_type"])
        member_keys = {
            organization_key(str(name))
            for row in rows
            for name in [row["canonical_label"], *row["aliases"]]
        }
        explicit_group_ids = sorted({variant_to_group[key] for key in member_keys if key in variant_to_group})
        if len(explicit_group_ids) > 1:
            raise ValueError("organization component crosses approved equivalence groups")
        explicit_group = groups[explicit_group_ids[0]] if explicit_group_ids else None
        canonical_label = explicit_group["canonical_label"] if explicit_group else str(semantic_rows[0]["canonical_label"])
        all_names = {
            str(name)
            for row in rows
            for name in [row["canonical_label"], *row["aliases"]]
        }
        if explicit_group:
            all_names.update(explicit_group["variants"])
        aliases = sorted(
            {name for name in all_names if normalize_text(name) != normalize_text(canonical_label)},
            key=lambda value: (organization_key(value), value),
        )
        evidence_keys = {
            (item["document_id"], item["source_field"], item["extraction_rule"], item["excerpt"])
            for row in rows
            for item in row["corpus_evidence"]
        }
        source_document_ids = sorted({doc_id for row in rows for doc_id in row["source_document_ids"]})
        trusted_document_ids = sorted({doc_id for row in rows for doc_id in row["trusted_metadata_document_ids"]})
        labels = [canonical_label, *aliases]
        exact_documents = {
            document_id
            for document_id, document in documents_by_id.items()
            if any(_exact_contains(str(document["text"]), label) for label in labels)
        }
        merged_id = _stable_id("entity-v31", strongest_type, organization_key(canonical_label))
        merged = {
            "entity_id": merged_id,
            "canonical_label": canonical_label,
            "normalized_label": normalize_text(canonical_label),
            "entity_type": strongest_type,
            "aliases": aliases,
            "rejected_aliases": sorted(
                [item for row in rows for item in row.get("rejected_aliases", [])],
                key=lambda item: (item["alias"], item["reason"]),
            ),
            "source_document_ids": source_document_ids,
            "source_field": sorted({field for row in rows for field in row["source_field"]}),
            "extraction_rule": sorted({rule for row in rows for rule in row["extraction_rule"]} | {"organization_canonicalization_v3_1"}),
            "corpus_evidence": [
                {"document_id": item[0], "source_field": item[1], "extraction_rule": item[2], "excerpt": item[3]}
                for item in sorted(evidence_keys)
            ],
            "document_frequency": len(exact_documents | set(trusted_document_ids)),
            "status": "accepted",
            "rejection_reason": "",
            "registry_version": REGISTRY_VERSION_3_1,
            "trusted_metadata_document_ids": trusted_document_ids,
        }
        output_accepted.append(merged)
        reason = explicit_group["reason"] if explicit_group else "exact_organization_normalization_equivalence"
        for row in rows:
            merge_map.append({
                "old_entity_id": row["entity_id"],
                "old_canonical_label": row["canonical_label"],
                "old_entity_type": row["entity_type"],
                "merged_entity_id": merged_id,
                "merged_canonical_label": canonical_label,
                "merged_entity_type": strongest_type,
                "reason": reason,
                "evidence_document_ids": sorted(row["source_document_ids"]),
            })

    for row in output_accepted:
        row["registry_version"] = REGISTRY_VERSION_3_1
    for row in rejected:
        row["registry_version"] = REGISTRY_VERSION_3_1

    post_org = [row for row in output_accepted if row["entity_type"] in organization_types]
    exact_duplicates: dict[str, list[str]] = defaultdict(list)
    for row in post_org:
        exact_duplicates[organization_key(str(row["canonical_label"]))].append(str(row["entity_id"]))
    surviving_exact_duplicates = {key: values for key, values in exact_duplicates.items() if len(values) > 1}
    if surviving_exact_duplicates:
        raise ValueError(f"organization duplicates survived canonicalization: {surviving_exact_duplicates}")

    near_duplicates: list[dict[str, Any]] = []
    for left_index, left in enumerate(sorted(post_org, key=lambda row: str(row["entity_id"]))):
        for right in sorted(post_org, key=lambda row: str(row["entity_id"]))[left_index + 1 :]:
            left_key, right_key = organization_key(str(left["canonical_label"])), organization_key(str(right["canonical_label"]))
            ratio = SequenceMatcher(None, left_key, right_key).ratio()
            if ratio >= 0.72:
                near_duplicates.append({
                    "left_entity_id": left["entity_id"],
                    "left_label": left["canonical_label"],
                    "right_entity_id": right["entity_id"],
                    "right_label": right["canonical_label"],
                    "similarity": ratio,
                    "action": "retained_distinct_not_approved_for_merge",
                })
    audit = {
        "registry_version": REGISTRY_VERSION_3_1,
        "normalization": "NFKC; ampersand to and; casefold; punctuation/apostrophes/dashes to spaces; collapse whitespace",
        "automatic_merge_scope": "exact organization normalization plus explicitly approved equivalences only; no stemming or fuzzy auto-merge",
        "accepted_organization_audit": [
            {
                "entity_id": row["entity_id"],
                "canonical_label": row["canonical_label"],
                "organization_key": organization_key(str(row["canonical_label"])),
                "entity_type": row["entity_type"],
                "source_document_ids": row["source_document_ids"],
            }
            for row in sorted(post_org, key=lambda row: str(row["entity_id"]))
        ],
        "approved_equivalences": [
            {"canonical_label": group["canonical_label"], "variants": group["variants"], "reason": group["reason"]}
            for group in groups
        ],
        "merge_map": sorted(merge_map, key=lambda row: (row["merged_entity_id"], row["old_entity_id"])),
        "merged_old_entity_count": len(merge_map),
        "new_merged_entity_count": len({row["merged_entity_id"] for row in merge_map}),
        "near_duplicate_candidates_retained_distinct": near_duplicates,
        "surviving_exact_normalization_duplicates": surviving_exact_duplicates,
        "accepted_entity_count": len(output_accepted),
        "rejected_entity_count": len(rejected),
    }
    output = sorted([*output_accepted, *rejected], key=lambda row: str(row["entity_id"]))
    if len(output) != len({str(row["entity_id"]) for row in output}):
        raise ValueError("duplicate entity IDs after organization canonicalization")
    return output, audit


def apply_corpus_backed_scheme_aliases(
    *,
    registry: Sequence[Mapping[str, Any]],
    chunks: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
    additions: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply frozen corpus-proven scheme aliases without changing other entities."""
    output = [dict(row) for row in registry]
    accepted = {str(row["entity_id"]): row for row in output if row["status"] == "accepted"}
    scheme_by_label = {
        normalize_text(str(row["canonical_label"])): row
        for row in accepted.values()
        if row["entity_type"] == "scheme"
    }
    documents_by_id = {str(row["document_id"]): row for row in documents}
    if len(additions) != len({normalize_text(str(row["alias"])) for row in additions}):
        raise ValueError("approved alias additions collide after normalization")

    existing_owners: dict[str, set[str]] = defaultdict(set)
    for entity in accepted.values():
        for name in [entity["canonical_label"], *entity["aliases"]]:
            existing_owners[normalize_text(str(name))].add(str(entity["entity_id"]))
    applied: list[dict[str, Any]] = []
    for addition in sorted(additions, key=lambda row: (normalize_text(str(row["canonical_label"])), normalize_text(str(row["alias"])))):
        canonical_label = str(addition["canonical_label"])
        alias = str(addition["alias"])
        normalized_alias = normalize_text(alias)
        scheme = scheme_by_label.get(normalize_text(canonical_label))
        if not scheme:
            raise ValueError(f"approved alias canonical scheme absent: {canonical_label}")
        scheme_id = str(scheme["entity_id"])
        owners = existing_owners.get(normalized_alias, set())
        if owners and owners != {scheme_id}:
            raise ValueError(f"approved alias maps to multiple canonical entities: {alias}: {sorted(owners | {scheme_id})}")
        if normalized_alias in {normalize_text(str(name)) for name in [scheme["canonical_label"], *scheme["aliases"]]}:
            raise ValueError(f"approved alias already exists: {canonical_label} -> {alias}")

        pattern = re.compile(re.escape(alias), re.IGNORECASE)
        evidence: list[dict[str, Any]] = []
        canonical_documents = set(map(str, scheme["source_document_ids"]))
        canonical_occurrence = False
        for chunk in sorted(chunks, key=lambda row: str(row["chunk_id"])):
            text = str(chunk["text"])
            for match in pattern.finditer(text):
                document_id = str(chunk["document_id"])
                canonical_occurrence |= document_id in canonical_documents
                prefix_tokens = len(re.findall(r"\S+", text[: match.start()]))
                matched_tokens = len(re.findall(r"\S+", text[match.start() : match.end()]))
                evidence.append({
                    "document_id": document_id,
                    "source_id": str(chunk["source_id"]),
                    "chunk_id": str(chunk["chunk_id"]),
                    "matched_text": text[match.start() : match.end()],
                    "character_span": [match.start(), match.end()],
                    "token_span": [prefix_tokens, prefix_tokens + matched_tokens],
                    "excerpt": " ".join(text[max(0, match.start() - 100) : min(len(text), match.end() + 140)].split()),
                    "source_sha256": str(chunk["source_sha256"]),
                    "chunk_text_sha256": str(chunk["text_sha256"]),
                })
        if not evidence or not canonical_occurrence:
            raise ValueError(f"approved alias lacks exact canonical-document corpus evidence: {canonical_label} -> {alias}")
        scheme["aliases"] = sorted({*map(str, scheme["aliases"]), alias}, key=lambda value: (normalize_text(value), value))
        scheme.setdefault("alias_provenance", []).append({
            "alias": alias,
            "normalized_alias": normalized_alias,
            "extraction_rule": str(addition["extraction_rule"]),
            "evidence_document_ids": sorted({row["document_id"] for row in evidence}),
            "evidence_chunk_ids": sorted({row["chunk_id"] for row in evidence}),
            "corpus_evidence": evidence,
            "evidence_source": "frozen chunks only; no benchmark inputs",
        })
        scheme["alias_provenance"] = sorted(scheme["alias_provenance"], key=lambda row: normalize_text(str(row["alias"])))
        scheme["extraction_rule"] = sorted({*map(str, scheme["extraction_rule"]), f"scheme_alias:{addition['extraction_rule']}"})
        all_labels = [str(scheme["canonical_label"]), *map(str, scheme["aliases"])]
        exact_documents = {
            document_id
            for document_id, document in documents_by_id.items()
            if any(_exact_contains(str(document["text"]), label) for label in all_labels)
        }
        scheme["document_frequency"] = len(exact_documents | set(map(str, scheme["trusted_metadata_document_ids"])))
        existing_owners[normalized_alias].add(scheme_id)
        applied.append({
            "canonical_entity_id": scheme_id,
            "canonical_label": canonical_label,
            "alias": alias,
            "normalized_alias": normalized_alias,
            "extraction_rule": str(addition["extraction_rule"]),
            "evidence_document_ids": sorted({row["document_id"] for row in evidence}),
            "evidence_chunk_ids": sorted({row["chunk_id"] for row in evidence}),
            "evidence_occurrence_count": len(evidence),
        })

    for row in output:
        row["registry_version"] = REGISTRY_VERSION_3_2
    final_owners: dict[str, set[str]] = defaultdict(set)
    for entity in output:
        if entity["status"] != "accepted":
            continue
        for name in [entity["canonical_label"], *entity["aliases"]]:
            final_owners[normalize_text(str(name))].add(str(entity["entity_id"]))
    ambiguous_applied = {
        normalized: sorted(final_owners[normalized])
        for normalized in (row["normalized_alias"] for row in applied)
        if len(final_owners[normalized]) != 1
    }
    if ambiguous_applied:
        raise ValueError(f"applied aliases remain ambiguous: {ambiguous_applied}")
    audit = {
        "registry_version": REGISTRY_VERSION_3_2,
        "applied_alias_count": len(applied),
        "applied_aliases": applied,
        "ambiguous_applied_aliases": ambiguous_applied,
        "entity_count_unchanged": len(output) == len(registry),
        "entity_ids_unchanged": sorted(str(row["entity_id"]) for row in output) == sorted(str(row["entity_id"]) for row in registry),
        "forbidden_benchmark_inputs": [],
    }
    return sorted(output, key=lambda row: str(row["entity_id"])), audit


@dataclass(frozen=True)
class AliasMatch:
    """One longest-first exact alias match in normalized query coordinates."""

    entity_id: str
    canonical_label: str
    entity_type: str
    matched_alias: str
    token_start: int
    token_end: int
    matched_query_span: str
    document_frequency: int


class EntityMatcher:
    """Deterministic exact-token, longest-match-first alias resolver."""

    def __init__(self, registry: Sequence[Mapping[str, Any]]) -> None:
        aliases: list[tuple[tuple[str, ...], str, Mapping[str, Any]]] = []
        for record in registry:
            if record["status"] != "accepted":
                continue
            for alias in [record["canonical_label"], *record["aliases"]]:
                tokens = normalized_tokens(str(alias))
                if tokens:
                    aliases.append((tokens, str(alias), record))
        self._aliases = sorted(
            aliases,
            key=lambda row: (-len(row[0]), row[0], TYPE_PRIORITY[str(row[2]["entity_type"])], row[2]["entity_id"]),
        )

    def match(self, query: str) -> list[AliasMatch]:
        tokens = normalized_tokens(query)
        occupied: set[int] = set()
        matched_entities: set[str] = set()
        matches: list[AliasMatch] = []
        for alias_tokens, alias, record in self._aliases:
            for start in range(len(tokens) - len(alias_tokens) + 1):
                end = start + len(alias_tokens)
                if tokens[start:end] != alias_tokens or any(index in occupied for index in range(start, end)):
                    continue
                entity_id = str(record["entity_id"])
                if entity_id in matched_entities:
                    continue
                occupied.update(range(start, end))
                matched_entities.add(entity_id)
                matches.append(AliasMatch(
                    entity_id=entity_id,
                    canonical_label=str(record["canonical_label"]),
                    entity_type=str(record["entity_type"]),
                    matched_alias=alias,
                    token_start=start,
                    token_end=end,
                    matched_query_span=" ".join(tokens[start:end]),
                    document_frequency=int(record["document_frequency"]),
                ))
        return sorted(matches, key=lambda match: (match.token_start, match.token_end, match.entity_id))


def build_graph(
    *,
    chunks: Sequence[Mapping[str, Any]],
    registry: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]], dict[str, Any]]:
    """Build exact mention and canonical undirected co-occurrence edges."""
    accepted = [row for row in registry if row["status"] == "accepted"]
    chunks_by_document: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_document[str(chunk["document_id"])].append(chunk)
    for values in chunks_by_document.values():
        values.sort(key=lambda row: str(row["chunk_id"]))

    chunk_entities: dict[str, set[str]] = {str(chunk["chunk_id"]): set() for chunk in chunks}
    mention_sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    for entity in accepted:
        entity_id = str(entity["entity_id"])
        labels = [str(entity["canonical_label"]), *map(str, entity["aliases"])]
        for chunk in chunks:
            chunk_id = str(chunk["chunk_id"])
            if any(_exact_contains(str(chunk["text"]), label) for label in labels):
                chunk_entities[chunk_id].add(entity_id)
                mention_sources[(entity_id, chunk_id)].add("exact_token_sequence")
        for document_id in entity["trusted_metadata_document_ids"]:
            # The first chunk is the deterministic document anchor.  Linking
            # metadata to every chunk would manufacture document-wide
            # co-occurrence, which the corrected methodology forbids.
            anchored_chunks = chunks_by_document.get(str(document_id), [])[:1]
            for anchored_chunk in anchored_chunks:
                chunk_id = str(anchored_chunk["chunk_id"])
                chunk_entities[chunk_id].add(entity_id)
                mention_sources[(entity_id, chunk_id)].add("trusted_metadata_link")

    support: dict[tuple[str, str], set[str]] = defaultdict(set)
    for chunk_id, entities in chunk_entities.items():
        ordered = sorted(entities)
        for left_index, left in enumerate(ordered):
            for right in ordered[left_index + 1 :]:
                support[(left, right)].add(chunk_id)

    entity_lookup = {str(row["entity_id"]): row for row in accepted}
    nodes = [
        {
            "node_id": f"entity:{entity_id}",
            "node_type": "entity",
            "entity_id": entity_id,
            "entity_type": entity_lookup[entity_id]["entity_type"],
            "canonical_label": entity_lookup[entity_id]["canonical_label"],
        }
        for entity_id in sorted(entity_lookup)
    ] + [
        {"node_id": f"chunk:{chunk['chunk_id']}", "node_type": "chunk", "chunk_id": str(chunk["chunk_id"]), "document_id": str(chunk["document_id"])}
        for chunk in sorted(chunks, key=lambda row: str(row["chunk_id"]))
    ]
    edges: list[dict[str, Any]] = []
    for (entity_id, chunk_id), sources in sorted(mention_sources.items()):
        edges.append({
            "edge_id": f"mention:{entity_id}:{chunk_id}",
            "edge_type": "MENTIONED_IN",
            "source": f"entity:{entity_id}",
            "target": f"chunk:{chunk_id}",
            "evidence_sources": sorted(sources),
        })
    for (left, right), chunk_ids in sorted(support.items()):
        edges.append({
            "edge_id": f"cooccurs:{left}:{right}",
            "edge_type": "CO_OCCURS_WITH",
            "source": f"entity:{left}",
            "target": f"entity:{right}",
            "supporting_chunk_ids": sorted(chunk_ids),
            "cooccurrence_count": len(chunk_ids),
        })

    adjacency: dict[str, set[str]] = defaultdict(set)
    degree = Counter()
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    all_node_ids = {row["node_id"] for row in nodes}
    seen: set[str] = set()
    component_sizes: list[int] = []
    for node_id in sorted(all_node_ids):
        if node_id in seen:
            continue
        queue = deque([node_id])
        seen.add(node_id)
        size = 0
        while queue:
            current = queue.popleft()
            size += 1
            for neighbor in sorted(adjacency[current]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        component_sizes.append(size)
    entity_degree = [degree[f"entity:{entity_id}"] for entity_id in entity_lookup]
    degree_distribution = Counter(str(value) for value in entity_degree)
    audit = {
        "entity_nodes": len(entity_lookup),
        "chunk_nodes": len(chunks),
        "mention_edges": len(mention_sources),
        "cooccurrence_edges": len(support),
        "total_edges": len(edges),
        "connected_components": len(component_sizes),
        "largest_component_fraction": max(component_sizes, default=0) / len(nodes) if nodes else 0.0,
        "isolated_entities": sorted(entity_id for entity_id in entity_lookup if degree[f"entity:{entity_id}"] == 0),
        "isolated_chunks": sorted(str(chunk["chunk_id"]) for chunk in chunks if degree[f"chunk:{chunk['chunk_id']}"] == 0),
        "entity_degree_distribution": dict(sorted(degree_distribution.items(), key=lambda item: int(item[0]))),
        "top_50_hubs": [
            {
                "entity_id": entity_id,
                "canonical_label": entity_lookup[entity_id]["canonical_label"],
                "entity_type": entity_lookup[entity_id]["entity_type"],
                "degree": degree[f"entity:{entity_id}"],
                "document_frequency": entity_lookup[entity_id]["document_frequency"],
                "corpus_evidence": entity_lookup[entity_id]["corpus_evidence"][:2],
            }
            for entity_id in sorted(entity_lookup, key=lambda item: (-degree[f"entity:{item}"], item))[:50]
        ],
    }
    serialized_chunk_entities = {chunk_id: sorted(entity_ids) for chunk_id, entity_ids in sorted(chunk_entities.items())}
    return sorted(nodes, key=lambda row: row["node_id"]), sorted(edges, key=lambda row: row["edge_id"]), serialized_chunk_entities, audit


def graph_adjacency(edges: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    """Reconstruct deterministic undirected adjacency from serialized edges."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        source, target = str(edge["source"]), str(edge["target"])
        adjacency[source].add(target)
        adjacency[target].add(source)
    return {node: tuple(sorted(neighbors)) for node, neighbors in sorted(adjacency.items())}


def rank_query(
    *,
    query: str,
    matcher: EntityMatcher,
    edges: Sequence[Mapping[str, Any]],
    n_chunks: int,
    maximum_path_length: int = 2,
    hop_decay: float = 0.5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Score chunks with independent per-seed shortest paths and no fallback."""
    if maximum_path_length != 2 or hop_decay != 0.5:
        raise ValueError("corrected Phase 3 scoring is frozen at depth=2 and hop_decay=0.5")
    matches = matcher.match(query)
    if not matches:
        return [], {"status": "no_valid_seed", "matched_seeds": [], "contributions": {}}
    adjacency = graph_adjacency(edges)
    scores: dict[str, float] = defaultdict(float)
    contributions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seed_rows: list[dict[str, Any]] = []
    for match in matches:
        seed_node = f"entity:{match.entity_id}"
        weight = math.log((n_chunks + 1) / (match.document_frequency + 1)) + 1
        seed_rows.append({**match.__dict__, "seed_weight": weight})
        distances = {seed_node: 0}
        predecessor: dict[str, str] = {}
        queue = deque([seed_node])
        while queue:
            current = queue.popleft()
            distance = distances[current]
            if distance >= maximum_path_length:
                continue
            for neighbor in adjacency.get(current, ()):
                candidate_distance = distance + 1
                if neighbor not in distances or candidate_distance < distances[neighbor]:
                    distances[neighbor] = candidate_distance
                    predecessor[neighbor] = current
                    queue.append(neighbor)
        for node, distance in sorted(distances.items()):
            if not node.startswith("chunk:") or not 1 <= distance <= maximum_path_length:
                continue
            chunk_id = node.removeprefix("chunk:")
            contribution = weight * (hop_decay**distance)
            path = [node]
            while path[-1] != seed_node:
                path.append(predecessor[path[-1]])
            path.reverse()
            scores[chunk_id] += contribution
            contributions[chunk_id].append({
                "entity_id": match.entity_id,
                "distance": distance,
                "path": path,
                "seed_weight": weight,
                "contribution": contribution,
            })
    ranking = [
        {"chunk_id": chunk_id, "rank": rank, "score": score}
        for rank, (chunk_id, score) in enumerate(sorted(scores.items(), key=lambda item: (-item[1], item[0])), 1)
        if score > 0
    ]
    return ranking, {
        "status": "ok" if ranking else "no_reachable_chunk",
        "matched_seeds": seed_rows,
        "contributions": {chunk_id: rows for chunk_id, rows in sorted(contributions.items())},
    }
