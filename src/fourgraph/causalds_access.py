"""Allowlisted CausalDS public/grading file access."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


PUBLIC_ARTIFACTS = {
    "data": "data.parquet",
    "schema": "schema.json",
    "tasks": "tasks.json",
    "test_features": "test_features.parquet",
}

GRADING_ARTIFACTS = {
    "ground_truth": "ground_truth.json",
    "test": "test.parquet",
    "graph_image": "graph.png",
}


class GradingPurpose(str, Enum):
    """Explicit capabilities for the grading side of the release."""

    INTEGRITY_AUDIT = "integrity_audit"
    ORACLE = "oracle"
    SCORING = "scoring"


GRADING_PURPOSE_ARTIFACTS = {
    GradingPurpose.INTEGRITY_AUDIT: frozenset(GRADING_ARTIFACTS),
    GradingPurpose.ORACLE: frozenset({"ground_truth"}),
    GradingPurpose.SCORING: frozenset({"ground_truth", "test"}),
}


def _validate_scene_id(scene_id: str) -> None:
    if not scene_id.startswith("scene_") or not scene_id[6:].isdigit():
        raise ValueError(f"Invalid scene_id: {scene_id}")


def _validate_variant(variant: str) -> None:
    if variant not in {"clean", "proxy", "proxy_hard"}:
        raise ValueError(f"Invalid observation variant: {variant}")


def resolve_public_artifact(
    source_root: Path,
    scene_id: str,
    variant: str,
    artifact: str,
) -> Path:
    """Resolve an allowlisted public artifact and reject grading names."""
    _validate_scene_id(scene_id)
    _validate_variant(variant)
    if artifact not in PUBLIC_ARTIFACTS:
        raise PermissionError(f"Artifact is not available in public view: {artifact}")
    return (
        source_root.resolve()
        / "data"
        / "benchmark"
        / "main"
        / "scenes"
        / scene_id
        / "variants"
        / variant
        / PUBLIC_ARTIFACTS[artifact]
    )


def resolve_public_story(source_root: Path, scene_id: str) -> Path:
    """Resolve the public story without exposing the grading directory."""
    _validate_scene_id(scene_id)
    return (
        source_root.resolve()
        / "data"
        / "benchmark"
        / "main"
        / "scenes"
        / scene_id
        / "story.md"
    )


def resolve_grading_artifact(
    source_root: Path,
    scene_id: str,
    artifact: str,
    *,
    purpose: GradingPurpose,
) -> Path:
    """Resolve grading data only for an explicit allowlisted purpose."""
    _validate_scene_id(scene_id)
    if not isinstance(purpose, GradingPurpose):
        raise PermissionError(f"Purpose cannot access grading view: {purpose}")
    if artifact not in GRADING_ARTIFACTS:
        raise PermissionError(f"Unknown grading artifact: {artifact}")
    if artifact not in GRADING_PURPOSE_ARTIFACTS[purpose]:
        raise PermissionError(
            f"Grading purpose {purpose.value} cannot access artifact: {artifact}"
        )
    return (
        source_root.resolve()
        / "data"
        / "benchmark"
        / "main"
        / "scenes_private"
        / scene_id
        / GRADING_ARTIFACTS[artifact]
    )
