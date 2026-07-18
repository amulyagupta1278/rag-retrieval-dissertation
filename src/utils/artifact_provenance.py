"""Deterministic fingerprints for corpus-derived experiment artifacts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Iterable


def sha256_file(path: str | Path) -> str:
    """Return streaming SHA-256 for *path*."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_json_hash(value: object) -> str:
    """Hash JSON-compatible data using canonical serialization."""
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def package_versions(names: Iterable[str]) -> dict[str, str | None]:
    """Resolve installed distribution versions without importing packages."""
    output = {}
    for name in names:
        try:
            output[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            output[name] = None
    return output


def validate_config_hash(config: dict, *, required: bool = False) -> None:
    """Reject modified configuration snapshots while allowing historical artifacts."""
    expected = config.get("configuration_hash")
    if not expected:
        if required:
            raise RuntimeError("Index configuration_hash is missing")
        return
    payload = {key: value for key, value in config.items() if key != "configuration_hash"}
    actual = stable_json_hash(payload)
    if expected != actual:
        raise RuntimeError(
            f"Index configuration hash mismatch: recorded={expected} actual={actual}"
        )


def ordered_chunk_ids_sha256(chunk_ids: Iterable[str]) -> str:
    """Fingerprint exact vector/index row order."""
    return stable_json_hash(list(chunk_ids))


def chunk_provenance(
    chunks: list[dict], chunks_path: str | Path | None = None,
) -> dict[str, str | int | None]:
    """Return file, semantic-content, and row-order fingerprints."""
    semantic_rows = [
        {
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk.get("doc_id", ""),
            "text": chunk.get("text", ""),
        }
        for chunk in chunks
    ]
    path = Path(chunks_path) if chunks_path else None
    return {
        "num_chunks": len(chunks),
        "chunks_file_sha256": sha256_file(path) if path and path.is_file() else None,
        "corpus_content_sha256": stable_json_hash(semantic_rows),
        "ordered_chunk_ids_sha256": ordered_chunk_ids_sha256(
            row["chunk_id"] for row in semantic_rows
        ),
    }


def validate_chunk_provenance(
    recorded: dict | None,
    chunks: list[dict],
    chunks_path: str | Path | None = None,
    *,
    require_complete: bool = False,
) -> dict[str, str | int | None]:
    """Reject stale/same-cardinality indexes whose parent corpus differs."""
    actual = chunk_provenance(chunks, chunks_path)
    recorded = recorded or {}
    required = (
        "num_chunks", "corpus_content_sha256", "ordered_chunk_ids_sha256",
    )
    if require_complete:
        missing = [key for key in required if recorded.get(key) in (None, "")]
        if chunks_path and recorded.get("chunks_file_sha256") in (None, ""):
            missing.append("chunks_file_sha256")
        if missing:
            raise RuntimeError(
                "Index provenance missing required fields: " + ", ".join(missing)
            )
    for key in (*required, "chunks_file_sha256"):
        expected = recorded.get(key)
        observed = actual.get(key)
        if expected not in (None, "") and observed not in (None, "") and expected != observed:
            raise RuntimeError(
                f"Index provenance mismatch for {key}: index={expected} corpus={observed}"
            )
    return actual
