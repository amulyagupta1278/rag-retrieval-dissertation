#!/usr/bin/env python3
"""Fetch pinned browser libraries once; verify bytes before local vendoring."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
ASSETS = {
    "gsap-3.12.5.min.js": (
        "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js",
        "28033e449a31ebcc396e5be8b13b63152bf03094288fb5867034321927bce087",
    ),
    "three-r128.min.js": (
        "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
        "9274bbcec8d96168626c732b5d31c775aa8cfb7eaa0599bec0c175908a2c1ce2",
    ),
}


def main() -> None:
    VENDOR.mkdir(parents=True, exist_ok=True)
    for filename, (url, expected) in ASSETS.items():
        destination = VENDOR / filename
        payload = destination.read_bytes() if destination.is_file() else urllib.request.urlopen(url, timeout=30).read()
        observed = hashlib.sha256(payload).hexdigest()
        if observed != expected:
            raise RuntimeError(f"vendor hash mismatch for {filename}: {observed}")
        if not destination.is_file():
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            temporary.write_bytes(payload)
            temporary.replace(destination)
        print(f"{observed}  {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
