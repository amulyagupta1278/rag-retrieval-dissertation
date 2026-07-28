"""
QA Generator — Benchmark Layer
================================
Research purpose
    A stratified ground-truth QA dataset is the foundation of reproducible
    retrieval evaluation. Without gold evidence mappings, MRR, Recall@k, and
    nDCG@k cannot be computed. The benchmark directly operationalises H1–H3.

Design choice
    Template-based question generation from chunks combined with a manual
    review slot (the reviewed JSONL). Templates cover each query category
    defined in the dissertation: exact match, terminology-heavy, paraphrase,
    entity-relation, and multi-hop.

Alternative approaches
    LLM-based QA generation (e.g. GPT-4) produces more natural questions but
    introduces non-reproducible randomness and API cost. Template generation
    is auditable and free of external API dependencies at the mid-semester
    milestone.

Expected strengths
    Every generated item includes gold_evidence_ids enabling retrieval-layer
    evaluation (MRR/Recall@k/nDCG@k) independently of generation quality.

Expected weaknesses
    Template questions are more formulaic than human-written ones; diversity
    is limited by template coverage. The reviewed JSONL is the place to add
    manually written questions before the final submission.
"""

from __future__ import annotations

import json
import html
import logging
import pickle
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

QUERY_CATEGORIES = [
    "exact_match",
    "terminology_heavy",
    "paraphrase",
    "entity_relation",
    "multi_hop",
]

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]

_JSON_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
_MARKUP_RE = re.compile(r"<[^>]+>|&(?:lt|gt|amp|quot|#39);", re.I)
_SPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_FIELD_NAMES = {
    "answer", "answer_md", "question", "children", "text", "type", "link",
    "chunk_id", "doc_id", "schemeid", "_id", "core", "faqs", "documents",
    "schemecontent", "basicdetails", "applicationprocess", "eligibilitycriteria",
    "schemedefinitions", "paragraph", "list_item", "align_justify", "ol_list",
    "block_quote", "ul_list", "ordered_list", "unordered_list", "link", "offline", "online", "justify",
}
_ARTIFACT_RE = re.compile(
    r"[{}\[\]]|\b(?:answer_md|chunk_id|doc_id|schemeId|children|list_item|align_justify)\b",
    re.I,
)
_GENERIC_TERMS = {
    "the scheme", "the programme", "the program", "organisation", "organization",
    "it", "this", "this scheme", "the organization", "the organisation",
}
_BAD_SUBJECT_PREFIXES = {
    "the", "a", "an", "you", "your", "what", "which", "who", "how", "why",
    "when", "where", "is", "are", "does", "do", "can", "could", "will", "would",
}
_GENERIC_BRIDGES = {
    "application", "assistance", "bank", "beneficiary", "beneficiaries", "central",
    "central government", "central sector scheme", "centrally sponsored scheme", "department",
    "download", "email", "faq", "fellowship", "government", "government of india", "govt",
    "india", "indian", "institute", "loan", "ministry", "mobile number", "official website",
    "otp", "pension", "programme", "program", "scheme", "state", "state government", "states",
    "step", "the central government", "the government of india", "the scheme", "the state government",
    "yojana", "application form", "bank account", "certificate of internship", "family welfare",
    "farmers welfare", "new delhi", "post office", "the application form", "the state governments",
    "university institution", "the head of the institute", "head of the institute",
}
_BRIDGE_ARTIFACTS = {
    "answer md", "applicationprocess", "children", "dbtscheme", "exclusions md",
    "nodalministryname", "process md", "schemeid", "schemecontent",
}


