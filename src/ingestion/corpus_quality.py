"""Quality, provenance, deduplication, and statistics helpers for corpus v2."""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REQUIRED_CATALOG_FIELDS = {
    "catalog_id", "document_id", "source", "ministry", "scheme_name",
    "publication_date", "url", "document_type", "format", "language",
    "scope", "enabled",
}
REQUIRED_DOCUMENT_TYPES = {
    "scheme_description", "operational_guideline", "faq",
    "implementation_manual", "eligibility_beneficiary", "funding_guideline",
    "application_procedure",
}
_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_WORD_RE = re.compile(r"[a-z0-9]+")
_EXPLICIT_HOSTS = {"mygov.in", "www.mygov.in"}


class CorpusValidationError(ValueError):
    """Raised when catalog or corpus invariants fail."""


def canonicalize_url(url: str) -> str:
    """Return stable URL form used for duplicate detection."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    port = f":{parts.port}" if parts.port else ""
    path = re.sub(r"/{2,}", "/", parts.path or "/").rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host + port, path, parts.query, ""))


def is_authoritative_url(url: str, explicit_hosts: set[str] | None = None) -> bool:
    """Accept HTTPS Indian government hosts and explicit reviewed exceptions."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    allowed = _EXPLICIT_HOSTS | set(explicit_hosts or ())
    return parts.scheme.lower() == "https" and (
        host.endswith(".gov.in") or host.endswith(".nic.in") or host in allowed
    )


def validate_catalog(records: list[dict], explicit_hosts: set[str] | None = None) -> None:
    """Validate source catalog schema and stable identifiers."""
    seen_catalog: set[str] = set()
    seen_documents: set[str] = set()
    errors: list[str] = []
    for line_no, record in enumerate(records, 1):
        missing = REQUIRED_CATALOG_FIELDS - record.keys()
        if missing:
            errors.append(f"record {line_no}: missing {sorted(missing)}")
            continue
        cid = str(record["catalog_id"])
        did = str(record["document_id"])
        if not _ID_RE.fullmatch(cid) or not _ID_RE.fullmatch(did):
            errors.append(f"record {line_no}: IDs must be lowercase snake_case")
        if cid in seen_catalog:
            errors.append(f"record {line_no}: duplicate catalog_id {cid}")
        if did in seen_documents:
            errors.append(f"record {line_no}: duplicate document_id {did}")
        seen_catalog.add(cid)
        seen_documents.add(did)
        if record["scope"] not in {"central", "national"}:
            errors.append(f"record {line_no}: invalid scope {record['scope']!r}")
        if record["language"] != "en":
            errors.append(f"record {line_no}: language must be 'en'")
        if record["format"] not in {"pdf", "docx", "html", "txt", "json"}:
            errors.append(f"record {line_no}: unsupported format {record['format']!r}")
        if not is_authoritative_url(str(record["url"]), explicit_hosts):
            errors.append(f"record {line_no}: non-authoritative URL {record['url']}")
        publication_date = record["publication_date"]
        if publication_date is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(publication_date)):
            errors.append(f"record {line_no}: publication_date must be ISO date or null")
    if errors:
        raise CorpusValidationError("; ".join(errors))


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return " ".join(_WORD_RE.findall(normalized))


