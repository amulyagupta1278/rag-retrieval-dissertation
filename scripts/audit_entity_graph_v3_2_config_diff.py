#!/usr/bin/env python3
"""Fail unless v3.2 config differs from v3.1 only in approved alias/version fields."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import stable_json, write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


ALLOWED_PATHS = {
    "alias_registry_sha256",
    "approved_corpus_backed_alias_additions",
    "graph_version",
    "registry_version",
}


def differences(left: Any, right: Any, prefix: str = "") -> list[dict[str, Any]]:
    if isinstance(left, dict) and isinstance(right, dict):
        rows: list[dict[str, Any]] = []
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in left:
                rows.append({"path": path, "v3_1": "__MISSING__", "v3_2": right[key]})
            elif key not in right:
                rows.append({"path": path, "v3_1": left[key], "v3_2": "__MISSING__"})
            else:
                rows.extend(differences(left[key], right[key], path))
        return rows
    return [] if left == right else [{"path": prefix, "v3_1": left, "v3_2": right}]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v3-1", type=Path, required=True)
    parser.add_argument("--v3-2", type=Path, required=True)
    parser.add_argument("--accepted-additions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    paths = tuple(path.resolve() for path in (args.v3_1, args.v3_2, args.accepted_additions, args.output))
    approved = (
        (ROOT / "configs/entity_graph_v3_1_frozen.json").resolve(),
        (ROOT / "configs/entity_graph_v3_2_frozen.json").resolve(),
        (ROOT / "audits/phase3_graph_v3_2/accepted_alias_additions.json").resolve(),
        (ROOT / "audits/phase3_graph_v3_2/configuration_diff_v3_1_to_v3_2.json").resolve(),
    )
    if paths != approved:
        raise ValueError("configuration diff requires approved paths")
    v31 = json.loads(paths[0].read_text(encoding="utf-8"))
    v32 = json.loads(paths[1].read_text(encoding="utf-8"))
    accepted = json.loads(paths[2].read_text(encoding="utf-8"))
    diff = differences(v31, v32)
    changed_roots = {row["path"].split(".", 1)[0] for row in diff}
    unexpected = sorted(changed_roots - ALLOWED_PATHS)
    if unexpected:
        raise ValueError(f"unapproved v3.1→v3.2 configuration changes: {unexpected}")
    expected_additions = [
        {"alias": row["alias"], "canonical_label": row["canonical_label"], "extraction_rule": row["extraction_rule"]}
        for row in accepted["additions"]
    ]
    if v32["approved_corpus_backed_alias_additions"] != expected_additions:
        raise ValueError("v3.2 config additions disagree with corpus alias audit")
    if v32["alias_registry_sha256"] != sha256_file(paths[2]):
        raise ValueError("v3.2 alias registry hash mismatch")
    if v31["scoring"] != v32["scoring"]:
        raise ValueError("scoring changed")
    output = {
        "status": "passed_only_version_and_approved_alias_fields_changed",
        "v3_1_config_sha256": sha256_file(paths[0]),
        "v3_2_config_sha256": sha256_file(paths[1]),
        "accepted_alias_additions_sha256": sha256_file(paths[2]),
        "allowed_changed_roots": sorted(ALLOWED_PATHS),
        "observed_changed_roots": sorted(changed_roots),
        "unexpected_changed_roots": unexpected,
        "scoring_unchanged": v31["scoring"] == v32["scoring"],
        "differences": diff,
    }
    write_json(paths[3], output, overwrite=args.overwrite)
    print(stable_json(output))


if __name__ == "__main__":
    main()
