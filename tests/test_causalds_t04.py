import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from fourgraph.causalds_access import (
    GradingPurpose,
    resolve_grading_artifact,
    resolve_public_artifact,
)
from fourgraph.causalds_inventory import PRIMARY_TASK_IDS
from fourgraph.config import load_config


INTEGRITY_PATH = Path("data/manifests/p0_data_integrity.json")
PRIMARY_TASK_PATH = Path("data/manifests/p0_primary_task_manifest.jsonl")
SUPPLEMENTARY_TASK_PATH = Path(
    "data/manifests/p0_supplementary_task_manifest.jsonl"
)
FROZEN_SPLIT_PATH = Path("data/manifests/p0_frozen_split.json")
PROVISIONAL_SPLIT_PATH = Path("data/manifests/p0_provisional_split.json")
SOURCE_MANIFEST_PATH = Path("data/manifests/causalds.json")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_t04_integrity_gate_passed_all_scenes() -> None:
    integrity = _json(INTEGRITY_PATH)
    aggregate = integrity["aggregate"]

    assert integrity["integrity_ready"] is True
    assert integrity["status"] == "complete"
    assert aggregate["scene_count"] == 33
    assert aggregate["passed_scenes"] == 33
    assert aggregate["failed_scene_ids"] == []
    assert aggregate["data_rows_total"] == 528_000
    assert aggregate["actual_dtype_counts"] == {"float64": 120}
    assert aggregate["null_values_total"] == 0
    assert aggregate["nan_values_total"] == 0
    assert aggregate["infinite_values_total"] == 0
    assert aggregate["constant_columns_total"] == 0
    assert aggregate["binary_support_mismatches"] == 0
    assert all(scene["passed"] for scene in integrity["scene_results"])
    assert integrity["scope"]["grading_parquets_read"] == []


def test_frozen_primary_and_supplementary_task_manifests() -> None:
    primary = _jsonl(PRIMARY_TASK_PATH)
    supplementary = _jsonl(SUPPLEMENTARY_TASK_PATH)

    assert len(primary) == 135
    assert len({record["scene_id"] for record in primary}) == 27
    primary_counts = Counter(record["scene_id"] for record in primary)
    assert set(primary_counts.values()) == {5}
    for scene_id in primary_counts:
        assert {
            record["task_id"]
            for record in primary
            if record["scene_id"] == scene_id
        } == set(PRIMARY_TASK_IDS)
    assert all(record["downstream_role"] == "primary" for record in primary)

    assert len(supplementary) == 89
    assert len({record["scene_id"] for record in supplementary}) == 6
    assert all(
        record["downstream_role"] == "exploratory_only"
        for record in supplementary
    )
    forbidden = {"gold", "gold_answer", "ground_truth", "graph_edges"}
    assert all(not (forbidden & set(record)) for record in primary + supplementary)


def test_frozen_split_preserves_t03_ids_and_nesting() -> None:
    frozen = _json(FROZEN_SPLIT_PATH)
    provisional = _json(PROVISIONAL_SPLIT_PATH)

    assert frozen["status"] == "frozen_after_t04_integrity"
    assert frozen["not_frozen"] is False
    assert frozen["cohorts"] == provisional["cohorts"]
    assert frozen["algorithm"] == provisional["algorithm"]
    assert all(frozen["nesting_checks"].values())
    assert frozen["freeze_gate"]["all_33_scenes_passed"] is True


def test_public_and_grading_access_are_separate() -> None:
    root = Path("C:/fake/causalds")
    public_path = resolve_public_artifact(
        root, "scene_000098", "clean", "data"
    )
    assert "scenes_private" not in public_path.parts
    assert public_path.name == "data.parquet"

    with pytest.raises(PermissionError, match="not available in public view"):
        resolve_public_artifact(root, "scene_000098", "clean", "ground_truth")
    with pytest.raises(PermissionError, match="Purpose cannot access grading"):
        resolve_grading_artifact(
            root,
            "scene_000098",
            "ground_truth",
            purpose="reasoner",  # type: ignore[arg-type]
        )

    grading_path = resolve_grading_artifact(
        root,
        "scene_000098",
        "ground_truth",
        purpose=GradingPurpose.INTEGRITY_AUDIT,
    )
    assert "scenes_private" in grading_path.parts


def test_t04_hashes_and_frozen_config() -> None:
    source_manifest = _json(SOURCE_MANIFEST_PATH)
    config = load_config("configs/p0_released.yaml")
    derived = source_manifest["derived_artifacts"]
    artifacts = (
        ("t04_data_integrity", INTEGRITY_PATH),
        ("t04_primary_task_manifest", PRIMARY_TASK_PATH),
        ("t04_supplementary_task_manifest", SUPPLEMENTARY_TASK_PATH),
        ("t04_frozen_split", FROZEN_SPLIT_PATH),
    )
    for key, path in artifacts:
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert digest == derived[key]["sha256"]
        assert path.stat().st_size == derived[key]["size_bytes"]

    assert config["t04"]["integrity_ready"] is True
    assert config["t04"]["all_33_scenes_passed"] is True
    assert config["t04"]["grading_parquet_values_read"] is False
    assert all(
        cohort["split"]["status"] == "frozen_after_t04_integrity"
        for cohort in config["cohorts"].values()
    )
    assert all(
        cohort["split"]["ids_manifest"] == FROZEN_SPLIT_PATH.as_posix()
        for cohort in config["cohorts"].values()
    )
