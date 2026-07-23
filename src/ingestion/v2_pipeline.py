"""Strict V2 acquisition rendering and chunking primitives."""

from __future__ import annotations

import html
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.contracts.chunk import ChunkV2
from src.utils.hashing import sha256_text

RENDERER_VERSION = "myscheme-approved-fields-v1"
CHUNKER_VERSION = "fixed-word-window-v1"
APPROVED_SECTIONS = (
    ("detailedDescription_md", "detailedDescription"),
    ("briefDescription",),
    ("benefits_md", "benefits"),
    ("eligibilityDescription_md", "eligibilityDescription"),
    ("exclusions_md",),
)
FORBIDDEN = re.compile(
    r"(?:<script|javascript:|cookie banner|schema_version|schemeContent|detailedDescription_md|\{\s*\"|\bnull\b)", re.I
)
LABEL_LINE = re.compile(r"^\s*(?:scheme name|objective|description|benefits?|eligibility|application process|required documents?|exclusions?|ministry|department|implementing agency|official references?)\s*:\s*", re.I)


class AcquisitionError(RuntimeError):
    """Raised after bounded acquisition retries fail."""


@dataclass(frozen=True)
class HTTPResult:
    status: int
    final_url: str
    mime_type: str
    body: bytes


def fetch_https(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
    backoff_seconds: float = 0.25,
    opener: Callable[..., Any] = urlopen,
) -> HTTPResult:
    """Fetch HTTPS URL with bounded backoff and no silent fallback."""
    if not url.startswith("https://"):
        raise AcquisitionError("only HTTPS acquisition is allowed")
    if attempts < 1:
        raise AcquisitionError("attempts must be positive")
    safe_headers = {"User-Agent": "rag-dissertation-v2/1.0", **(headers or {})}
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            with opener(Request(url, headers=safe_headers), timeout=45) as response:
                status = int(response.status)
                body = response.read()
                mime = response.headers.get_content_type().lower()
                if status != 200 or not body:
                    raise AcquisitionError(f"HTTP {status} or empty body for {url}")
                return HTTPResult(status, response.geturl(), mime, body)
        except (HTTPError, URLError, TimeoutError, OSError, AcquisitionError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(backoff_seconds * (2**attempt))
    raise AcquisitionError(f"acquisition failed after {attempts} attempts for {url}: {last}")


def _plain(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(_plain(item) for item in value)
    elif isinstance(value, dict):
        value = " ".join(_plain(item) for item in value.values())
    elif not isinstance(value, str):
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"!\[[^]]*]\([^)]*\)|\[([^]]+)]\([^)]*\)", r"\1", value)
    value = re.sub(r"^\s{0,3}(?:#{1,6}|>\s*|[-*+] |\d+[.)] )", "", value, flags=re.M)
    value = re.sub(r"[*_`~|]", "", value)
    lines = [LABEL_LINE.sub("", line).strip() for line in value.splitlines()]
    value = " ".join(line for line in lines if line and line.lower() not in {"none", "n/a", "not available"})
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()


def render_myscheme_record(record: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Render approved MyScheme fields into unlabeled natural prose."""
    english = record.get("en")
    if not isinstance(english, dict):
        raise ValueError("MyScheme record lacks en object")
    basic = english.get("basicDetails")
    content = english.get("schemeContent")
    eligibility = english.get("eligibilityCriteria") or {}
    if not isinstance(basic, dict) or not isinstance(content, dict):
        raise ValueError("MyScheme basicDetails or schemeContent malformed")
    title = _plain(basic.get("schemeName"))
    ministry = _plain((basic.get("nodalMinistryName") or {}).get("label"))
    department = _plain((basic.get("nodalDepartmentName") or {}).get("label"))
    agency = _plain(basic.get("implementingAgency"))
    sections: list[str] = []
    for choices in APPROVED_SECTIONS[:3]:
        rendered = next((_plain(content.get(key)) for key in choices if _plain(content.get(key))), "")
        if rendered and rendered not in sections:
            sections.append(rendered)
    elig = next((_plain(eligibility.get(key)) for key in APPROVED_SECTIONS[3] if _plain(eligibility.get(key))), "")
    if elig:
        sections.append(elig)
    exclusions = _plain(content.get("exclusions_md"))
    if exclusions:
        sections.append(exclusions)
    applications = english.get("applicationProcess") or []
    for application in applications:
        process = _plain(application.get("process_md") or application.get("process")) if isinstance(application, dict) else ""
        if process:
            sections.append(process)
    prefix = ". ".join(x for x in (title, ministry, department, agency) if x)
    text = ". ".join([prefix, *sections]).strip(" .") + "."
    if not title or not ministry or len(text.split()) < 80:
        raise ValueError("rendered record missing title/ministry or has fewer than 80 words")
    if FORBIDDEN.search(text) or LABEL_LINE.search(text):
        raise ValueError("rendered text contains raw JSON, schema label, HTML, or placeholder leakage")
    return text, {"title": title, "ministry": ministry, "department": department, "implementing_agency": agency}


def chunk_document_v2(
    *, document_id: str, source_id: str, text: str, source_sha256: str,
    corpus_version: str = "pilot-v2", renderer_version: str = RENDERER_VERSION,
    max_words: int = 300, overlap: int = 60,
) -> list[ChunkV2]:
    """Create stable word chunks with exact offsets and overlap."""
    if not text.strip():
        raise ValueError("cannot chunk empty text")
    if max_words != 300 or overlap != 60:
        raise ValueError("V2 pilot chunking is frozen at 300 words with overlap 60")
    matches = list(re.finditer(r"\S+", text))
    chunks: list[ChunkV2] = []
    step = max_words - overlap
    for index, start in enumerate(range(0, len(matches), step)):
        end = min(start + max_words, len(matches))
        start_char = matches[start].start()
        end_char = matches[end - 1].end()
        chunk_text = text[start_char:end_char]
        digest = sha256_text(chunk_text)
        chunk_id = f"{corpus_version}-{document_id}-{index:04d}-{digest[:12]}"
        chunks.append(ChunkV2(
            schema_version="2.0", chunk_id=chunk_id, document_id=document_id, source_id=source_id,
            chunk_index=index, start_word=start, end_word=end, word_count=end-start,
            start_char=start_char, end_char=end_char, previous_overlap=0 if index == 0 else min(overlap, end-start),
            text=chunk_text, text_sha256=digest, source_sha256=source_sha256,
            corpus_version=corpus_version, renderer_version=renderer_version, chunker_version=CHUNKER_VERSION,
        ))
        if end == len(matches):
            break
    return chunks
