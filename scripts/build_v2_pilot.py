#!/usr/bin/env python3
"""Acquire, render, and chunk official Phase 1 pilot corpus."""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.contracts.document import CorpusManifest, ExtractedDocument
from src.contracts.source import RawSourceRecord
from src.ingestion.v2_pipeline import RENDERER_VERSION, chunk_document_v2, fetch_https, render_myscheme_record
from src.utils.atomic_io import write_bytes, write_json, write_jsonl
from src.utils.hashing import sha256_bytes, sha256_text

SCHEMA = "2.0"
CORPUS = "pilot-v2"
SLUGS = (
    "ab-pmjay", "apy", "mgnrega", "pm-gkay", "pm-janman", "pm-poshan", "pm-svanidhi",
    "pmay-g", "pmay-u", "pmegp", "pmfby", "pmjdy", "pmjjby", "pmkvy-rpl", "pmkvy-sp",
    "pmkvy-stt", "pmmy", "pmsby", "pmuy", "pmuy2",
)
PDFS = (
    ("pm-kisan-guidelines", "PM-KISAN Operational Guidelines", "Ministry of Agriculture & Farmers Welfare",
     "Department of Agriculture & Farmers Welfare", "https://pmkisan.gov.in/Documents/RevisedPM-KISANOperationalGuidelines%28English%29.pdf"),
    ("pm-kmy-guidelines", "Pradhan Mantri Kisan Maan Dhan Yojana Operational Guidelines", "Ministry of Agriculture & Farmers Welfare",
     "Department of Agriculture & Farmers Welfare", "https://pmkisan.gov.in/Documents/PM-KMY%20-%20Operational%20Guidelines.pdf"),
)


def public_api_key() -> str:
    """Read public web-client credential into memory; never persist or log it."""
    page = fetch_https("https://www.myscheme.gov.in/schemes/pmmy").body.decode("utf-8")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', page)
    source = next((x for x in scripts if "pages/schemes/" in x), None)
    if not source:
        raise RuntimeError("MyScheme page lacks scheme client bundle")
    bundle = fetch_https(source).body.decode("utf-8")
    match = re.search(r'"x-api-key":"([^"]+)"', bundle, re.I)
    if not match:
        raise RuntimeError("MyScheme client bundle lacks public API header")
    return match.group(1)


