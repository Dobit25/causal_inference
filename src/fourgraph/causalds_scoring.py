"""Narrow grading-only answer loader for T12 scorers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from fourgraph.causalds_access import GradingPurpose, resolve_grading_artifact
from fourgraph.causalds_public import read_json_object, sha256_file
from fourgraph.graph_contract import VariableMap
from fourgraph.reasoner import OfficialTarget, ReasonerQuery, TASKS


def load_official_target(
    source_root: Path, query: ReasonerQuery, variable_map: VariableMap
) -> OfficialTarget:
    """Return a narrow scoring DTO; never expose the raw grading document."""

    path = resolve_grading_artifact(
        source_root, query.scene_id, "ground_truth", purpose=GradingPurpose.SCORING
    )
    gt = read_json_object(path, label="Scoring ground truth")
    causal = gt.get("causal") or {}
    internal_to_public = gt.get("mapping") or {}
    public_to_canonical = variable_map.scd_rename_map()

    def rename_set(values: Iterable[str]) -> tuple[str, ...]:
        return tuple(
            sorted(public_to_canonical[internal_to_public.get(item, item)] for item in values)
        )

    raw_valid = causal.get("valid_backdoor_sets") or []
    valid = tuple(
        sorted((rename_set(item) for item in raw_valid), key=lambda item: (len(item), item))
    )
    if query.task_id == TASKS[0]:
        accepted: tuple[Any, ...] = valid if valid else ("no_backdoor",)
    elif query.task_id == TASKS[1]:
        if valid:
            size = min(map(len, valid))
            accepted = (tuple(sorted(item for item in valid if len(item) == size)),)
        else:
            accepted = ("no_backdoor",)
    elif query.task_id == TASKS[2]:
        accepted = (min(map(len, valid)),) if valid else ("no_backdoor",)
    elif query.task_id == TASKS[3]:
        accepted = (len(valid),) if valid else ("no_backdoor",)
    else:
        forbidden = causal.get("forbidden_conditioning") or {}
        union = (forbidden.get("colliders") or []) + (forbidden.get("descendants") or [])
        accepted = (rename_set(union),) if valid else ("no_backdoor",)
    return OfficialTarget(query.task_id, accepted, sha256_file(path))