def text_sha256(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def word_shingles(text: str, size: int = 5) -> set[tuple[str, ...]]:
    words = normalize_text(text).split()
    if len(words) < size:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def jaccard_similarity(left: set, right: set) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _source_rank(doc: dict) -> tuple:
    url = str(doc.get("url", ""))
    host = (urlsplit(url).hostname or "").lower()
    aggregator = host in {"myscheme.gov.in", "www.myscheme.gov.in", "india.gov.in", "www.india.gov.in"}
    date = doc.get("publication_date") or "0000-00-00"
    text_length = len(doc.get("cleaned_text", ""))
    return (aggregator, "".join(chr(255 - ord(c)) for c in date), -text_length, doc.get("document_id", ""))


def deduplicate_documents(documents: list[dict], threshold: float = 0.95) -> tuple[list[dict], list[dict]]:
    """Deterministically remove URL, byte, cleaned-text, and near duplicates."""
    ordered = sorted(documents, key=_source_rank)
    kept: list[dict] = []
    reports: list[dict] = []
    seen_url: dict[str, dict] = {}
    seen_raw: dict[str, dict] = {}
    seen_text: dict[str, dict] = {}
    shingles: dict[str, set] = {}

    def reject(doc: dict, retained: dict, method: str, score: float) -> None:
        reports.append({
            "rejected_document_id": doc["document_id"],
            "retained_document_id": retained["document_id"],
            "method": method,
            "similarity": round(score, 6),
            "rejected_url": doc.get("url"),
            "retained_url": retained.get("url"),
            "reason": f"deterministic {method} duplicate; preferred official/newer/richer source",
        })

    for doc in ordered:
        url_key = canonicalize_url(doc.get("final_url") or doc.get("url", ""))
        raw_key = doc.get("sha256", "")
        clean_key = text_sha256(doc.get("cleaned_text", ""))
        if url_key in seen_url:
            reject(doc, seen_url[url_key], "canonical_url", 1.0)
            continue
        if raw_key and raw_key in seen_raw:
            reject(doc, seen_raw[raw_key], "raw_sha256", 1.0)
            continue
        if clean_key in seen_text:
            reject(doc, seen_text[clean_key], "cleaned_text_sha256", 1.0)
            continue
        current = word_shingles(doc.get("cleaned_text", ""))
        duplicate = None
        duplicate_score = 0.0
        for retained in kept:
            score = jaccard_similarity(current, shingles[retained["document_id"]])
            if score >= threshold:
                duplicate, duplicate_score = retained, score
                break
        if duplicate:
            reject(doc, duplicate, "five_word_shingle_jaccard", duplicate_score)
            continue
        kept.append(doc)
        seen_url[url_key] = doc
        if raw_key:
            seen_raw[raw_key] = doc
        seen_text[clean_key] = doc
        shingles[doc["document_id"]] = current
    return sorted(kept, key=lambda d: d["document_id"]), sorted(reports, key=lambda r: r["rejected_document_id"])


def validate_corpus(documents: list[dict], chunks: list[dict], config: dict) -> None:
    """Enforce corpus-size, metadata, diversity, and lineage gates."""
    errors: list[str] = []
    min_docs, max_docs = config.get("min_documents", 100), config.get("max_documents", 150)
    min_chunks, max_chunks = config.get("min_chunks", 800), config.get("max_chunks", 1500)
    if not min_docs <= len(documents) <= max_docs:
        errors.append(f"documents={len(documents)} outside [{min_docs}, {max_docs}]")
    if not min_chunks <= len(chunks) <= max_chunks:
        errors.append(f"chunks={len(chunks)} outside [{min_chunks}, {max_chunks}]")
    required = {"document_id", "source", "ministry", "scheme_name", "publication_date", "url"}
    for doc in documents:
        missing = [key for key in required if key not in doc or (key != "publication_date" and not doc[key])]
        if missing:
            errors.append(f"{doc.get('document_id', '?')}: missing {missing}")
        if not is_authoritative_url(doc.get("url", ""), set(config.get("explicit_authority_hosts", []))):
            errors.append(f"{doc.get('document_id', '?')}: non-authoritative URL")
    for key in ("doc_id", "document_id"):
        values = [doc.get(key) for doc in documents]
        if len(values) != len(set(values)):
            errors.append(f"duplicate {key}")
    chunk_ids = [chunk.get("chunk_id") for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        errors.append("duplicate chunk_id")
    doc_ids = {doc["doc_id"] for doc in documents}
    for chunk in chunks:
        if chunk.get("doc_id") not in doc_ids:
            errors.append(f"orphan chunk {chunk.get('chunk_id')}")
        if not chunk.get("text", "").strip():
            errors.append(f"empty chunk {chunk.get('chunk_id')}")
        if chunk.get("word_count") != len(chunk.get("text", "").split()):
            errors.append(f"incorrect word_count {chunk.get('chunk_id')}")
    if len({doc.get("ministry") for doc in documents}) < config.get("min_ministries", 8):
        errors.append("insufficient ministry diversity")
    present_types = {doc.get("document_type") for doc in documents}
    missing_types = REQUIRED_DOCUMENT_TYPES - present_types
    if missing_types:
        errors.append(f"missing document types {sorted(missing_types)}")
    if errors:
        raise CorpusValidationError("; ".join(errors[:30]))


def build_statistics(
    documents: list[dict], chunks: list[dict], *, corpus_version: str = "v2",
    catalog_entries: int = 0, acquisition: list[dict] | None = None,
    duplicate_count: int = 0, graph_nodes: list[dict] | None = None,
    graph_edges: list[dict] | None = None,
) -> dict:
    """Build machine-readable corpus and graph statistics."""
    words = [int(chunk.get("word_count", 0)) for chunk in chunks]
    acquisition = acquisition or []
    graph_nodes = graph_nodes or []
    graph_edges = graph_edges or []
    entity_nodes = [n for n in graph_nodes if n.get("type") == "entity"]

    def distribution(key: str, items: list[dict]) -> dict[str, int]:
        counts = Counter(str(item.get(key) or "unknown") for item in items)
        return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))

    chunks_by_ministry = Counter()
    ministry_by_doc = {doc["doc_id"]: doc.get("ministry", "unknown") for doc in documents}
    for chunk in chunks:
        chunks_by_ministry[ministry_by_doc.get(chunk.get("doc_id"), "unknown")] += 1
    hosts = Counter((urlsplit(doc.get("url", "")).hostname or "unknown").lower() for doc in documents)
    return {
        "corpus_version": corpus_version,
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "catalog_entries": catalog_entries,
        "download_successes": sum(a.get("outcome") in {"downloaded", "reused"} for a in acquisition),
        "download_failures": sum(a.get("outcome") == "rejected" for a in acquisition),
        "documents_before_deduplication": len(documents) + duplicate_count,
        "duplicates_removed": duplicate_count,
        "accepted_documents": len(documents),
        "total_chunks": len(chunks),
        "total_words": sum(words),
        "average_chunk_size_words": round(statistics.mean(words), 2) if words else 0,
        "minimum_chunk_size_words": min(words, default=0),
        "maximum_chunk_size_words": max(words, default=0),
        "median_chunk_size_words": statistics.median(words) if words else 0,
        "unique_entities_extracted": len(entity_nodes),
        "entity_nodes": len(entity_nodes),
        "chunk_nodes": sum(n.get("type") == "chunk" for n in graph_nodes),
        "graph_nodes": len(graph_nodes),
        "graph_edges": len(graph_edges),
        "documents_by_ministry": distribution("ministry", documents),
        "chunks_by_ministry": dict(sorted(chunks_by_ministry.items(), key=lambda p: (-p[1], p[0]))),
        "documents_by_scheme": distribution("scheme_name", documents),
        "documents_by_document_type": distribution("document_type", documents),
        "documents_by_source_type": distribution("source_type", documents),
        "documents_with_publication_date": sum(doc.get("publication_date") is not None for doc in documents),
        "documents_without_publication_date": sum(doc.get("publication_date") is None for doc in documents),
        "authority_domain_distribution": dict(sorted(hosts.items(), key=lambda p: (-p[1], p[0]))),
    }


def write_statistics(stats: dict, json_path: str | Path, markdown_path: str | Path) -> None:
    json_path, markdown_path = Path(json_path), Path(markdown_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(stats, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    lines = [
        "# Corpus Statistics v2", "",
        f"- Documents: {stats['accepted_documents']}",
        f"- Chunks: {stats['total_chunks']}",
        f"- Average chunk size: {stats['average_chunk_size_words']} words",
        f"- Unique entities: {stats['unique_entities_extracted']}",
        f"- Graph nodes: {stats['graph_nodes']}",
        f"- Graph edges: {stats['graph_edges']}", "", "## Documents by ministry", "",
        "| Ministry | Documents |", "|---|---:|",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in stats["documents_by_ministry"].items())
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
