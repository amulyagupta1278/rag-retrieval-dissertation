"""Artifact lineage manifest contracts."""

from __future__ import annotations

from dataclasses import dataclass

from ._validation import require_schema, require_sha256, require_unique, required_text, stable_dict


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    path: str
    sha256: str
    byte_size: int
    created_by: str
    input_artifact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("artifact_id", "path", "created_by"):
            required_text(name, getattr(self, name))
        require_sha256("sha256", self.sha256)
        require_unique("input_artifact_ids", self.input_artifact_ids)
        if self.byte_size < 0:
            raise ValueError("byte_size must be non-negative")


@dataclass(frozen=True)
class ArtifactManifest:
    schema_version: str
    manifest_id: str
    created_at: str
    artifacts: tuple[ArtifactRecord, ...]

    def __post_init__(self) -> None:
        require_schema(self.schema_version)
        required_text("manifest_id", self.manifest_id)
        required_text("created_at", self.created_at)
        require_unique("artifact IDs", (x.artifact_id for x in self.artifacts))
        paths = [x.path for x in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("artifact manifest contains duplicate paths")
        known = {x.artifact_id for x in self.artifacts}
        unknown = sorted({parent for x in self.artifacts for parent in x.input_artifact_ids} - known)
        if unknown:
            raise ValueError(f"artifact manifest has unknown input references: {unknown}")

    def to_dict(self) -> dict:
        return stable_dict(self)
