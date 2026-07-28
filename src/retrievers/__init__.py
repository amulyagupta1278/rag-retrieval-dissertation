"""Retriever package.

Import note (2026-07-28):
  ``FAISSRetriever`` is resolved lazily via PEP 562 ``__getattr__``. It is the
  only retriever in this package requiring heavy ML dependencies
  (``sentence_transformers``, ``faiss``, ``torch``).

  Previously this module imported it eagerly, which meant importing any sibling
  submodule -- ``bm25_retriever``, ``entity_graph_v3``, ``hybrid_rrf_v1``,
  ``prompt_rag_contract``, ``prompt_rag_claude_v2`` -- ran the package
  ``__init__`` and transitively required torch. None of those modules use FAISS.
  That coupling made 168 pure-logic test functions across 10 modules unrunnable
  without a ~430MB dependency chain, and was the technical cause of the
  over-broad ``pytest.importorskip`` skips recorded in
  audits/phase6_invalidation/INVALIDATION_NOTICE.md (Violation 4).

  Public API is unchanged: ``from src.retrievers import FAISSRetriever`` still
  works and still raises ImportError if the ML extras are absent -- but now only
  when FAISSRetriever is actually requested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base_retriever import BaseRetriever, RetrievalResult, RetrievalRun
from .bm25_retriever import BM25Retriever
from .graphrag_retriever import GraphRAGRetriever
from .structured_graph_retriever import StructuredMetadataGraphRetriever

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from .faiss_retriever import FAISSRetriever

_LAZY = {"FAISSRetriever": ".faiss_retriever"}

__all__ = [
    "BaseRetriever",
    "RetrievalResult",
    "RetrievalRun",
    "FAISSRetriever",
    "BM25Retriever",
    "GraphRAGRetriever",
    "StructuredMetadataGraphRetriever",
]


def __getattr__(name: str) -> Any:
    """Resolve heavy retrievers on first attribute access (PEP 562)."""
    if name in _LAZY:
        from importlib import import_module

        module = import_module(_LAZY[name], __name__)
        value = getattr(module, name)
        globals()[name] = value  # cache so this resolves once
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
