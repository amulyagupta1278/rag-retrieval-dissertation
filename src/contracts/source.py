"""Raw official-source acquisition contract."""

from __future__ import annotations

from dataclasses import dataclass

from ._validation import require_schema, require_sha256, require_url, required_text, stable_dict

SUPPORTED_MIME_TYPES = {"application/json", "application/pdf", "text/html"}


@dataclass(frozen=True)
class RawSourceRecord:
    schema_version: str
    source_id: str
    scheme_id: str
    scheme_title: str
    ministry: str
    department: str
    official_url: str
    retrieved_at: str
    http_status: int
    final_url: str
    mime_type: str
    content_length: int
    acquisition_method: str
    raw_sha256: str
    raw_snapshot_path: str
    extraction_method: str
    extraction_tool_version: str
    extraction_status: str
    validation_status: str
    error_reason: str = ""

    def __post_init__(self) -> None:
        require_schema(self.schema_version)
        for name in ("source_id", "scheme_id", "scheme_title", "ministry", "retrieved_at",
                     "acquisition_method", "raw_snapshot_path", "extraction_method",
                     "extraction_tool_version", "extraction_status", "validation_status"):
            required_text(name, getattr(self, name))
        require_url("official_url", self.official_url)
        require_url("final_url", self.final_url)
        require_sha256("raw_sha256", self.raw_sha256)
        if type(self.http_status) is not int or not 100 <= self.http_status <= 599:
            raise ValueError("http_status must be an integer from 100 through 599")
        if type(self.content_length) is not int or self.content_length <= 0:
            raise ValueError("content_length must be a positive integer")
        if self.mime_type not in SUPPORTED_MIME_TYPES:
            raise ValueError(f"unsupported MIME type: {self.mime_type!r}")
        if self.extraction_status != "complete" or self.validation_status != "valid":
            if not self.error_reason.strip():
                raise ValueError("invalid or partial source requires error_reason")

    def to_dict(self) -> dict:
        return stable_dict(self)
