#!/usr/bin/env python3
"""Build self-contained Screen 2 exhibit from shared verified payload."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboards"
DATA = DASH / "data/dashboard_payload.json"
TEMPLATE = DASH / "screen2_template.html"
OUTPUT = DASH / "screen2_exhibit.html"
MANIFEST = DASH / "data/screen2_manifest.json"
VENDOR = {
    "__GSAP__": DASH / "vendor/gsap-3.12.5.min.js",
    "__THREE__": DASH / "vendor/three-r128.min.js",
}
VENDOR_HASHES = {
    "__GSAP__": "28033e449a31ebcc396e5be8b13b63152bf03094288fb5867034321927bce087",
    "__THREE__": "9274bbcec8d96168626c732b5d31c775aa8cfb7eaa0599bec0c175908a2c1ce2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    if payload.get("evidence_commit") != "7bc5bda9c6fc01964bab0247145699fe14e35175":
        raise ValueError("shared payload has wrong evidence commit")
    if len(payload.get("queries", [])) != 34 or len(payload.get("aggregates", [])) != 5:
        raise ValueError("shared payload has wrong panel dimensions")
    document = TEMPLATE.read_text(encoding="utf-8")
    if document.count("__DATA__") != 1 or any(document.count(marker) != 1 for marker in VENDOR):
        raise ValueError("screen2 template vendor/data marker count mismatch")
    document = document.replace(
        "__DATA__",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
    )
    document = document.replace("__PAYLOAD_HASH__", sha256(DATA))
    for marker, path in VENDOR.items():
        if sha256(path) != VENDOR_HASHES[marker]:
            raise ValueError(f"vendor asset hash drift: {path.name}")
        document = document.replace(marker, path.read_text(encoding="utf-8"))
    if "__DATA__" in document or "__PAYLOAD_HASH__" in document:
        raise ValueError("unresolved screen2 template marker")
    if re.search(r"(?:src|href)=[\"']https?://|@import\s+url", document, flags=re.IGNORECASE):
        raise ValueError("Screen 2 contains external dependency")
    temporary = OUTPUT.with_suffix(".html.tmp")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(OUTPUT)
    manifest = {
        "status": "gate3_passed",
        "evidence_commit": payload["evidence_commit"],
        "qrels_base": payload["qrels_base"],
        "payload_sha256": sha256(DATA),
        "output_sha256": sha256(OUTPUT),
        "output_bytes": OUTPUT.stat().st_size,
        "offline_external_reference_n": 0,
        "vendor_hashes": {path.name: VENDOR_HASHES[marker] for marker, path in VENDOR.items()},
        "required_panels": [
            "response_grid",
            "irt_ability_dial",
            "three_dimensional_query_field",
            "radar",
            "category_bars",
            "h5_aggregate",
            "provenance",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
