"""
Corpus Versioner — Ingestion Layer
=====================================
Research purpose
    Reproducibility demands that every experiment run can trace back to an
    exact corpus snapshot. The versioner creates an immutable manifest
    (JSONL) and a corpus profile (JSON) so the benchmark's data provenance
    is fully auditable.

Design choice
    Content-addressed versioning using SHA-256 of each document. The manifest
    can be compared across corpus versions to detect additions, removals, and
    modifications.

Alternative approaches
    DVC (Data Version Control) provides richer lineage but adds tool
    dependency overhead not justified for a dissertation-scale corpus.

Expected strengths
    Self-contained; the manifest and profile JSONs are human-readable and
    can be committed to version control alongside code.

Expected weaknesses
    Does not track schema changes to the RawDocument model itself; a schema
    migration story is postponed to the final semester.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CorpusVersioner:
    """
    Writes and reads corpus manifests and profiles.

    Parameters
    ----------
    output_dir : str | Path
        Directory where manifest.jsonl and corpus_profile.json will be written.
    version : str
        Version label, e.g. "v1".
    """

    def __init__(self, output_dir: str | Path, version: str = "v1") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.version = version

    def save_manifest(self, documents: list[dict]) -> Path:
        """Write one JSONL line per document."""
        manifest_path = self.output_dir / f"manifest_{self.version}.jsonl"
        with manifest_path.open("w", encoding="utf-8") as fh:
            for doc in documents:
                fh.write(json.dumps(doc) + "\n")
        logger.info("Manifest written: %s (%d docs)", manifest_path, len(documents))
        return manifest_path

    def save_corpus_profile(self, documents: list[dict]) -> Path:
        """Write aggregate corpus statistics."""
        total_tokens = sum(len(d.get("raw_text", "").split()) for d in documents)
        avg_length = total_tokens / max(len(documents), 1)
        source_types: dict[str, int] = {}
        domain_tags: dict[str, int] = {}

        for doc in documents:
            st = doc.get("source_type", "unknown")
            source_types[st] = source_types.get(st, 0) + 1
            dt = doc.get("domain_tag", "general")
            domain_tags[dt] = domain_tags.get(dt, 0) + 1

        profile: dict[str, Any] = {
            "corpus_version": self.version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "num_documents": len(documents),
            "total_tokens_approx": total_tokens,
            "avg_doc_length_tokens": round(avg_length, 1),
            "source_type_distribution": source_types,
            "domain_tag_distribution": domain_tags,
        }

        profile_path = self.output_dir / f"corpus_profile_{self.version}.json"
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        logger.info("Corpus profile written: %s", profile_path)
        return profile_path

    def load_manifest(self, version: str | None = None) -> list[dict]:
        """Load a manifest from disk."""
        v = version or self.version
        manifest_path = self.output_dir / f"manifest_{v}.jsonl"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        docs = []
        with manifest_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    docs.append(json.loads(line))
        return docs
