import hashlib
import json
from collections import Counter
from pathlib import Path

from fourgraph.causalds_inventory import (
    PRIMARY_TASK_IDS,
    build_provisional_split,
    load_inventory,
)
from fourgraph.config import load_config


INVENTORY_PATH = Path("data/manifests/causalds_scene_inventory.jsonl")
SPLIT_PATH = Path("data/manifests/p0_provisional_split.json")
SOURCE_MANIFEST_PATH = Path("data/manifests/causalds.json")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_complete_scene_inventory() -> None:
    inventory = load_inventory(INVENTORY_PATH)

    assert len(inventory) == 100
    assert len({row["scene_id"] for row in inventory}) == 100
    assert Counter(row["observation_variant"] for row in inventory) == {
        "clean": 48,
        "proxy": 32,
        "proxy_hard": 20,
    }
    assert {row["n_rows"] for row in inventory} == {16000}
    assert all(row["dag_valid"] for row in inventory)
    assert all(row["mapping_complete"] for row in inventory)
    assert all(row["mechanisms"]["metadata_available"] for row in inventory)
    assert all(
        row["mechanisms"]["complete_for_all_graph_nodes"] for row in inventory
    )
    assert all(row["task_ids"] for row in inventory)


def test_inventory_reproduces_nested_eligibility() -> None:
    inventory = load_inventory(INVENTORY_PATH)
    graph = {
        row["scene_id"]
        for row in inventory
        if row["cohort_membership"]["graph"]
    }
    primary = {
        row["scene_id"]
        for row in inventory
        if row["cohort_membership"]["primary_downstream"]
    }
    supplementary = {
        row["scene_id"]
        for row in inventory
        if row["cohort_membership"]["supplementary"]
    }

    assert (len(graph), len(primary), len(supplementary)) == (33, 27, 6)
    assert primary.isdisjoint(supplementary)
    assert primary | supplementary == graph
    assert all(
        set(PRIMARY_TASK_IDS) <= set(row["task_ids"])
        for row in inventory
        if row["scene_id"] in primary
    )


def test_provisional_split_contract_and_nesting() -> None:
    split = _load_json(SPLIT_PATH)
    graph = split["cohorts"]["graph"]
    primary = split["cohorts"]["primary_downstream"]
    supplementary = split["cohorts"]["supplementary"]

    assert split["status"] == "provisional_until_t04_integrity"
    assert split["not_frozen"] is True
    assert (len(graph["dev_ids"]), len(graph["holdout_ids"])) == (8, 25)
    assert (len(primary["dev_ids"]), len(primary["holdout_ids"])) == (7, 20)
    assert (
        len(supplementary["dev_ids"]),
        len(supplementary["holdout_ids"]),
    ) == (1, 5)
    assert set(primary["dev_ids"]) | set(supplementary["dev_ids"]) == set(
        graph["dev_ids"]
    )
    assert set(primary["holdout_ids"]) | set(
        supplementary["holdout_ids"]
    ) == set(graph["holdout_ids"])
    assert set(graph["dev_ids"]).isdisjoint(graph["holdout_ids"])
    assert all(split["nesting_checks"].values())
    assert split["balance_checks"]["common_graph_strata_covered"] is True
    assert split["balance_checks"]["common_primary_strata_covered"] is True
    assert (
        split["balance_checks"]["selected_loss_below_baseline_median"] is True
    )


def test_split_reproduces_deterministically() -> None:
    inventory = load_inventory(INVENTORY_PATH)
    committed = _load_json(SPLIT_PATH)
    reproduced = build_provisional_split(
        inventory,
        seed=committed["algorithm"]["seed"],
        restarts=committed["algorithm"]["restarts"],
    )

    assert reproduced["cohorts"] == committed["cohorts"]
    assert reproduced["algorithm"]["selected_objective_loss"] == committed[
        "algorithm"
    ]["selected_objective_loss"]
    assert reproduced["balance"] == committed["balance"]


def test_t03_artifact_hashes_and_config_pointers() -> None:
    source_manifest = _load_json(SOURCE_MANIFEST_PATH)
    config = load_config("configs/p0_released.yaml")
    derived = source_manifest["derived_artifacts"]

    for key, path in (
        ("t03_scene_inventory", INVENTORY_PATH),
        ("t03_provisional_split", SPLIT_PATH),
    ):
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert digest == derived[key]["sha256"]
        assert path.stat().st_size == derived[key]["size_bytes"]

    assert config["t03"]["status"] == "complete_superseded_by_t04_freeze"
    assert _load_json(SPLIT_PATH)["status"] == "provisional_until_t04_integrity"
    assert config["t03"]["inventory"] == INVENTORY_PATH.as_posix()
    assert config["t03"]["split_manifest"] == SPLIT_PATH.as_posix()
    assert config["t03"]["parquet_content_audit"] == "deferred_to_t04"
