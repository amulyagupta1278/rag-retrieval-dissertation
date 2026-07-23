"""Deterministic collision-safe atomic JSON writers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _atomic_write(path: Path, text: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"output exists; pass overwrite=True explicitly: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_json(path: str | Path, value: Any, *, overwrite: bool = False) -> None:
    _atomic_write(Path(path), stable_json(value) + "\n", overwrite=overwrite)


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]], *, key: str, overwrite: bool = False) -> None:
    ordered = sorted(rows, key=lambda row: str(row[key]))
    values = [row[key] for row in ordered]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {key} values")
    _atomic_write(Path(path), "".join(stable_json(row) + "\n" for row in ordered), overwrite=overwrite)


def write_bytes(path: str | Path, data: bytes, *, overwrite: bool = False) -> None:
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"output exists; pass overwrite=True explicitly: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
