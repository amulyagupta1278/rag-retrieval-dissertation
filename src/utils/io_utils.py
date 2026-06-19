"""JSONL and YAML I/O helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_jsonl(path: str | Path) -> list[dict]:
    items: list[dict] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def save_jsonl(items: list[dict], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item) + "\n")


def load_yaml(path: str | Path) -> Any:
    try:
        import yaml

        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except ImportError:
        raise ImportError("Install PyYAML: pip install pyyaml")
