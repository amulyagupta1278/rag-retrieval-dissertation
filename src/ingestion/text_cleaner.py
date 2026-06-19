"""
Text Cleaner — Ingestion Layer
================================
Research purpose
    Normalises raw extracted text before chunking. Cleaning decisions (what to
    keep vs remove) directly affect retrieval quality, so the module is
    parameterised and every decision is logged.

Design choice
    Pure-Python pipeline of composable cleaning steps; no external NLP library
    required so the module runs cheaply on CPU.

Alternative approaches
    LangChain text splitters bundle cleaning and chunking; separating them
    keeps each stage independently ablatable.

Expected strengths
    Unicode normalisation handles multi-byte artefacts from PDF extraction.
    Boilerplate heuristics remove headers/footers that degrade BM25 term
    statistics.

Expected weaknesses
    Heuristic boilerplate removal may accidentally strip legitimate repeated
    terms in domain-specific corpora (e.g. regulatory documents with repeated
    section headers).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Patterns that identify boilerplate lines
_BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*page\s+\d+\s*(of\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$"),                    # bare page numbers
    re.compile(r"^\s*(table of contents|contents)\s*$", re.IGNORECASE),
    re.compile(r"^\s*www\.\S+\s*$", re.IGNORECASE),  # bare URLs
    re.compile(r"^\s*©.*$", re.IGNORECASE),
    re.compile(r"^\s*all rights reserved.*$", re.IGNORECASE),
]

_EXCESS_WHITESPACE = re.compile(r"\n{3,}")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class CleaningConfig:
    normalise_unicode: bool = True
    remove_boilerplate_lines: bool = True
    remove_control_chars: bool = True
    collapse_whitespace: bool = True
    lowercase: bool = False           # keep case for NER downstream


class TextCleaner:
    """
    Transforms raw extracted text into normalised, retrieval-ready text.

    Parameters
    ----------
    config : CleaningConfig
        Feature flags controlling each cleaning step.
    """

    def __init__(self, config: CleaningConfig | None = None) -> None:
        self.config = config or CleaningConfig()

    def clean(self, text: str) -> str:
        """Return cleaned text."""
        if self.config.normalise_unicode:
            text = self._normalise_unicode(text)
        if self.config.remove_control_chars:
            text = _CONTROL_CHARS.sub(" ", text)
        if self.config.remove_boilerplate_lines:
            text = self._remove_boilerplate(text)
        if self.config.collapse_whitespace:
            text = _EXCESS_WHITESPACE.sub("\n\n", text)
            text = text.strip()
        if self.config.lowercase:
            text = text.lower()
        return text

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_unicode(text: str) -> str:
        # NFKC: compatibility decomposition then canonical composition.
        # Converts ligatures (ﬁ → fi), normalises dashes, etc.
        return unicodedata.normalize("NFKC", text)

    @staticmethod
    def _remove_boilerplate(text: str) -> str:
        lines = text.split("\n")
        cleaned: list[str] = []
        for line in lines:
            if not any(p.match(line) for p in _BOILERPLATE_PATTERNS):
                cleaned.append(line)
        return "\n".join(cleaned)