def extract_pdf(body: bytes) -> tuple[str, dict]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF required for PDF extraction") from exc
    doc = fitz.open(stream=body, filetype="pdf")
    pages = [page.get_text("text", sort=True).strip() for page in doc]
    metadata = {
        "page_count": len(pages), "pages_extracted": sum(bool(x) for x in pages),
        "empty_page_count": sum(not x for x in pages), "extraction_warnings": [],
        "ocr_used": False, "extraction_library": f"PyMuPDF {fitz.VersionBind}",
    }
    text = "\n\n".join(x for x in pages if x)
    doc.close()
    if metadata["pages_extracted"] == 0 or len(text.split()) < 80:
        raise RuntimeError("PDF extraction produced insufficient text")
    return text, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    root = args.output_root.resolve()
    expected = (ROOT / "data/v2/pilot").resolve()
    if root != expected:
        raise ValueError(f"output-root must be {expected}")
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    key = public_api_key()
    sources: list[RawSourceRecord] = []
    documents: list[ExtractedDocument] = []
    failures: list[dict] = [{
        "source": "https://api.myscheme.gov.in/search/v4/schemes", "status": 401,
        "reason": "legacy search endpoint requires authorization; no credential supplied",
    }]

    for slug in SLUGS:
        endpoint = f"https://api.myscheme.gov.in/schemes/v6/public/schemes?slug={slug}&lang=en"
        result = fetch_https(endpoint, headers={"x-api-key": key})
        payload = json.loads(result.body)
        record = payload.get("data")
        if not isinstance(record, dict):
            failures.append({"source": endpoint, "status": result.status, "reason": "missing structured data"})
            continue
        text, meta = render_myscheme_record(record)
        source_id = f"myscheme-{slug}"
        document_id = f"doc-{slug}"
        raw_path = root / "raw" / f"{source_id}.json"
        raw_bytes = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        write_bytes(raw_path, raw_bytes, overwrite=args.overwrite)
        source_hash = sha256_bytes(raw_bytes)
        sources.append(RawSourceRecord(
            SCHEMA, source_id, slug, meta["title"], meta["ministry"], meta["department"],
            f"https://www.myscheme.gov.in/schemes/{slug}", timestamp, result.status, result.final_url,
            "application/json", len(raw_bytes), "myscheme_public_structured_api", source_hash,
            str(raw_path.relative_to(ROOT)), "approved_field_renderer", RENDERER_VERSION, "complete", "valid",
        ))
        documents.append(ExtractedDocument(
            SCHEMA, document_id, source_id, slug, meta["title"], meta["ministry"], meta["department"],
            text, sha256_text(text), source_hash, RENDERER_VERSION, "complete", "valid",
        ))

    for slug, title, ministry, department, url in PDFS:
        result = fetch_https(url)
        if result.mime_type != "application/pdf" and not result.body.startswith(b"%PDF"):
            failures.append({"source": url, "status": result.status, "reason": f"not PDF: {result.mime_type}"})
            continue
        source_id = f"official-pdf-{slug}"
        raw_path = root / "raw" / f"{source_id}.pdf"
        write_bytes(raw_path, result.body, overwrite=args.overwrite)
        text, pdf = extract_pdf(result.body)
        source_hash = sha256_bytes(result.body)
        sources.append(RawSourceRecord(
            SCHEMA, source_id, slug, title, ministry, department, url, timestamp, result.status,
            result.final_url, "application/pdf", len(result.body), "official_government_pdf", source_hash,
            str(raw_path.relative_to(ROOT)), "pymupdf_text", pdf["extraction_library"], "complete", "valid",
        ))
        documents.append(ExtractedDocument(
            SCHEMA, f"doc-{slug}", source_id, slug, title, ministry, department, text, sha256_text(text),
            source_hash, pdf["extraction_library"], "complete", "valid", pdf["page_count"],
            pdf["pages_extracted"], pdf["empty_page_count"], tuple(pdf["extraction_warnings"]), False,
        ))

    if not 20 <= len(documents) <= 25:
        raise RuntimeError(f"valid document count must be 20..25; got {len(documents)}")
    ministry_count = len({x.ministry for x in documents})
    manifest = CorpusManifest(SCHEMA, CORPUS, timestamp, tuple(x.document_id for x in documents),
                              tuple(x.source_id for x in sources), len(documents), ministry_count)
    chunks = [chunk for doc in documents for chunk in chunk_document_v2(
        document_id=doc.document_id, source_id=doc.source_id, text=doc.text,
        source_sha256=doc.source_sha256, renderer_version=doc.renderer_version,
    )]
    write_jsonl(root / "manifests/raw_sources.jsonl", [x.to_dict() for x in sources], key="source_id", overwrite=args.overwrite)
    write_jsonl(root / "extracted/documents.jsonl", [x.to_dict() for x in documents], key="document_id", overwrite=args.overwrite)
    write_jsonl(root / "chunks/chunks.jsonl", [x.to_dict() for x in chunks], key="chunk_id", overwrite=args.overwrite)
    write_json(root / "manifests/corpus.json", {**manifest.to_dict(), "chunk_count": len(chunks)}, overwrite=args.overwrite)
    write_json(root / "audits/acquisition_failures.json", failures, overwrite=args.overwrite)
    write_json(root / "audits/environment.json", {"python": platform.python_version(), "platform": platform.platform()}, overwrite=args.overwrite)
    print(json.dumps({"documents": len(documents), "structured": len(documents)-len(PDFS), "pdfs": len(PDFS),
                      "ministries": ministry_count, "chunks": len(chunks)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
