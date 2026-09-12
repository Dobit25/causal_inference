"""Restricted public-only CausalDS views shared by graph builders."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from fourgraph.causalds_access import resolve_public_artifact, resolve_public_story
from fourgraph.graph_contract import VariableMap


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _variable_type(column: Mapping[str, Any]) -> str:
    if column.get("is_binary") is True or column.get("dtype") == "bool":
        return "binary"
    for flag, variable_type in (
        ("is_categorical", "categorical"),
        ("is_ordinal", "ordinal"),
        ("is_count", "count"),
    ):
        if column.get(flag) is True:
            return variable_type
    dtype = str(column.get("dtype", "")).lower()
    if any(token in dtype for token in ("float", "double", "int")):
        return "continuous"
    raise ValueError(f"Cannot infer a canonical variable type from schema: {column}")


def load_causalds_variable_map(
    source_root: Path,
    scene_id: str,
    *,
    variant: str = "clean",
) -> tuple[VariableMap, str]:
    """Build the canonical map from public schema order only."""

    schema_path = resolve_public_artifact(
        source_root, scene_id, variant, "schema"
    )
    schema = read_json_object(schema_path, label="Public schema")
    columns = schema.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise ValueError("Public schema must contain a non-empty columns mapping")
    if schema.get("n_columns") != len(columns):
        raise ValueError("Public schema n_columns does not match its columns")
    variables: list[tuple[str, str]] = []
    for name, metadata in columns.items():
        if not isinstance(name, str) or not isinstance(metadata, dict):
            raise ValueError("Public schema columns are malformed")
        variables.append((name, _variable_type(metadata)))
    return VariableMap.build(scene_id, variables), sha256_file(schema_path)


@dataclass(frozen=True)
class PublicLLMGraphInput:
    """Complete and intentionally narrow evidence supplied to G_LLM."""

    scene_id: str
    story: str
    variable_map: VariableMap
    story_sha256: str
    public_schema_sha256: str

    @property
    def input_artifact_sha256(self) -> tuple[str, str]:
        return tuple(sorted((self.story_sha256, self.public_schema_sha256)))

    def semantic_view(self) -> dict[str, Any]:
        return {
            "story": self.story,
            "variables": self.variable_map.semantic_builder_view()["nodes"],
        }


def load_llm_graph_input(
    source_root: Path,
    scene_id: str,
    *,
    variant: str = "clean",
) -> PublicLLMGraphInput:
    """Load story and public schema only; no tasks, tables, or grading paths."""

    variable_map, schema_sha256 = load_causalds_variable_map(
        source_root, scene_id, variant=variant
    )
    story_path = resolve_public_story(source_root, scene_id)
    story = story_path.read_text(encoding="utf-8").strip()
    if not story:
        raise ValueError("Public story cannot be empty")
    missing = [
        variable.public_name
        for variable in variable_map.variables
        if variable.public_name not in story
    ]
    if missing:
        raise ValueError(f"Public story omits schema variables: {missing}")
    return PublicLLMGraphInput(
        scene_id=scene_id,
        story=story,
        variable_map=variable_map,
        story_sha256=sha256_file(story_path),
        public_schema_sha256=schema_sha256,
    )
