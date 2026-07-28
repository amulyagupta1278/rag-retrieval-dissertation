#!/usr/bin/env python3
"""Create or verify complete SHA-256 manifests for versioned releases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXCLUDED_NAMES = {"SHA256SUMS", "BASELINE_SHA256SUMS", "release_manifest.jsonl"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_type(path: Path) -> str:
    parts = set(path.parts)
    if "chunks" in parts:
        return "chunks"
    if "queries" in parts:
        return "queries"
    if "qrels" in parts:
        return "qrels"
    if "indexes" in parts or "bm25" in parts or "faiss" in parts or "entity_graph" in parts:
        return "index"
    if "retrieval" in parts:
        return "retrieval_run"
    if "metrics" in parts:
        return "metrics"
    if "reports" in parts:
        return "report"
    if "metadata" in parts:
        return "metadata"
    return "artifact"


def _relative(path: Path, base_dir: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"Artifact {path} is outside manifest base {base_dir}") from exc


def configuration_hash(paths: list[Path], base_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: _relative(item, base_dir)):
        digest.update(_relative(path, base_dir).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def collect_files(roots: list[Path], outputs: set[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.name in EXCLUDED_NAMES or path in outputs or path.name == ".DS_Store":
                continue
            files.append(path)
    return sorted(set(files), key=lambda path: str(path))


def write_manifest(args: argparse.Namespace) -> None:
    base_dir = Path(args.base_dir)
    roots = [Path(value) for value in args.include_root]
    manifest_path = Path(args.manifest)
    sums_path = Path(args.sums)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    sums_path.parent.mkdir(parents=True, exist_ok=True)
    outputs = {manifest_path.resolve(), sums_path.resolve()}
    files = collect_files(roots, outputs)
    config_digest = configuration_hash([Path(value) for value in args.config], base_dir) if args.config else None
    with manifest_path.open("w", encoding="utf-8") as manifest, sums_path.open("w", encoding="utf-8") as sums:
        for path in files:
            digest = sha256_file(path)
            relative_path = _relative(path, base_dir)
            record = {
                "relative_path": relative_path,
                "sha256": digest,
                "byte_size": path.stat().st_size,
                "artifact_type": artifact_type(path),
                "corpus_version": args.version,
                "query_count": args.query_count,
                "chunk_count": args.chunk_count,
                "creation_command": args.creation_command,
                "configuration_hash": config_digest,
            }
            manifest.write(json.dumps(record, sort_keys=True) + "\n")
            sums.write(f"{digest}  {relative_path}\n")
    print(json.dumps({"version": args.version, "files": len(files), "manifest": str(manifest_path)}, indent=2))


def verify_manifest(args: argparse.Namespace) -> None:
    base_dir = Path(args.base_dir)
    manifest_path = Path(args.manifest)
    records = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = {record["relative_path"] for record in records}
    roots = [Path(value) for value in args.include_root]
    outputs = {manifest_path.resolve(), Path(args.sums).resolve()}
    actual = {_relative(path, base_dir) for path in collect_files(roots, outputs)}
    errors: list[str] = []
    for record in records:
        path = base_dir / record["relative_path"]
        if not path.exists():
            errors.append(f"missing: {path}")
        elif path.stat().st_size != record["byte_size"]:
            errors.append(f"size mismatch: {path}")
        elif sha256_file(path) != record["sha256"]:
            errors.append(f"checksum mismatch: {path}")
    for path in sorted(actual - expected):
        errors.append(f"unexpected: {path}")
    for path in sorted(expected - actual):
        if (base_dir / path).exists():
            errors.append(f"untracked: {path}")
    if errors:
        raise SystemExit("Manifest verification failed:\n" + "\n".join(errors))
    print(json.dumps({"verified": len(records), "unexpected": 0, "missing": 0}, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-root", action="append", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sums", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--chunk-count", type=int, default=0)
    parser.add_argument("--query-count", type=int, default=0)
    parser.add_argument("--creation-command", default="unknown")
    parser.add_argument("--config", action="append", default=[])
    parser.add_argument("--verify", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    parsed = parse_args()
    verify_manifest(parsed) if parsed.verify else write_manifest(parsed)
