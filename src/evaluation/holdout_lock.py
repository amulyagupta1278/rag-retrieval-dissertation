"""Hash lock for preventing system changes after holdout visibility."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

TRACKED_SUFFIXES = {".py", ".yaml", ".yml", ".json"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _files(base: Path, roots: list[Path]) -> list[Path]:
    output = []
    for root in roots:
        path = root if root.is_absolute() else base / root
        if path.is_file():
            output.append(path)
        elif path.is_dir():
            output.extend(
                item for item in path.rglob("*")
                if item.is_file() and item.suffix in TRACKED_SUFFIXES and "__pycache__" not in item.parts
            )
        else:
            raise FileNotFoundError(path)
    return sorted(set(output), key=lambda path: path.resolve().relative_to(base.resolve()).as_posix())


def create_lock(base: str | Path, roots: list[str | Path], selection_files: list[str | Path], output: str | Path) -> dict:
    base_path = Path(base).resolve()
    root_paths = [Path(root) for root in roots]
    source_files = _files(base_path, root_paths)
    selections = [Path(path) if Path(path).is_absolute() else base_path / path for path in selection_files]
    records = [
        {
            "relative_path": path.resolve().relative_to(base_path).as_posix(),
            "sha256": _sha256(path), "byte_size": path.stat().st_size,
        }
        for path in source_files + selections
    ]
    records.sort(key=lambda record: record["relative_path"])
    digest = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    lock = {
        "schema_version": 1, "status": "configuration_frozen_before_holdout",
        "lock_id": digest, "roots": [str(root) for root in roots],
        "selection_files": [path.resolve().relative_to(base_path).as_posix() for path in selections],
        "files": records,
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lock


def verify_lock(lock_path: str | Path, base: str | Path = ".") -> dict:
    base_path = Path(base).resolve()
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    errors = []
    expected = {record["relative_path"] for record in lock["files"]}
    for record in lock["files"]:
        path = base_path / record["relative_path"]
        if not path.exists():
            errors.append(f"missing: {record['relative_path']}")
        elif path.stat().st_size != record["byte_size"] or _sha256(path) != record["sha256"]:
            errors.append(f"changed: {record['relative_path']}")
    roots = [Path(root) for root in lock["roots"]]
    actual = {
        path.resolve().relative_to(base_path).as_posix()
        for path in _files(base_path, roots)
    }
    actual.update(lock.get("selection_files", []))
    errors.extend(f"new tracked file: {path}" for path in sorted(actual - expected))
    if errors:
        raise RuntimeError("Holdout configuration lock failed:\n- " + "\n- ".join(errors))
    return lock
