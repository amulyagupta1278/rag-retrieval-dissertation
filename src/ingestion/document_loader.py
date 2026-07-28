"""
Document Loader — Ingestion Layer
==================================
Research purpose
    Entry point for the dataset pipeline. Converts heterogeneous file formats
    (PDF, DOCX, TXT, HTML, JSON) into a canonical RawDocument schema that every
    downstream module can consume without format-specific branching.

Design choice
    A format-dispatching class with one method per format keeps each extractor
    independently testable. The canonical schema is a frozen dataclass so
    downstream code cannot accidentally mutate it.

Alternative approaches
    LangChain document loaders are convenient but hide extraction details and
    make reproducibility harder to audit. Unstructured.io is heavier than
    needed for dissertation-scale corpora.

Expected strengths
    Full provenance tracking from raw bytes to processed text; supports all
    formats required by the dissertation corpus.

Expected weaknesses
    PDF extraction quality depends on PyMuPDF; scanned PDFs require OCR (not
    in scope for mid-semester milestone).
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

_JSON_METADATA_KEYS = {
    "_id", "id", "schemeid", "slug", "type", "align", "bold", "italic",
    "underline", "link", "url", "value", "schemeimageurl",
}
_SPACE_RE = re.compile(r"\s+")


def _clean_json_text(value: str) -> str:
    """Convert one human-facing JSON string into plain retrieval text."""
    text = value
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\\n", "\n")
    return _SPACE_RE.sub(" ", text).strip(" \t\r\n-|")


def _human_text_leaves(value) -> list[str]:
    """Extract ordered human text while excluding schema and Markdown copies."""
    if isinstance(value, str):
        cleaned = _clean_json_text(value)
        return [cleaned] if cleaned else []
    if isinstance(value, list):
        return [text for item in value for text in _human_text_leaves(item)]
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("text"), str):
        cleaned = _clean_json_text(value["text"])
        return [cleaned] if cleaned else []
    output: list[str] = []
    for key, child in value.items():
        lower = key.lower()
        if lower in _JSON_METADATA_KEYS or lower.endswith("_md"):
            continue
        output.extend(_human_text_leaves(child))
    return output


def _label(value) -> str:
    if isinstance(value, dict):
        return _clean_json_text(str(value.get("label") or ""))
    if isinstance(value, str):
        return _clean_json_text(value)
    return ""


def _unique_paragraphs(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_json_text(value)
        key = " ".join(re.findall(r"[a-z0-9]+", cleaned.lower()))
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def extract_myscheme_text(data: dict) -> tuple[str, str, dict] | None:
    """Project official myScheme JSON into deterministic, non-serialized text."""
    core = data.get("core")
    english = core.get("en") if isinstance(core, dict) else None
    if not isinstance(english, dict) or not isinstance(english.get("basicDetails"), dict):
        return None
    basic = english["basicDetails"]
    scheme_name = _clean_json_text(str(basic.get("schemeName") or ""))
    if not scheme_name:
        return None

    paragraphs: list[str] = [f"Scheme: {scheme_name}"]
    structured = (
        ("Ministry", basic.get("nodalMinistryName")),
        ("Department", basic.get("nodalDepartmentName")),
        ("Implementing agency", basic.get("implementingAgency")),
        ("Level", basic.get("level")),
        ("Scheme type", basic.get("schemeType")),
    )
    for heading, value in structured:
        content = _label(value)
        if content:
            paragraphs.append(f"{heading}: {content}")
    beneficiaries = [_label(item) for item in basic.get("targetBeneficiaries") or []]
    beneficiaries = [value for value in beneficiaries if value]
    if beneficiaries:
        paragraphs.append(f"Target beneficiaries: {', '.join(beneficiaries)}")

    scheme_content = english.get("schemeContent") if isinstance(english.get("schemeContent"), dict) else {}
    eligibility = english.get("eligibilityCriteria") if isinstance(english.get("eligibilityCriteria"), dict) else {}
    documents = data.get("documents", {}).get("en", {}) if isinstance(data.get("documents"), dict) else {}
    if not isinstance(documents, dict):
        documents = {}
    sections = (
        ("Overview", scheme_content.get("briefDescription")),
        ("Detailed description", scheme_content.get("detailedDescription")),
        ("Benefits", scheme_content.get("benefits")),
        ("Exclusions", scheme_content.get("exclusions")),
        ("Eligibility", eligibility.get("eligibilityDescription")),
        ("Application process", english.get("applicationProcess")),
        ("Required documents", documents.get("documents_required")),
        ("Definitions", english.get("schemeDefinitions")),
    )
    for heading, value in sections:
        content = _unique_paragraphs(_human_text_leaves(value))
        if content:
            paragraphs.append(heading)
            paragraphs.extend(content)

    faqs = data.get("faqs", {}).get("en", {}).get("faqs", [])
    faq_lines: list[str] = []
    for item in faqs if isinstance(faqs, list) else []:
        if not isinstance(item, dict):
            continue
        question = _clean_json_text(str(item.get("question") or ""))
        answers = _unique_paragraphs(_human_text_leaves(item.get("answer")))
        if question and answers:
            faq_lines.extend((f"Question: {question}", f"Answer: {' '.join(answers)}"))
    if faq_lines:
        paragraphs.append("Frequently asked questions")
        paragraphs.extend(faq_lines)

    text = "\n\n".join(_unique_paragraphs(paragraphs))
    return text, scheme_name, {"json_projection": "myscheme_v1"}


@dataclass
class RawDocument:
    """Canonical representation of an ingested document."""

    doc_id: str
    source_path: str
    source_type: str          # pdf | docx | txt | html | json
    raw_text: str
    title: str
    language: str
    byte_size: int
    sha256: str
    ingested_at: str
    domain_tag: str
    extra_meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "raw_text": self.raw_text,
            "title": self.title,
            "language": self.language,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "ingested_at": self.ingested_at,
            "domain_tag": self.domain_tag,
            "extra_meta": self.extra_meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RawDocument":
        return cls(**d)


class DocumentLoader:
    """
    Loads documents from disk and returns RawDocument instances.

    Parameters
    ----------
    domain_tag : str
        Corpus-level tag written to every document's metadata.
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".html", ".htm", ".json"}

    def __init__(self, domain_tag: str = "general") -> None:
        self.domain_tag = domain_tag

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_file(self, path: str | Path) -> RawDocument:
        """Load a single file and return a RawDocument."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")

        ext = p.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported extension: {ext}")

        raw_bytes = p.read_bytes()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        doc_id = f"doc_{sha256[:12]}"

        dispatch = {
            ".pdf": self._load_pdf,
            ".docx": self._load_docx,
            ".txt": self._load_txt,
            ".html": self._load_html,
            ".htm": self._load_html,
            ".json": self._load_json,
        }
        text, title, extra = dispatch[ext](p)

        return RawDocument(
            doc_id=doc_id,
            source_path=str(p.resolve()),
            source_type=ext.lstrip("."),
            raw_text=text,
            title=title,
            language="en",
            byte_size=len(raw_bytes),
            sha256=sha256,
            ingested_at=datetime.now(timezone.utc).isoformat(),
            domain_tag=self.domain_tag,
            extra_meta=extra,
        )

    def load_directory(
        self,
        directory: str | Path,
        recursive: bool = True,
    ) -> Iterator[RawDocument]:
        """Yield RawDocument for each supported file in *directory*."""
        d = Path(directory)
        pattern = "**/*" if recursive else "*"
        for p in sorted(d.glob(pattern)):
            if p.is_file() and p.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                try:
                    yield self.load_file(p)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to load %s: %s", p, exc)

    # ------------------------------------------------------------------
    # Format extractors
    # ------------------------------------------------------------------

    def _load_txt(self, path: Path) -> tuple[str, str, dict]:
        text = path.read_text(encoding="utf-8", errors="replace")
        title = path.stem.replace("_", " ").replace("-", " ").title()
        return text, title, {}

    def _load_pdf(self, path: Path) -> tuple[str, str, dict]:
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(path))
            pages = [page.get_text() for page in doc]
            text = "\n".join(pages)
            title = doc.metadata.get("title") or path.stem
            extra = {
                "num_pages": len(doc),
                "author": doc.metadata.get("author", ""),
            }
            doc.close()
            return text, title, extra
        except ImportError:
            logger.warning("PyMuPDF not installed; reading PDF as bytes")
            return path.read_text(encoding="utf-8", errors="replace"), path.stem, {}

    def _load_docx(self, path: Path) -> tuple[str, str, dict]:
        try:
            import docx

            doc = docx.Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
            props = doc.core_properties
            title = getattr(props, "title", None) or path.stem
            return text, title, {"author": getattr(props, "author", "")}
        except ImportError:
            logger.warning("python-docx not installed; skipping DOCX: %s", path)
            return "", path.stem, {}

    def _load_html(self, path: Path) -> tuple[str, str, dict]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(raw, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else path.stem
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
        except ImportError:
            # Fallback: strip tags with regex
            text = re.sub(r"<[^>]+>", " ", raw)
            title = path.stem
        return text, title, {}

    def _load_json(self, path: Path) -> tuple[str, str, dict]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            projected = extract_myscheme_text(data)
            if projected:
                return projected
            text = data.get("text") or data.get("content")
            if not isinstance(text, str) or not text.strip():
                text = "\n\n".join(_unique_paragraphs(_human_text_leaves(data)))
            title = data.get("title") or path.stem
        elif isinstance(data, list):
            text = "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in data
            )
            title = path.stem
        else:
            text = str(data)
            title = path.stem
        return text, title, {}
