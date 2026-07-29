#!/usr/bin/env python3
"""Build a byte-identical consolidated view of frozen V2 pilot evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "runs/CANONICAL_EVIDENCE.json"
OUTPUT_ROOT = ROOT / "runs/canonical_v2_pilot"


def sha256(path: Path) -> str:
    """Return lowercase SHA-256 for one file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    """Load a JSON object or fail with an actionable error."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON object: {path.relative_to(ROOT)}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path.relative_to(ROOT)}")
    return value


def canonical_path(relative: str) -> Path:
    """Resolve one repository-relative path and reject traversal."""

    if not relative or Path(relative).is_absolute():
        raise ValueError(f"path must be non-empty and relative: {relative!r}")
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {relative}") from exc
    return path


def atomic_copy(source: Path, destination: Path, *, overwrite: bool) -> None:
    """Copy exact bytes atomically, preserving an equal existing destination."""

    payload = source.read_bytes()
    if destination.exists():
        if destination.read_bytes() == payload:
            return
        if not overwrite:
            raise FileExistsError(
                f"canonical view collision: {destination.relative_to(ROOT)}; use --overwrite"
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def stable_json_bytes(value: Any) -> bytes:
    """Serialize deterministic UTF-8 JSON."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write_json(path: Path, value: Any, *, overwrite: bool) -> None:
    """Write deterministic JSON atomically."""

    payload = stable_json_bytes(value)
    if path.exists():
        if path.read_bytes() == payload:
            return
        if not overwrite:
            raise FileExistsError(f"manifest collision: {path.relative_to(ROOT)}; use --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def add_copy(
    copies: list[dict[str, str]],
    source_relative: str,
    destination_relative: str,
    *,
    expected_sha256: str | None,
    overwrite: bool,
) -> None:
    """Verify source, copy it, then record source/destination lineage."""

    source = canonical_path(source_relative)
    destination = canonical_path(destination_relative)
    if not source.is_file():
        raise FileNotFoundError(f"missing canonical source: {source_relative}")
    digest = sha256(source)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"source SHA-256 mismatch: {source_relative}")
    atomic_copy(source, destination, overwrite=overwrite)
    if sha256(destination) != digest:
        raise ValueError(f"copied SHA-256 mismatch: {destination_relative}")
    copies.append(
        {
            "destination_path": destination_relative,
            "sha256": digest,
            "source_path": source_relative,
        }
    )


def build(*, overwrite: bool) -> dict[str, Any]:
    """Materialize consolidated rankings, metrics, statistics, and benchmark inputs."""

    registry = load_object(REGISTRY_PATH)
    systems = registry.get("systems")
    if not isinstance(systems, dict) or len(systems) != 5:
        raise ValueError("canonical registry must contain exactly five systems")

    copies: list[dict[str, str]] = []
    for system, record in sorted(systems.items()):
        add_copy(
            copies,
            record["ranking_path"],
            f"runs/canonical_v2_pilot/retrieval/{system}_top50.jsonl",
            expected_sha256=record["ranking_sha256"],
            overwrite=overwrite,
        )

    benchmark = registry["benchmark"]
    add_copy(
        copies,
        benchmark["questions_path"],
        "runs/canonical_v2_pilot/benchmark/questions_r5.jsonl",
        expected_sha256=benchmark["questions_sha256"],
        overwrite=overwrite,
    )
    add_copy(
        copies,
        benchmark["qrels_path"],
        "runs/canonical_v2_pilot/benchmark/final_pooled_qrels.tsv",
        expected_sha256=benchmark["qrels_sha256"],
        overwrite=overwrite,
    )

    supplement_path = ROOT / "runs/v2/phase6_seed42_final/metrics/supplement_manifest.json"
    supplement = load_object(supplement_path)
    metric_hashes = supplement.get("outputs")
    if not isinstance(metric_hashes, dict) or not metric_hashes:
        raise ValueError("Phase 6 supplement manifest has no metric outputs")
    for source_relative, expected in sorted(metric_hashes.items()):
        name = Path(source_relative).name
        add_copy(
            copies,
            source_relative,
            f"runs/canonical_v2_pilot/metrics/{name}",
            expected_sha256=expected,
            overwrite=overwrite,
        )

    statistics_manifest_path = ROOT / "runs/v2/phase6_seed42_final/statistics/manifest.json"
    statistics_manifest = load_object(statistics_manifest_path)
    statistic_hashes = statistics_manifest.get("outputs")
    if not isinstance(statistic_hashes, dict) or not statistic_hashes:
        raise ValueError("Phase 6 statistics manifest has no outputs")
    for source_relative, expected in sorted(statistic_hashes.items()):
        name = Path(source_relative).name
        add_copy(
            copies,
            source_relative,
            f"runs/canonical_v2_pilot/statistics/{name}",
            expected_sha256=expected,
            overwrite=overwrite,
        )

    for source, destination in (
        (
            "runs/v2/phase6_seed42_final/metrics/supplement_manifest.json",
            "runs/canonical_v2_pilot/provenance/phase6_metrics_manifest.json",
        ),
        (
            "runs/v2/phase6_seed42_final/statistics/manifest.json",
            "runs/canonical_v2_pilot/provenance/phase6_statistics_manifest.json",
        ),
        ("runs/CANONICAL_EVIDENCE.json", "runs/canonical_v2_pilot/provenance/source_registry.json"),
        ("src/retrievers/SYSTEMS.json", "runs/canonical_v2_pilot/provenance/system_code_registry.json"),
    ):
        add_copy(copies, source, destination, expected_sha256=None, overwrite=overwrite)

    manifest = {
        "artifact_count": len(copies),
        "benchmark_scope": registry["benchmark"]["scope"],
        "copies": sorted(copies, key=lambda row: row["destination_path"]),
        "historical_sources_modified": False,
        "schema_version": 1,
        "status": "canonical_v2_pilot_consolidated_view",
        "system_count": 5,
    }
    atomic_write_json(OUTPUT_ROOT / "manifest.json", manifest, overwrite=overwrite)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="replace drifted view files")
    args = parser.parse_args()
    manifest = build(overwrite=args.overwrite)
    print(json.dumps({"artifact_count": manifest["artifact_count"], "status": manifest["status"]}))


if __name__ == "__main__":
    main()
