#!/usr/bin/env python3
"""Build, verify, and atomically publish a complete immutable corpus release.

The stages deliberately communicate only through explicit versioned paths.
No stage reads a canonical index, benchmark, or run by accident.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import pickle
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.ingestion.corpus_quality import validate_clean_projection
from src.utils.io_utils import load_jsonl, load_yaml


STAGES = ("corpus", "indexes", "benchmark", "evaluate", "statistics", "verify", "all")
DETERMINISTIC_PATHS = (
    "data/processed/documents.jsonl",
    "data/chunks/chunks.jsonl",
    "data/metadata/corpus_manifest.json",
    "data/metadata/sources.csv",
    "data/raw/manifest_{version}.jsonl",
    "data/raw/corpus_profile_{version}.json",
    "data/queries/qa_dataset_{version}.jsonl",
    "data/queries/query_categories_{version}.json",
    "data/qrels/qrels_{version}.tsv",
    "data/qrels/evidence_map_{version}.json",
    "data/metadata/qa_validation_stats_{version}.json",
    "data/metadata/cross_scheme_audit_{version}.jsonl",
    "indexes/bm25/bm25_index.pkl",
    "indexes/faiss/faiss.index",
    "indexes/faiss/chunk_ids.json",
    "indexes/faiss/config.json",
    "indexes/graphrag/graph.gpickle",
    "indexes/graphrag/graph.json",
    "indexes/graphrag/chunk_lookup.json",
    "indexes/graphrag/nodes.jsonl",
    "indexes/graphrag/edges.jsonl",
    "data/metadata/corpus_statistics_{version}.json",
    "data/metadata/corpus_statistics_{version}.md",
)


def _run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    env = {
        **os.environ,
        "PYTHONHASHSEED": "0",
        "TOKENIZERS_PARALLELISM": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _paths(work: Path, version: str) -> dict[str, Path]:
    data = work / "data"
    indexes = work / "indexes"
    return {
        "data": data,
        "chunks": data / "chunks" / "chunks.jsonl",
        "documents": data / "processed" / "documents.jsonl",
        "qa": data / "queries" / f"qa_dataset_{version}.jsonl",
        "qrels": data / "qrels" / f"qrels_{version}.tsv",
        "categories": data / "queries" / f"query_categories_{version}.json",
        "bm25": indexes / "bm25" / "bm25_index.pkl",
        "faiss": indexes / "faiss",
        "graph": indexes / "graphrag",
        "runs": work / "runs",
    }


def _copy_release_inputs(args: argparse.Namespace, work: Path) -> None:
    shutil.copytree(ROOT / "configs", work / "configs", dirs_exist_ok=True)
    shutil.copy2(ROOT / args.benchmark_seed, work / "configs" / "benchmark_seed.jsonl")
    sources = work / "data" / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "data/sources/source_catalog_v2.jsonl", sources / "source_catalog_v2.jsonl")
    metadata = work / "data" / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "data/metadata/acquisition_audit_v2.jsonl", metadata / "acquisition_audit_v2.jsonl")
    raw = work / "data" / "raw" / "snapshot_v2"
    raw.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "data/raw/snapshot_v2/metadata.jsonl", raw / "metadata.jsonl")


def _capture_environment_and_code(work: Path) -> None:
    manifests = work / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    packages = {}
    for name in (
        "numpy", "rank-bm25", "sentence-transformers", "faiss-cpu", "spacy",
        "networkx", "PyMuPDF", "python-docx", "beautifulsoup4", "PyYAML", "torch",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    environment = {
        "python": sys.version.split()[0], "packages": dict(sorted(packages.items())),
        "embedding_execution_device": "runtime-selected; index bytes are checksum-verified",
    }
    (manifests / "environment.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_files = []
    for directory in ("src", "experiments", "scripts", "tests"):
        source_files.extend((ROOT / directory).rglob("*.py"))
    source_files.extend(ROOT / name for name in ("pyproject.toml", "requirements.txt", "Makefile"))
    with (manifests / "source_code_manifest.jsonl").open("w", encoding="utf-8") as handle:
        for path in sorted(set(source_files)):
            handle.write(json.dumps({
                "relative_path": path.relative_to(ROOT).as_posix(),
                "sha256": _sha256(path), "byte_size": path.stat().st_size,
            }, sort_keys=True) + "\n")


def build_corpus(args: argparse.Namespace, work: Path) -> None:
    if args.clean_work and work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    _copy_release_inputs(args, work)
    _capture_environment_and_code(work)
    _run([
        sys.executable, "experiments/build_dataset.py",
        "--version", args.version,
        "--output-root", str(work / "data"),
        "--corpus-config", str(work / "configs/corpus.yaml"),
        "--chunking-config", str(work / "configs/chunking.yaml"),
    ])


def build_indexes(args: argparse.Namespace, work: Path) -> None:
    paths = _paths(work, args.version)
    if not paths["chunks"].exists():
        raise RuntimeError("Corpus stage has not produced chunks")
    _run([
        sys.executable, "experiments/run_bm25.py", "--build-only", "--rebuild",
        "--chunks", str(paths["chunks"]), "--index-path", str(paths["bm25"]),
        "--config", str(work / "configs/retrieval.yaml"),
    ])
    _run([
        sys.executable, "experiments/run_faiss.py", "--build-only", "--rebuild",
        "--chunks", str(paths["chunks"]), "--index-dir", str(paths["faiss"]),
        "--config", str(work / "configs/retrieval.yaml"),
    ])
    _run([
        sys.executable, "experiments/run_graphrag.py", "--build-only", "--rebuild",
        "--chunks", str(paths["chunks"]), "--graph-dir", str(paths["graph"]),
        "--config", str(work / "configs/retrieval.yaml"),
    ])


def build_benchmark(args: argparse.Namespace, work: Path) -> None:
    paths = _paths(work, args.version)
    if not (paths["chunks"].exists() and (paths["graph"] / "graph.gpickle").exists()):
        raise RuntimeError("Corpus and graph stages must precede benchmark generation")
    _run([
        sys.executable, "scripts/regenerate_qa.py",
        "--version", args.version,
        "--chunks", str(paths["chunks"]),
        "--base-qa", str(work / "configs/benchmark_seed.jsonl"),
        "--graph", str(paths["graph"] / "graph.gpickle"),
        "--output-dir", str(work / "data"),
    ])


def evaluate(args: argparse.Namespace, work: Path) -> None:
    paths = _paths(work, args.version)
    common = [
        "--top-k", "10", "--chunks", str(paths["chunks"]),
        "--qa-dataset", str(paths["qa"]), "--qrels", str(paths["qrels"]),
        "--query-categories", str(paths["categories"]),
        "--config", str(work / "configs/retrieval.yaml"),
        "--output-root", str(paths["runs"]),
    ]
    _run([sys.executable, "experiments/run_bm25.py", *common, "--index-path", str(paths["bm25"])])
    _run([sys.executable, "experiments/run_faiss.py", *common, "--index-dir", str(paths["faiss"])])
    _run([sys.executable, "experiments/run_graphrag.py", *common, "--graph-dir", str(paths["graph"])])
    _run([
        sys.executable, "scripts/report_phase0_metrics.py",
        "--qa", str(paths["qa"]), "--qrels", str(paths["qrels"]),
        "--chunks", str(paths["chunks"]), "--runs-root", str(paths["runs"]),
        "--output-root", str(paths["runs"]),
    ])
    _run([
        sys.executable, "experiments/compare_retrievers.py",
        "--run-dir", str(paths["runs"] / "retrieval"),
        "--qrels", str(paths["qrels"]),
        "--query-categories", str(paths["categories"]),
        "--output-dir", str(paths["runs"] / "metrics"),
        "--reports-dir", str(paths["runs"] / "reports"),
    ])


def statistics(args: argparse.Namespace, work: Path) -> None:
    paths = _paths(work, args.version)
    _run([
        sys.executable, "scripts/generate_corpus_statistics.py",
        "--version", args.version,
        "--documents", str(paths["documents"]), "--chunks", str(paths["chunks"]),
        "--catalog", str(work / "data/sources/source_catalog_v2.jsonl"),
        "--acquisition", str(work / "data/metadata/acquisition_audit_v2.jsonl"),
        "--deduplication", str(work / f"data/metadata/deduplication_report_{args.version}.jsonl"),
        "--nodes", str(paths["graph"] / "nodes.jsonl"),
        "--edges", str(paths["graph"] / "edges.jsonl"),
        "--output-dir", str(work / "data/metadata"),
    ])


def validate_benchmark_cardinality(
    qa: list[dict], qrels: dict[str, dict[str, int]], *, expected_queries: int, expected_judgments: int,
) -> int:
    """Fail closed on the historical pre-cross 120-qrel benchmark."""
    judgments = sum(len(value) for value in qrels.values())
    if len(qa) != expected_queries or len(qrels) != expected_queries or judgments != expected_judgments:
        raise RuntimeError(
            f"benchmark cardinality mismatch: queries={len(qa)} qrel_queries={len(qrels)} "
            f"judgments={judgments}; expected={expected_queries}/{expected_queries}/{expected_judgments}"
        )
    return judgments


def validate_release(args: argparse.Namespace, work: Path, require_runs: bool = True) -> dict:
    paths = _paths(work, args.version)
    documents = load_jsonl(paths["documents"])
    chunks = load_jsonl(paths["chunks"])
    qa = load_jsonl(paths["qa"])
    qrels = QRelsBuilder.load_qrels_tsv(paths["qrels"])
    judgments = validate_benchmark_cardinality(
        qa, qrels, expected_queries=args.expected_queries, expected_judgments=args.expected_qrels,
    )
    errors: list[str] = []
    expected = (args.expected_documents, args.expected_chunks, args.expected_queries, args.expected_qrels)
    actual = (len(documents), len(chunks), len(qa), judgments)
    if actual != expected:
        errors.append(f"cardinality mismatch: actual={actual} expected={expected}")
    if load_yaml(work / "configs/corpus.yaml").get("corpus", {}).get("version") != args.version:
        errors.append("corpus configuration version does not match release label")
    try:
        validate_clean_projection(documents, chunks)
    except Exception as exc:  # aggregate gate failures into one report
        errors.append(f"clean projection validation failed: {exc}")
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    chunk_set = set(chunk_ids)
    if len(chunk_ids) != len(chunk_set):
        errors.append("duplicate chunk IDs")
    gold_ids = {chunk_id for value in qrels.values() for chunk_id in value}
    if gold_ids - chunk_set:
        errors.append(f"qrels contain {len(gold_ids - chunk_set)} unknown chunk IDs")
    category_counts = Counter(item.get("category") for item in qa)
    if set(category_counts.values()) != {20} or len(category_counts) != 5:
        errors.append(f"unbalanced query categories: {dict(category_counts)}")

    with paths["bm25"].open("rb") as handle:
        bm25_payload = pickle.load(handle)
    bm25_ids = [item["chunk_id"] for item in bm25_payload["meta"]]
    if bm25_ids != chunk_ids:
        errors.append("BM25 chunk-ID order differs from corpus")
    try:
        import faiss
        faiss_index = faiss.read_index(str(paths["faiss"] / "faiss.index"))
        faiss_ids = json.loads((paths["faiss"] / "chunk_ids.json").read_text(encoding="utf-8"))
        if faiss_index.ntotal != len(chunks) or faiss_ids != chunk_ids:
            errors.append("FAISS cardinality or chunk-ID order mismatch")
    except Exception as exc:
        errors.append(f"FAISS validation failed: {exc}")
    with (paths["graph"] / "graph.gpickle").open("rb") as handle:
        graph_payload = pickle.load(handle)
    if set(graph_payload.get("chunk_meta", {})) != chunk_set:
        errors.append("entity graph chunk lookup differs from corpus")
    graph_json = json.loads((paths["graph"] / "graph.json").read_text(encoding="utf-8"))
    if len(graph_json["nodes"]) != graph_payload["graph"].number_of_nodes():
        errors.append("entity graph portable-node count mismatch")
    stats = json.loads(
        (work / f"data/metadata/corpus_statistics_{args.version}.json").read_text(encoding="utf-8")
    )
    if stats.get("corpus_version") != args.version or stats.get("total_chunks") != len(chunks):
        errors.append("corpus statistics do not match release")

    if require_runs:
        qa_ids = {item["question_id"] for item in qa}
        for system in ("bm25", "faiss", "graphrag"):
            run_path = paths["runs"] / "retrieval" / f"{system}_run.jsonl"
            runs = load_jsonl(run_path)
            run_ids = {run["query_id"] for run in runs}
            retrieved = {result["chunk_id"] for run in runs for result in run.get("results", [])}
            if len(runs) != len(qa) or run_ids != qa_ids:
                errors.append(f"{system} run query set mismatch")
            if retrieved - chunk_set:
                errors.append(f"{system} run contains unknown chunks")
    if errors:
        raise RuntimeError("Release gate failed:\n- " + "\n- ".join(errors))
    return {
        "corpus_version": args.version,
        "documents": len(documents), "chunks": len(chunks),
        "queries": len(qa), "qrels": judgments,
        "categories": dict(sorted(category_counts.items())),
        "graph_nodes": graph_payload["graph"].number_of_nodes(),
        "graph_edges": graph_payload["graph"].number_of_edges(),
    }


def _write_manifest(args: argparse.Namespace, work: Path, summary: dict) -> None:
    manifests = work / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    release_record = {
        **summary,
        "human_graph_name": "Entity-Co-occurrence Graph Retrieval",
        "legacy_graph_key": "graphrag",
        "creation_command": f"python scripts/release_pipeline.py --version {args.version} --stage all",
        "source_catalog_sha256": _sha256(work / "data/sources/source_catalog_v2.jsonl"),
        "corpus_manifest_sha256": _sha256(work / "data/metadata/corpus_manifest.json"),
        "chunks_sha256": _sha256(work / "data/chunks/chunks.jsonl"),
        "qa_sha256": _sha256(work / f"data/queries/qa_dataset_{args.version}.jsonl"),
        "qrels_sha256": _sha256(work / f"data/qrels/qrels_{args.version}.tsv"),
    }
    (manifests / "release.json").write_text(
        json.dumps(release_record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    command = [
        sys.executable, "scripts/release_manifest.py",
        "--base-dir", str(work),
        "--manifest", str(manifests / "release_manifest.jsonl"),
        "--sums", str(manifests / "SHA256SUMS"),
        "--version", args.version,
        "--chunk-count", str(summary["chunks"]),
        "--query-count", str(summary["queries"]),
        "--creation-command", release_record["creation_command"],
    ]
    for name in ("data", "indexes", "runs", "reports", "configs", "manifests"):
        path = work / name
        if path.exists():
            command += ["--include-root", str(path)]
    for name in ("corpus.yaml", "chunking.yaml", "retrieval.yaml", "benchmark_seed.jsonl"):
        command += ["--config", str(work / "configs" / name)]
    _run(command)
    _run([*command, "--verify"])


def _determinism_check(args: argparse.Namespace, work: Path) -> None:
    shadow = work.parent / f".determinism-{args.version}-{uuid.uuid4().hex}"
    shadow_args = argparse.Namespace(**vars(args))
    shadow_args.clean_work = True
    try:
        build_corpus(shadow_args, shadow)
        build_indexes(shadow_args, shadow)
        build_benchmark(shadow_args, shadow)
        statistics(shadow_args, shadow)
        validate_release(shadow_args, shadow, require_runs=False)
        mismatches = []
        for template in DETERMINISTIC_PATHS:
            relative = Path(template.format(version=args.version))
            first, second = work / relative, shadow / relative
            if not first.exists() or not second.exists() or _sha256(first) != _sha256(second):
                mismatches.append(str(relative))
        if mismatches:
            raise RuntimeError("Non-deterministic release artifacts:\n- " + "\n- ".join(mismatches))
        print(f"Determinism gate passed: {len(DETERMINISTIC_PATHS)} artifacts")
    finally:
        shutil.rmtree(shadow, ignore_errors=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".release-new")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def _publish_canonical(release: Path, version: str) -> None:
    # First mirror every released data/run artifact to its compatibility path.
    # Per-file replace keeps readers from observing partially written files.
    for family in ("data", "runs"):
        root = release / family
        for source in root.rglob("*"):
            if source.is_file():
                _atomic_copy(source, ROOT / family / source.relative_to(root))

    # Versioned benchmark artifacts also populate the legacy canonical names.
    pairs = [
        (f"data/queries/qa_dataset_{version}.jsonl", "data/queries/qa_dataset.jsonl"),
        (f"data/queries/query_categories_{version}.json", "data/queries/query_categories.json"),
        (f"data/qrels/qrels_{version}.tsv", "data/qrels/qrels.tsv"),
        (f"data/qrels/evidence_map_{version}.json", "data/qrels/evidence_map.json"),
    ]
    for source, destination in pairs:
        _atomic_copy(release / source, ROOT / destination)
    for family in ("bm25", "faiss", "graphrag"):
        for source in (release / "indexes" / family).iterdir():
            if source.is_file():
                _atomic_copy(source, ROOT / "indexes" / family / source.name)


def publish(args: argparse.Namespace, work: Path, summary: dict) -> Path:
    release = ROOT / args.release_root / args.version
    if release.exists() and not args.replace:
        raise FileExistsError(f"Release exists: {release}; pass --replace after review")
    backup = release.with_name(release.name + ".previous")
    shutil.rmtree(backup, ignore_errors=True)
    if release.exists():
        os.replace(release, backup)
    try:
        os.replace(work, release)
    except Exception:
        if backup.exists() and not release.exists():
            os.replace(backup, release)
        raise
    shutil.rmtree(backup, ignore_errors=True)

    current = release.parent / "CURRENT"
    temporary = release.parent / f".CURRENT-{uuid.uuid4().hex}"
    temporary.symlink_to(args.version)
    os.replace(temporary, current)
    if args.publish_canonical:
        _publish_canonical(release, args.version)
    print(json.dumps({"published": str(release), **summary}, indent=2))
    return release


def verify_and_publish(args: argparse.Namespace, work: Path) -> None:
    summary = validate_release(args, work, require_runs=True)
    if args.verify_determinism:
        _determinism_check(args, work)
    _write_manifest(args, work, summary)
    publish(args, work, summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v3_clean")
    parser.add_argument("--stage", choices=STAGES, default="all")
    parser.add_argument("--release-root", default="releases")
    parser.add_argument("--work-dir", default=None)
    parser.add_argument("--benchmark-seed", default="data/queries/qa_dataset_v3_clean.jsonl")
    parser.add_argument("--expected-documents", type=int, default=130)
    parser.add_argument("--expected-chunks", type=int, default=856)
    parser.add_argument("--expected-queries", type=int, default=100)
    parser.add_argument("--expected-qrels", type=int, default=140)
    parser.add_argument("--clean-work", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--publish-canonical", action="store_true")
    parser.add_argument("--verify-determinism", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    work = Path(args.work_dir) if args.work_dir else ROOT / args.release_root / f".work-{args.version}"
    if args.stage == "all":
        args.clean_work = True
        build_corpus(args, work)
        build_indexes(args, work)
        build_benchmark(args, work)
        evaluate(args, work)
        statistics(args, work)
        verify_and_publish(args, work)
        return
    actions = {
        "corpus": build_corpus,
        "indexes": build_indexes,
        "benchmark": build_benchmark,
        "evaluate": evaluate,
        "statistics": statistics,
        "verify": verify_and_publish,
    }
    actions[args.stage](args, work)


if __name__ == "__main__":
    main()