def _normalise_evidence(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", html.unescape(text).lower()))


def _clean_leaf_text(text: str) -> str:
    """Extract human-facing JSON string values, never serialized keys/punctuation."""
    if not text.strip():
        return ""
    values: list[str] = []
    if '"' in text and (":" in text or "{" in text or "}" in text):
        for match in _JSON_STRING_RE.finditer(text):
            token = match.group()
            try:
                value = json.loads(token)
            except json.JSONDecodeError:
                continue
            remainder = text[match.end():]
            if re.match(r"\s*:", remainder):
                continue  # JSON field name
            value = html.unescape(str(value))
            value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
            value = re.sub(r"<[^>]+>", " ", value)
            value = value.replace('"', "")
            value = _SPACE_RE.sub(" ", value).strip(" \n\t\r\"'{}[]")
            if not value or value.lower() in _FIELD_NAMES:
                continue
            if re.fullmatch(r"[0-9a-f]{20,}", value.lower()) or re.fullmatch(r"[a-z]+(?:_[a-z]+)+", value.lower()):
                continue
            if len(value) >= 3 and re.search(r"[A-Za-z]", value):
                values.append(value)
    else:
        value = html.unescape(text)
        value = re.sub(r"<[^>]+>", " ", value)
        values.append(_SPACE_RE.sub(" ", value).strip())
    # Adjacent structured fields can repeat Markdown and rich-text versions.
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _normalise_evidence(value)
        if key and key not in seen:
            output.append(value)
            seen.add(key)
    # Preserve field boundaries so adjacent metadata values cannot form fake prose.
    return ". ".join(value.rstrip(" .") for value in output if value.rstrip(" ."))


def _sentences(text: str, minimum: int = 30) -> list[str]:
    return [
        _SPACE_RE.sub(" ", sentence).strip(" -:;\"'")
        for sentence in _SENTENCE_RE.split(text)
        if len(_SPACE_RE.sub(" ", sentence).strip()) >= minimum
        and len(_SPACE_RE.sub(" ", sentence).strip()) <= 500
        and not _ARTIFACT_RE.search(sentence)
    ]


def _usable_answer_sentence(sentence: str) -> bool:
    lower = sentence.lower().strip()
    if "?" in sentence:
        return False
    if re.match(r"^(?:true|false|https?://|central\s+ministry|ministry\s+of|department\s+of)\b", lower):
        return False
    if len(re.findall(r"\b[a-z]{3,}\b", sentence)) < 5:
        return False
    if re.search(r"\b(?:the|a|an|to|of|in|on|for|prescribed)\W*$", lower):
        return False
    metadata_markers = sum(marker in lower for marker in (
        "skills & employment", "social welfare & empowerment", "health & wellness",
        "education & learning", "banking,financial services", "individual central",
    ))
    return metadata_markers == 0


def _evidence_supports(answer: str, evidence_texts: list[str]) -> bool:
    """Require each multi-hop clause to be present or near-verbatim in gold evidence."""
    clauses = [part.strip() for part in answer.split(" Additionally, ") if part.strip()]
    normalised_evidence = [_normalise_evidence(text) for text in evidence_texts]
    for clause in clauses:
        target = _normalise_evidence(clause)
        if not target:
            return False
        if any(target in evidence for evidence in normalised_evidence):
            continue
        target_words = set(target.split())
        if not target_words or max(
            (len(target_words & set(evidence.split())) / len(target_words) for evidence in normalised_evidence),
            default=0.0,
        ) < 0.85:
            return False
    return True


def _valid_question_text(question: str) -> bool:
    if _ARTIFACT_RE.search(question) or '"' in question or re.search(r"'[^']+'", question):
        return False
    return len(question.split()) >= 4 and len(question) <= 240


def _validate_item(item: "QAItem", clean_by_id: dict[str, str], chunks_by_id: dict[str, dict]) -> tuple[bool, str]:
    if not _valid_question_text(item.question):
        return False, "question_artifact"
    evidence = [clean_by_id.get(cid, "") for cid in item.gold_evidence_ids]
    if not evidence or any(not text for text in evidence):
        return False, "missing_clean_evidence"
    if not _evidence_supports(item.reference_answer, evidence):
        return False, "answer_not_supported"
    if item.category == "exact_match":
        subject = re.sub(r"^What is\s+", "", item.question, flags=re.I).rstrip("?").strip()
        words = subject.lower().split()
        has_acronym = bool(re.search(r"\b[A-Z]{2,}(?:-[A-Z]+)?\b", subject))
        if not words or words[0] in _BAD_SUBJECT_PREFIXES or words[-1] in {"if", "to", "of", "and", "you"}:
            return False, "generic_exact_subject"
        if not has_acronym and (len(words) < 2 or subject.lower() in {"men and women", "terms and conditions"}):
            return False, "generic_exact_subject"
    if item.category == "entity_relation":
        subject = re.sub(r"^How does\s+", "", item.question, flags=re.I).split(" relate to ", 1)[0].strip()
        if not subject or subject.split()[0].lower() in _BAD_SUBJECT_PREFIXES:
            return False, "invalid_relation_subject"
    if item.category == "multi_hop":
        if len(item.gold_evidence_ids) != 2:
            return False, "invalid_multi_hop_arity"
        left, right = (chunks_by_id[cid] for cid in item.gold_evidence_ids)
        same_document = left["doc_id"] == right["doc_id"]
        shared = _shared_entities(clean_by_id[left["chunk_id"]], clean_by_id[right["chunk_id"]])
        if not same_document and not shared:
            return False, "unrelated_multi_hop"
    return True, "accepted"


def _shared_entities(left: str, right: str) -> list[str]:
    pattern = re.compile(r"\b(?:[A-Z]{2,8}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5})\b")
    left_entities = {match.group().strip() for match in pattern.finditer(left)}
    right_lower = right.lower()
    return sorted(
        (entity for entity in left_entities if entity.lower() in right_lower and entity.lower() not in _GENERIC_TERMS),
        key=lambda value: (-len(value), value),
    )


def _find_string_field(value, field_name: str) -> str | None:
    if isinstance(value, dict):
        field = value.get(field_name)
        if isinstance(field, str) and field.strip():
            return field.strip()
        for child in value.values():
            found = _find_string_field(child, field_name)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_string_field(child, field_name)
            if found:
                return found
    return None


def _source_scheme_name(chunk: dict, cache: dict[str, str]) -> str:
    """Prefer schemeName parsed from official source JSON over catalog label."""
    path = str(chunk.get("source_path") or "")
    if path in cache:
        return cache[path]
    name = ""
    if path:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            name = _find_string_field(payload, "schemeName") or ""
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            name = ""
    cache[path] = name or str(chunk.get("scheme_name") or chunk.get("section_title") or "")
    return cache[path]


def _collect_string_fields(value, field_names: set[str]) -> list[str]:
    """Collect human-facing values for selected official-source metadata fields."""
    def leaf_strings(node) -> list[str]:
        if isinstance(node, str):
            return [html.unescape(node).strip()] if node.strip() else []
        if isinstance(node, dict):
            return [text for child in node.values() for text in leaf_strings(child)]
        if isinstance(node, list):
            return [text for child in node for text in leaf_strings(child)]
        return []

    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in field_names:
                found.extend(leaf_strings(child))
            found.extend(_collect_string_fields(child, field_names))
    elif isinstance(value, list):
        for child in value:
            found.extend(_collect_string_fields(child, field_names))
    return found


def _source_relationship_values(chunk: dict, cache: dict[str, set[str]]) -> set[str]:
    """Return normalized ministry/department/agency values from parsed source JSON."""
    path = str(chunk.get("source_path") or "")
    if path in cache:
        return cache[path]
    values: set[str] = set()
    if path:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            raw_values = _collect_string_fields(
                payload,
                {"nodalministryname", "nodaldepartmentname", "implementingagency"},
            )
            values = {_normalise_evidence(value) for value in raw_values if _normalise_evidence(value)}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            values = set()
    cache[path] = values
    return values


def _bridge_matches_structured_relationship(bridge: str, values: set[str]) -> bool:
    bridge_key = _normalise_evidence(bridge)
    return any(bridge_key in value or value in bridge_key for value in values if len(value.split()) >= 2)


@dataclass
class QAItem:
    """A single benchmark question with gold evidence mapping."""

    question_id: str
    question: str
    category: str
    difficulty: str
    reference_answer: str
    gold_evidence_ids: list[str]
    source_doc_ids: list[str]
    split: str = "test"           # dev | test
    benchmark_version: str | None = None
    parent_question_id: str | None = None
    review_status: str = "unreviewed"
    review_revision: int = 0
    fold_id: int | None = None
    extra_meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "category": self.category,
            "difficulty": self.difficulty,
            "reference_answer": self.reference_answer,
            "gold_evidence_ids": self.gold_evidence_ids,
            "source_doc_ids": self.source_doc_ids,
            "split": self.split,
            "benchmark_version": self.benchmark_version,
            "parent_question_id": self.parent_question_id,
            "review_status": self.review_status,
            "review_revision": self.review_revision,
            "fold_id": self.fold_id,
            "extra_meta": self.extra_meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QAItem":
        return cls(**d)


@dataclass(frozen=True)
class CrossSchemeCandidate:
    """Two distinct schemes connected by evidence-backed graph entity."""

    scheme_a: str
    scheme_b: str
    chunk_a: str
    chunk_b: str
    doc_a: str
    doc_b: str
    bridge: str
    relationship_type: str
    sentence_a: str
    sentence_b: str

    @property
    def pair_key(self) -> tuple[str, str]:
        return tuple(sorted((_normalise_evidence(self.scheme_a), _normalise_evidence(self.scheme_b))))


def _is_semantic_bridge(entity: str) -> bool:
    normalised = _normalise_evidence(entity)
    if not normalised or normalised in _GENERIC_BRIDGES:
        return False
    if any(artifact in normalised for artifact in _BRIDGE_ARTIFACTS):
        return False
    if re.fullmatch(r"[0-9a-f]{12,}", normalised) or "\\n" in entity or "_md" in entity.lower():
        return False
    if re.search(r"&(?:amp|lt|gt|quot|#\d+);", entity, re.I) or re.search(r"\bamp\b", normalised):
        return False
    if re.search(r"\b(?:and|or|of|the|f)\W*$", normalised) or entity.count("(") != entity.count(")"):
        return False
    words = normalised.split()
    is_acronym = bool(re.fullmatch(r"[A-Z][A-Z0-9-]{1,9}", entity.strip()))
    if len(words) < 2 and not is_acronym:
        return False
    semantic_pattern = re.compile(
        r"\b(?:ministry|department|authority|council|corporation|board|agency|commission|"
        r"organisation|organization|institute|university|panchayat|municipality|municipal council|"
        r"hospitals?|health centres?|national trust|provident fund|act|rules?|code|law|"
        r"scheduled caste|scheduled tribe|backward classes|self help groups?|below poverty line|"
        r"self help groups?|workers?|students?|senior citizens?|persons with disabilities|"
        r"direct benefit transfer|national social assistance programme|district hospitals?|"
        r"union territor(?:y|ies)|himalayan states|backward districts)\b",
        re.I,
    )
    return len(normalised) >= 4 and (is_acronym or bool(semantic_pattern.search(entity)))


def _bridge_identity(bridge: str) -> str:
    """Canonical key used to enforce the semantic bridge diversity cap."""
    value = re.sub(r"^the\s+", "", _normalise_evidence(bridge))
    return re.sub(r"\s+government of india$", "", value).strip()


def _relationship_type(bridge: str) -> str:
    lower = bridge.lower()
    if re.search(r"\b(?:act|rules?|code|law)\b", lower):
        return "law"
    if re.search(r"\b(?:ministry|department|authority|council|corporation|board|agency|commission|organisation|organization)\b", lower):
        return "organization"
    if re.search(r"\b(?:institute|university|panchayat|municipality|municipal council|hospitals?|health centres?|national trust|provident fund)\b", lower):
        return "implementing_body"
    if re.search(r"\b(?:scheduled caste|scheduled tribe|backward classes|self help groups?|below poverty line|women|farmers?|workers?|students?|senior citizens?|persons with disabilities)\b", lower):
        return "beneficiary_group"
    if re.search(r"\b(?:district|state|city|delhi|pradesh|union territor|himalayan)\b", lower):
        return "location"
    if "direct benefit transfer" in lower or "national social assistance programme" in lower:
        return "named_mechanism"
    return "named_entity"


def _sentence_containing_bridge(clean_text: str, bridge: str) -> str | None:
    bridge_key = _normalise_evidence(bridge)
    for sentence in _sentences(clean_text, minimum=45):
        if _usable_answer_sentence(sentence) and bridge_key in _normalise_evidence(sentence):
            return sentence.rstrip(" ;,.") + "."
    return None


def _build_cross_scheme_candidates(
    chunks: list[dict], graph_path: str | Path,
) -> tuple[list[CrossSchemeCandidate], dict[str, str], dict[str, str]]:
    """Build verified cross-scheme candidates from existing graph without mutating it."""
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    clean_by_id = {chunk["chunk_id"]: _clean_leaf_text(chunk.get("text", "")) for chunk in chunks}
    source_name_cache: dict[str, str] = {}
    relationship_cache: dict[str, set[str]] = {}
    scheme_by_id = {chunk["chunk_id"]: _source_scheme_name(chunk, source_name_cache).strip() for chunk in chunks}
    relationships_by_id = {
        chunk["chunk_id"]: _source_relationship_values(chunk, relationship_cache) for chunk in chunks
    }
    with Path(graph_path).open("rb") as handle:
        payload = pickle.load(handle)
    graph = payload["graph"]

    entity_chunks: dict[str, list[str]] = defaultdict(list)
    for chunk_id, chunk in chunks_by_id.items():
        if chunk_id not in graph:
            continue
        clean_key = _normalise_evidence(clean_by_id[chunk_id])
        for entity in graph.neighbors(chunk_id):
            if graph.nodes[entity].get("type") != "entity":
                continue
            bridge = str(entity).strip(" ,;:.")
            bridge_key = _normalise_evidence(bridge)
            if _is_semantic_bridge(bridge) and bridge_key in clean_key:
                entity_chunks[bridge].append(chunk_id)

        # Structured source metadata is an equally valid candidate origin.
        # It is still accepted only when the same value is present in parsed
        # clean text, so metadata cannot silently manufacture a relationship.
        for bridge in sorted(relationships_by_id[chunk_id]):
            if _is_semantic_bridge(bridge) and bridge in clean_key:
                entity_chunks[bridge].append(chunk_id)

    candidates: dict[tuple[str, str, str], CrossSchemeCandidate] = {}
    for bridge, chunk_ids in sorted(entity_chunks.items()):
        by_scheme: dict[str, list[str]] = defaultdict(list)
        for chunk_id in sorted(set(chunk_ids)):
            scheme = scheme_by_id[chunk_id]
            if scheme:
                by_scheme[scheme].append(chunk_id)
        schemes = sorted(by_scheme, key=_normalise_evidence)
        for index, scheme_a in enumerate(schemes):
            for scheme_b in schemes[index + 1:]:
                if _normalise_evidence(scheme_a) == _normalise_evidence(scheme_b):
                    continue
                selected = None
                relationship_type = _relationship_type(bridge)
                for chunk_a in by_scheme[scheme_a]:
                    if relationship_type == "organization" and not _bridge_matches_structured_relationship(
                        bridge, relationships_by_id[chunk_a]
                    ):
                        continue
                    sentence_a = _sentence_containing_bridge(clean_by_id[chunk_a], bridge)
                    if not sentence_a:
                        continue
                    for chunk_b in by_scheme[scheme_b]:
                        if chunks_by_id[chunk_a]["doc_id"] == chunks_by_id[chunk_b]["doc_id"]:
                            continue
                        if relationship_type == "organization" and not _bridge_matches_structured_relationship(
                            bridge, relationships_by_id[chunk_b]
                        ):
                            continue
                        sentence_b = _sentence_containing_bridge(clean_by_id[chunk_b], bridge)
                        if sentence_b:
                            selected = CrossSchemeCandidate(
                                scheme_a, scheme_b, chunk_a, chunk_b,
                                chunks_by_id[chunk_a]["doc_id"], chunks_by_id[chunk_b]["doc_id"],
                                bridge, relationship_type, sentence_a, sentence_b,
                            )
                            break
                    if selected:
                        break
                if selected:
                    key = (*selected.pair_key, _bridge_identity(bridge))
                    candidates.setdefault(key, selected)
    return list(candidates.values()), clean_by_id, scheme_by_id


# ---------------------------------------------------------------------------
# Template factories
# ---------------------------------------------------------------------------

def _exact_match_templates(text: str, chunk_id: str, doc_id: str, qnum: int, scheme_name: str = "") -> list[QAItem]:
    """Create a definition query only when source passage names its scheme."""
    scheme_name = _SPACE_RE.sub(" ", scheme_name).strip(" \"'{}[]")
    if not scheme_name or _ARTIFACT_RE.search(scheme_name):
        return []
    normalised_scheme = _normalise_evidence(scheme_name)
    for sentence in _sentences(text, minimum=55):
        if _usable_answer_sentence(sentence) and normalised_scheme in _normalise_evidence(sentence) and re.search(
            r"\b(?:is|was launched|aims|provides|offers|scheme|programme|mission)\b", sentence, re.I
        ):
            return [QAItem(
                question_id=f"q_{qnum:04d}", question=f"What is {scheme_name}?",
                category="exact_match", difficulty="easy", reference_answer=sentence,
                gold_evidence_ids=[chunk_id], source_doc_ids=[doc_id],
            )]
    return []


def _terminology_heavy_templates(text: str, chunk_id: str, doc_id: str, qnum: int) -> list[QAItem]:
    """Build questions only from explicit expansion/acronym statements."""
    items: list[QAItem] = []
    matches: list[tuple[str, str]] = []
    # Canonical government prose: Long Form (ACRONYM).
    for match in re.finditer(r"\b([A-Z][A-Za-z&/-]*(?:\s+(?:of|and|for|the|in|on|[A-Z][A-Za-z&/-]*)){1,11})\s*\(([A-Z][A-Z0-9-]{1,9})\)", text):
        matches.append((match.group(2), match.group(1).strip()))
    # Explicit FAQ wording: full name/form of ACRONYM is Long Form.
    for match in re.finditer(r"(?:full\s+(?:name|form)|expansion)\s+of\s+([A-Z][A-Z0-9-]{1,9})\s+is\s+([A-Z][A-Za-z]*(?:\s+[A-Za-z&/-]+){1,11})", text, re.I):
        matches.append((match.group(1).upper(), match.group(2).strip()))
    seen: set[str] = set()
    for acronym, expansion in matches:
        expansion_words = [word.lower() for word in re.findall(r"[A-Za-z]+", expansion) if word.lower() not in {"of", "and", "for", "the", "in", "on"}]
        initials = "".join(word[0] for word in expansion_words).upper()
        compact = re.sub(r"[^A-Z0-9]", "", acronym.upper())
        if compact in seen or len(expansion_words) < 2 or initials != compact:
            continue
        seen.add(compact)
        # Expansion itself must occur verbatim in parsed source text.
        if _normalise_evidence(expansion) not in _normalise_evidence(text):
            continue
        qid = f"q_{qnum:04d}"
        items.append(
            QAItem(
                question_id=qid,
                question=f"What does {acronym} stand for?",
                category="terminology_heavy",
                difficulty="easy",
                reference_answer=expansion,
                gold_evidence_ids=[chunk_id],
                source_doc_ids=[doc_id],
            )
        )
        qnum += 1
        if len(items) >= 2:
            break
    return items


def _paraphrase_templates(
    text: str, chunk_id: str, doc_id: str, qnum: int, scheme_name: str = "",
) -> list[QAItem]:
    """Create questions whose surface form differs from the evidence text."""
    items: list[QAItem] = []
    sentences = [sentence for sentence in _sentences(text, minimum=50) if _usable_answer_sentence(sentence)]
    for sent in sentences[:2]:
        words = sent.split()
        if len(words) < 6:
            continue
        subject = _SPACE_RE.sub(" ", scheme_name).strip(" .,!?::;-\"'{}[]")
        if not subject or _ARTIFACT_RE.search(subject):
            continue
        qid = f"q_{qnum:04d}"
        items.append(
            QAItem(
                question_id=qid,
                question=f"What detail does the source provide about {subject}?",
                category="paraphrase",
                difficulty="medium",
                reference_answer=sent,
                gold_evidence_ids=[chunk_id],
                source_doc_ids=[doc_id],
            )
        )
        qnum += 1
    return items[:1]


def _entity_relation_templates(text: str, chunk_id: str, doc_id: str, qnum: int, scheme_name: str = "") -> list[QAItem]:
    """Relate named scheme to supported beneficiaries using explicit source sentence."""
    scheme_name = _SPACE_RE.sub(" ", scheme_name).strip(" \"'{}[]")
    if not scheme_name or _ARTIFACT_RE.search(scheme_name):
        return []
    for sentence in _sentences(text, minimum=55):
        if _usable_answer_sentence(sentence) and re.search(r"\b(?:beneficiar|provid|support|assist|enable|eligible|benefit)\w*\b", sentence, re.I):
            return [QAItem(
                question_id=f"q_{qnum:04d}",
                question=f"How does {scheme_name} support its intended beneficiaries?",
                category="entity_relation", difficulty="medium", reference_answer=sentence,
                gold_evidence_ids=[chunk_id], source_doc_ids=[doc_id],
            )]
    return []


def _multi_hop_template(
    chunk_a: dict, chunk_b: dict, clean_a: str, clean_b: str, qnum: int,
    scheme_name: str = "",
) -> Optional[QAItem]:
    """Create a question only for same-document or shared-entity evidence."""
    same_document = chunk_a["doc_id"] == chunk_b["doc_id"]
    shared_entities = _shared_entities(clean_a, clean_b)
    if not same_document and not shared_entities:
        return None
    sentences_a = [sentence for sentence in _sentences(clean_a, 45) if _usable_answer_sentence(sentence)]
    sentences_b = [sentence for sentence in _sentences(clean_b, 45) if _usable_answer_sentence(sentence)]
    if not sentences_a or not sentences_b:
        return None
    subject = (
        scheme_name or chunk_a.get("scheme_name") or chunk_a.get("section_title")
        if same_document else shared_entities[0]
    )
    subject = _SPACE_RE.sub(" ", str(subject or "this scheme")).strip(" \"'{}[]")
    if not subject or _ARTIFACT_RE.search(subject):
        return None
    answer_a = sentences_a[0].rstrip(" ;,.") + "."
    answer_b = sentences_b[0].rstrip(" ;,.") + "."
    return QAItem(
        question_id=f"q_{qnum:04d}",
        question=f"What two related details are provided about {subject}?",
        category="multi_hop",
        difficulty="hard",
        reference_answer=f"{answer_a} Additionally, {answer_b}",
        gold_evidence_ids=[chunk_a["chunk_id"], chunk_b["chunk_id"]],
        source_doc_ids=sorted({chunk_a["doc_id"], chunk_b["doc_id"]}),
    )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class QAGenerator:
    """
    Generates a stratified QA benchmark from a corpus of chunks.

    Parameters
    ----------
    seed : int
        Random seed for reproducible sampling.
    dev_ratio : float
        Fraction of items assigned to the dev split.
    """

    def __init__(self, seed: int = 42, dev_ratio: float = 0.2) -> None:
        self.seed = seed
        self.dev_ratio = dev_ratio
        self._rng = random.Random(seed)
        self.last_generation_stats: dict = {}

    @staticmethod
    def assign_stratified_splits(
        items: list[QAItem], *, dev_ratio: float = 0.2, seed: int = 42,
    ) -> None:
        """Assign deterministic per-category splits without changing item order."""
        if not 0 < dev_ratio < 1:
            raise ValueError("dev_ratio must be between 0 and 1")
        by_category: dict[str, list[QAItem]] = defaultdict(list)
        for item in items:
            by_category[item.category].append(item)
        rng = random.Random(seed)
        for category in sorted(by_category):
            values = sorted(by_category[category], key=lambda item: item.question_id)
            rng.shuffle(values)
            dev_count = max(1, int(len(values) * dev_ratio))
            dev_ids = {item.question_id for item in values[:dev_count]}
            for item in values:
                item.split = "dev" if item.question_id in dev_ids else "test"

    @staticmethod
    def assign_stratified_folds(
        items: list[QAItem], *, folds: int = 5, seed: int = 42,
        split: str = "dev",
    ) -> None:
        """Assign balanced deterministic folds for exploratory model selection."""
        if folds < 2:
            raise ValueError("folds must be at least 2")
        by_category: dict[str, list[QAItem]] = defaultdict(list)
        for item in items:
            by_category[item.category].append(item)
        rng = random.Random(seed)
        for category in sorted(by_category):
            values = sorted(by_category[category], key=lambda item: item.question_id)
            if len(values) % folds:
                raise ValueError(
                    f"Category {category} count {len(values)} is not divisible by {folds}"
                )
            rng.shuffle(values)
            for index, item in enumerate(values):
                item.split = split
                item.fold_id = index % folds

    def generate(self, chunks: list[dict], max_per_category: int = 20) -> list[QAItem]:
        """
        Generate QA items from *chunks*.

        Parameters
        ----------
        chunks : list[dict]
            Chunk dicts as produced by Chunker.to_dict().
        max_per_category : int
            Maximum items per query category.

        Returns
        -------
        list[QAItem]
        """
        chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
        clean_by_id = {chunk["chunk_id"]: _clean_leaf_text(chunk.get("text", "")) for chunk in chunks}
        source_name_cache: dict[str, str] = {}
        scheme_name_by_id = {chunk["chunk_id"]: _source_scheme_name(chunk, source_name_cache) for chunk in chunks}
        shuffled = list(chunks)
        self._rng.shuffle(shuffled)
        accepted: dict[str, list[QAItem]] = {category: [] for category in QUERY_CATEGORIES}
        candidate_count = 0
        rejected_count = 0
        rejection_reasons: dict[str, int] = {}
        accepted_questions: set[str] = set()

        def consider(items: list[QAItem]) -> None:
            nonlocal candidate_count, rejected_count
            for item in items:
                if len(accepted[item.category]) >= max_per_category:
                    continue
                candidate_count += 1
                question_key = _normalise_evidence(item.question)
                if question_key in accepted_questions:
                    rejected_count += 1
                    rejection_reasons["duplicate_question"] = rejection_reasons.get("duplicate_question", 0) + 1
                    continue
                valid, reason = _validate_item(item, clean_by_id, chunks_by_id)
                if valid:
                    accepted[item.category].append(item)
                    accepted_questions.add(question_key)
                else:
                    rejected_count += 1
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

        for chunk in shuffled:
            text = clean_by_id[chunk["chunk_id"]]
            cid = chunk["chunk_id"]
            did = chunk["doc_id"]
            scheme_name = scheme_name_by_id[cid]
            consider(_exact_match_templates(text, cid, did, candidate_count + 1, scheme_name))
            consider(_terminology_heavy_templates(text, cid, did, candidate_count + 1))
            consider(_paraphrase_templates(text, cid, did, candidate_count + 1, scheme_name))
            consider(_entity_relation_templates(text, cid, did, candidate_count + 1, scheme_name))
            if all(len(accepted[category]) >= max_per_category for category in QUERY_CATEGORIES[:-1]):
                break

        # Multi-hop candidates: adjacent chunks within same source document first.
        ordered = sorted(chunks, key=lambda chunk: (chunk["doc_id"], chunk.get("chunk_index", 0)))
        for left, right in zip(ordered, ordered[1:]):
            if len(accepted["multi_hop"]) >= max_per_category:
                break
            if left["doc_id"] != right["doc_id"]:
                continue
            item = _multi_hop_template(
                left, right, clean_by_id[left["chunk_id"]], clean_by_id[right["chunk_id"]],
                candidate_count + 1, scheme_name_by_id[left["chunk_id"]],
            )
            if item:
                consider([item])

        all_items = [item for category in QUERY_CATEGORIES for item in accepted[category]]
        for index, item in enumerate(all_items, 1):
            item.question_id = f"q_{index:04d}"

        self.assign_stratified_splits(all_items, dev_ratio=self.dev_ratio, seed=self.seed)
        all_items.sort(key=lambda item: item.question_id)

        self.last_generation_stats = {
            "candidates_generated": candidate_count,
            "accepted": len(all_items),
            "rejected": rejected_count,
            "rejection_rate": round(rejected_count / candidate_count, 4) if candidate_count else 0.0,
            "rejection_reasons": dict(sorted(rejection_reasons.items())),
            "accepted_by_category": {category: len(accepted[category]) for category in QUERY_CATEGORIES},
        }

        logger.info(
            "Generated %d QA items (exact=%d, term=%d, para=%d, entrel=%d, multi=%d)",
            len(all_items),
            len(accepted["exact_match"]),
            len(accepted["terminology_heavy"]),
            len(accepted["paraphrase"]),
            len(accepted["entity_relation"]),
            len(accepted["multi_hop"]),
        )
        return all_items

    def generate_cross_scheme(
        self,
        chunks: list[dict],
        graph_path: str | Path = "indexes/graphrag/graph.gpickle",
        per_category: int = 20,
    ) -> tuple[list[QAItem], list[dict]]:
        """Generate balanced cross-scheme entity-relation and multi-hop items."""
        candidates, clean_by_id, _ = _build_cross_scheme_candidates(chunks, graph_path)
        rng = random.Random(self.seed)
        rng.shuffle(candidates)
        accepted: dict[str, list[QAItem]] = {"entity_relation": [], "multi_hop": []}
        audit: list[dict] = []
        used_pairs: set[tuple[str, str]] = set()
        bridge_counts: Counter = Counter()
        scheme_counts: dict[str, Counter] = {category: Counter() for category in accepted}
        rejected = Counter()
        considered = 0

        # Use every available bridge once before permitting its second use.
        # This satisfies the global diversity cap without starving a category.
        allocation_order = [
            (bridge_cap, candidate)
            for bridge_cap in (1, 2)
            for candidate in candidates
        ]
        for bridge_cap, candidate in allocation_order:
            categories = tuple(sorted(accepted, key=lambda value: (len(accepted[value]), value)))
            for category in categories:
                if len(accepted[category]) >= per_category:
                    continue
                considered += 1
                pair_key = candidate.pair_key
                bridge_key = _bridge_identity(candidate.bridge)
                if pair_key in used_pairs:
                    rejected["pair_reused_across_categories"] += 1
                    continue
                if bridge_counts[bridge_key] >= bridge_cap:
                    rejected["bridge_diversity_cap"] += 1
                    continue
                if scheme_counts[category][_normalise_evidence(candidate.scheme_a)] >= 3 or scheme_counts[category][_normalise_evidence(candidate.scheme_b)] >= 3:
                    rejected["scheme_diversity_cap"] += 1
                    continue
                if category == "entity_relation":
                    question = (
                        f"How are {candidate.scheme_a} and {candidate.scheme_b} "
                        f"related through {candidate.bridge}?"
                    )
                else:
                    question = (
                        f"What combined evidence connects {candidate.scheme_a} and "
                        f"{candidate.scheme_b} through {candidate.bridge}?"
                    )
                item = QAItem(
                    question_id="",
                    question=question,
                    category=category,
                    difficulty="hard" if category == "multi_hop" else "medium",
                    reference_answer=f"{candidate.sentence_a} Additionally, {candidate.sentence_b}",
                    gold_evidence_ids=[candidate.chunk_a, candidate.chunk_b],
                    source_doc_ids=[candidate.doc_a, candidate.doc_b],
                    extra_meta={
                        "scheme_names": [candidate.scheme_a, candidate.scheme_b],
                        "bridge_entity": candidate.bridge,
                        "relationship_type": candidate.relationship_type,
                        "cross_scheme_validated": True,
                        "validation_result": "accepted",
                    },
                )
                valid, reason = self._validate_cross_scheme_item(item, clean_by_id, chunks)
                if not valid:
                    rejected[reason] += 1
                    continue
                item.question_id = f"q_{(61 if category == 'entity_relation' else 81) + len(accepted[category]):04d}"
                accepted[category].append(item)
                used_pairs.add(pair_key)
                bridge_counts[bridge_key] += 1
                scheme_counts[category][_normalise_evidence(candidate.scheme_a)] += 1
                scheme_counts[category][_normalise_evidence(candidate.scheme_b)] += 1
                audit.append({
                    "question_id": item.question_id,
                    "category": category,
                    "schemes": [candidate.scheme_a, candidate.scheme_b],
                    "bridge_entity": candidate.bridge,
                    "relationship_type": candidate.relationship_type,
                    "gold_chunk_ids": [candidate.chunk_a, candidate.chunk_b],
                    "source_doc_ids": [candidate.doc_a, candidate.doc_b],
                    "evidence_snippets": [candidate.sentence_a[:300], candidate.sentence_b[:300]],
                    "distinct_schemes": True,
                    "distinct_documents": True,
                    "validation_result": "accepted",
                })
                break
            if all(len(values) >= per_category for values in accepted.values()):
                break

        if any(len(items) != per_category for items in accepted.values()):
            raise RuntimeError(
                f"Cross-scheme gate failed: entity_relation={len(accepted['entity_relation'])}, "
                f"multi_hop={len(accepted['multi_hop'])}, rejected={dict(rejected)}"
            )
        items = accepted["entity_relation"] + accepted["multi_hop"]
        unique_rejected = len(candidates) - len(items)
        self.last_generation_stats = {
            "cross_scheme_candidates_available": len(candidates),
            "candidates_considered": len(candidates),
            "accepted": len(items),
            "rejected": unique_rejected,
            "rejection_rate": round(unique_rejected / len(candidates), 4) if candidates else 0.0,
            "selection_attempts": considered,
            "selection_rejections": sum(rejected.values()),
            "selection_rejection_reasons": dict(sorted(rejected.items())),
            "accepted_by_category": {category: len(values) for category, values in accepted.items()},
            "distinct_scheme_pairs": len(used_pairs),
        }
        return items, audit

    @staticmethod
    def _validate_cross_scheme_item(
        item: QAItem, clean_by_id: dict[str, str], chunks: list[dict],
    ) -> tuple[bool, str]:
        chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
        if not _valid_question_text(item.question) or len(item.question) > 240:
            return False, "invalid_question"
        if len(item.gold_evidence_ids) != 2 or len(item.source_doc_ids) != 2:
            return False, "invalid_gold_arity"
        if item.source_doc_ids[0] == item.source_doc_ids[1]:
            return False, "same_document"
        schemes = item.extra_meta.get("scheme_names", [])
        if len(schemes) != 2 or _normalise_evidence(schemes[0]) == _normalise_evidence(schemes[1]):
            return False, "same_scheme"
        bridge = str(item.extra_meta.get("bridge_entity", ""))
        if not _is_semantic_bridge(bridge):
            return False, "invalid_bridge"
        bridge_key = _normalise_evidence(bridge)
        evidence = [clean_by_id.get(chunk_id, "") for chunk_id in item.gold_evidence_ids]
        if any(not text or bridge_key not in _normalise_evidence(text) for text in evidence):
            return False, "bridge_missing_from_evidence"
        clauses = item.reference_answer.split(" Additionally, ")
        if len(clauses) != 2:
            return False, "invalid_answer_arity"
        for clause, text in zip(clauses, evidence):
            target = _normalise_evidence(clause)
            source = _normalise_evidence(text)
            if target not in source:
                target_words = set(target.split())
                if not target_words or len(target_words & set(source.split())) / len(target_words) < 0.85:
                    return False, "answer_clause_not_supported"
        if any(chunk_id not in chunks_by_id for chunk_id in item.gold_evidence_ids):
            return False, "missing_gold_chunk"
        return True, "accepted"

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def save(items: list[QAItem], path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(item.to_dict()) + "\n")
        logger.info("Saved %d QA items → %s", len(items), p)

    @staticmethod
    def load(path: str | Path) -> list[QAItem]:
        p = Path(path)
        items: list[QAItem] = []
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    items.append(QAItem.from_dict(json.loads(line)))
        return items
