#!/usr/bin/env python3
"""Acquire reviewed government documents without performing ingestion."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.ingestion.corpus_quality import (  # noqa: E402
    CorpusValidationError,
    is_authoritative_url,
    validate_catalog,
)

LOGGER = logging.getLogger("download_corpus")
USER_AGENT = "RAG-Retrieval-Dissertation/2.0 (academic corpus acquisition; contact in repository)"
# Public browser key distributed by myScheme frontend. Environment override handles rotation.
MYSCHEME_API_KEY = os.environ.get("MYSCHEME_API_KEY", "tYTy5eEhlu9rFjyxuCr7ra7ACp4dv1RH8gWuHTDc")
SIGNATURES = {
    "pdf": lambda data: data.startswith(b"%PDF-"),
    "docx": lambda data: data.startswith(b"PK\x03\x04"),
    "html": lambda data: b"<html" in data[:4096].lower() or b"<!doctype html" in data[:4096].lower(),
    "txt": lambda data: bool(data.strip()),
    "json": lambda data: data.lstrip().startswith((b"{", b"[")),
}
ERROR_MARKERS = (b"captcha", b"access denied", b"login required", b"page not found")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download authoritative corpus v2")
    parser.add_argument("--catalog", default="data/sources/source_catalog_v2.jsonl")
    parser.add_argument("--output-dir", default="data/raw/snapshot_v2")
    parser.add_argument("--audit", default="data/metadata/acquisition_audit_v2.jsonl")
    parser.add_argument("--min-documents", type=int, default=100)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--connect-timeout", type=float, default=15)
    parser.add_argument("--read-timeout", type=float, default=90)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise CorpusValidationError(f"{path}:{line_number}: {exc}") from exc
    return records


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    temporary.replace(path)


def validate_payload(data: bytes, expected_format: str) -> None:
    if not data.strip():
        raise ValueError("empty response")
    if expected_format == "html" and any(marker in data[:100_000].lower() for marker in ERROR_MARKERS):
        raise ValueError("response contains login/CAPTCHA/error content")
    validator = SIGNATURES[expected_format]
    if not validator(data):
        raise ValueError(f"response signature does not match {expected_format}")
    if expected_format == "html":
        lower = data[:250_000].lower()
        if b"government of india" not in lower and b"govt. of india" not in lower and b"ministry of" not in lower:
            raise ValueError("HTML lacks government ownership marker")


def fetch(session: requests.Session, record: dict, args: argparse.Namespace) -> tuple[bytes, requests.Response]:
    last_error: Exception | None = None
    for attempt in range(args.retries):
        try:
            response = session.get(
                record["url"], timeout=(args.connect_timeout, args.read_timeout),
                allow_redirects=True,
            )
            response.raise_for_status()
            if not is_authoritative_url(response.url):
                raise ValueError(f"redirected to non-authoritative URL: {response.url}")
            validate_payload(response.content, record["format"])
            return response.content, response
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt + 1 < args.retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(str(last_error))


def fetch_myscheme_bundle(session: requests.Session, record: dict, args: argparse.Namespace) -> tuple[bytes, str, int, str]:
    """Fetch scheme core, FAQs, and official linked-document metadata as one source document."""
    slug = record["url"].rstrip("/").rsplit("/", 1)[-1]
    base = "https://api.myscheme.gov.in/schemes/v6/public/schemes"
    headers = {"x-api-key": MYSCHEME_API_KEY, "Origin": "https://www.myscheme.gov.in", "Referer": record["url"]}
    last_error: Exception | None = None
    for attempt in range(args.retries):
        try:
            core_response = session.get(f"{base}?slug={slug}&lang=en", headers=headers, timeout=(args.connect_timeout, args.read_timeout))
            core_response.raise_for_status()
            core_payload = core_response.json()
            if core_payload.get("statusCode") != 200 or not core_payload.get("data", {}).get("_id"):
                raise ValueError("myScheme core API returned no scheme")
            scheme_id = core_payload["data"]["_id"]
            bundle = {"core": core_payload["data"]}
            for kind in ("faqs", "documents"):
                response = session.get(f"{base}/{scheme_id}/{kind}?lang=en", headers=headers, timeout=(args.connect_timeout, args.read_timeout))
                response.raise_for_status()
                bundle[kind] = response.json().get("data")
            data = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")
            validate_payload(data, "json")
            return data, core_response.url, core_response.status_code, core_response.headers.get("content-type", "application/json")
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < args.retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(str(last_error))


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="[%(levelname)s] %(message)s")
    catalog_path, output_dir, audit_path = Path(args.catalog), Path(args.output_dir), Path(args.audit)
    records = load_jsonl(catalog_path)
    validate_catalog(records)
    enabled = sorted((r for r in records if r["enabled"]), key=lambda r: r["catalog_id"])
    output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"})
    audit: list[dict] = []
    metadata: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for record in enabled:
        path = output_dir / f"{record['catalog_id']}.{record['format']}"
        base = {"catalog_id": record["catalog_id"], "requested_url": record["url"], "retrieved_at": now}
        try:
            if path.exists():
                data = path.read_bytes()
                validate_payload(data, record["format"])
                final_url, status, content_type, outcome = record["url"], None, None, "reused"
            else:
                if record.get("acquisition") == "myscheme_api_bundle":
                    data, final_url, status, content_type = fetch_myscheme_bundle(session, record, args)
                    response = None
                else:
                    data, response = fetch(session, record, args)
                    final_url, status = response.url, response.status_code
                    content_type = response.headers.get("content-type", "")
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(path)
                outcome = "downloaded"
            sha256 = hashlib.sha256(data).hexdigest()
            item = {
                **record, "local_path": str(path), "final_url": final_url,
                "http_status": status, "content_type": content_type,
                "sha256": sha256, "byte_size": len(data), "retrieved_at": now,
            }
            metadata.append(item)
            audit.append({**base, "final_url": final_url, "outcome": outcome, "sha256": sha256, "byte_size": len(data)})
            LOGGER.info("%s %s", outcome.upper(), record["catalog_id"])
        except Exception as exc:  # each rejection must remain auditable
            audit.append({**base, "outcome": "rejected", "reason": str(exc)})
            LOGGER.error("REJECTED %s: %s", record["catalog_id"], exc)

    write_jsonl(audit, audit_path)
    write_jsonl(metadata, output_dir / "metadata.jsonl")
    LOGGER.info("Acquisition complete: %d/%d accepted", len(metadata), len(enabled))
    if len(metadata) < args.min_documents:
        LOGGER.error("Accepted documents below required minimum %d", args.min_documents)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
