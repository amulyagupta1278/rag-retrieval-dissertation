"""Strict versioned contracts for V2 dissertation artifacts."""

from .artifact import ArtifactManifest, ArtifactRecord
from .benchmark import QAItemV2, QrelsJudgment
from .chunk import ChunkV2
from .document import CorpusManifest, ExtractedDocument
from .source import RawSourceRecord

__all__ = [
    "ArtifactManifest", "ArtifactRecord", "ChunkV2", "CorpusManifest",
    "ExtractedDocument", "QAItemV2", "QrelsJudgment", "RawSourceRecord",
]
