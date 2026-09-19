from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex
from fourgraph.p1_generation import scene_scm_record
from fourgraph.successor_generation import allocate_role, generate_blueprint


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_runtime_cost_pilot_preflight.yaml"
INVENTORY = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_inventory.jsonl"
MANIFEST = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_preflight.json"
AUDIT = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_preflight_audit.json"
REPORT = ROOT / "reports/p1_v3_runtime_cost_pilot_preflight.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def line(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def build() -> tuple[bytes, bytes, bytes, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    dependencies = [
        (ROOT / cfg["parent"]["audit"], cfg["parent"]["audit_sha256"]),
        (ROOT / cfg["parent"]["design"], cfg["parent"]["design_sha256"]),
        (ROOT / cfg["runner"]["entrypoint"], cfg["runner"]["entrypoint_sha256"]),
        (ROOT / cfg["runner"]["planning_library"], cfg["runner"]["planning_library_sha256"]),
        (ROOT / cfg["runner"]["bootstrap_contract"], cfg["runner"]["bootstrap_contract_sha256"]),
        (ROOT / cfg["runner"]["tetrad_backend"], cfg["runner"]["tetrad_backend_sha256"]),
        (ROOT / cfg["runner"]["openai_backend"], cfg["runner"]["openai_backend_sha256"]),
        (ROOT / cfg["runner"]["prompt"], cfg["runner"]["prompt_sha256"]),
        (ROOT / cfg["runner"]["response_schema"], cfg["runner"]["response_schema_sha256"]),
        (ROOT / cfg["environment"]["snapshot"], cfg["environment"]["snapshot_sha256"]),
        (ROOT / cfg["rate_budget"]["record"], cfg["rate_budget"]["record_sha256"]),
    ]
    for path, expected in dependencies:
        if sha256(path) != expected:
            raise RuntimeError(f"dependency hash mismatch: {path.relative_to(ROOT)}")
    parent = json.loads(dependencies[0][0].read_text(encoding="utf-8"))
    if parent["authorization"]["next_action"] != cfg["task"]:
        raise RuntimeError("parent did not authorize offline preflight freeze")
    env = json.loads((ROOT / cfg["environment"]["snapshot"]).read_text(encoding="utf-8"))
    if not env["credentials"]["openai_api_key_present"] or env["credentials"]["secret_values_captured"]:
        raise RuntimeError("credential-presence boundary failed")
    jar = ROOT / env["tetrad"]["jar"]
    if not jar.exists() or sha256(jar) != env["tetrad"]["sha256"]:
        raise RuntimeError("Tetrad jar missing or changed")
    jvm = Path(env["java"]["jvm_path"])
    if not jvm.exists():
        raise RuntimeError("pinned JVM does not exist")
    if int(env["machine"]["workspace_drive_free_bytes_at_capture"]) < int(cfg["environment"]["minimum_free_disk_bytes"]):
        raise RuntimeError("captured disk capacity gate failed")
    if int(env["machine"]["total_visible_memory_bytes"]) < int(cfg["environment"]["memory_gate_bytes"]):
        raise RuntimeError("captured memory gate failed")

    identity = cfg["pilot_identity"]
    marginals = {
        "node_count": {int(k): int(v) for k, v in identity["node_count"].items()},
        "primary_motif": identity["primary_motif"],
        "noise_family": identity["noise_family"],
        "query_stratum": identity["query_stratum"],
    }
    plans = allocate_role(
        role=identity["role"], namespace=identity["namespace"],
        scene_count=int(identity["scene_count"]), scene_number_start=int(identity["scene_number_start"]),
        master_seed=int(identity["master_seed"]), marginals=marginals,
    )
    edge_ranges = {int(k): tuple(v) for k, v in identity["edge_count_range"].items()}
    built = []
    for plan in plans:
        blueprint, agreements = generate_blueprint(
            plan, master_seed=int(identity["master_seed"]), edge_count_ranges=edge_ranges,
            minimum_unresolved_edges=int(identity["minimum_oracle_cpdag_unresolved_edges"]),
            maximum_attempts=int(identity["maximum_attempts_per_scene"]),
        )
        replay, replay_agreements = generate_blueprint(
            plan, master_seed=int(identity["master_seed"]), edge_count_ranges=edge_ranges,
            minimum_unresolved_edges=int(identity["minimum_oracle_cpdag_unresolved_edges"]),
            maximum_attempts=int(identity["maximum_attempts_per_scene"]),
        )
        blueprint_bytes = canonical_json_bytes(scene_scm_record(blueprint))
        if blueprint_bytes != canonical_json_bytes(scene_scm_record(replay)) or agreements != replay_agreements:
            raise RuntimeError("pilot blueprint replay mismatch")
        built.append((plan, blueprint, sha256_hex(blueprint_bytes), agreements))
    selected: set[str] = set()
    for node_count in (5, 6, 7):
        candidates = [row for row in built if row[0].node_count == node_count]
        candidates.sort(key=lambda row: hashlib.sha256(f"{identity['master_seed']}:{row[0].synthetic_id}:semantic".encode()).hexdigest())
        selected.update(row[0].synthetic_id for row in candidates[:2])
    rows = [
        {
            "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_identity.v1",
            "pilot_id": plan.synthetic_id,
            "scene_id": plan.contract_scene_id,
            "allocation": plan.to_dict(),
            "generation_attempt": blueprint.generation_attempt,
            "node_count": blueprint.node_count,
            "edge_count": len(blueprint.dag.directed),
            "oracle_cpdag_unresolved_edges": len(blueprint.oracle_cpdag.undirected),
            "task_solver_agreements": agreements,
            "blueprint_sha256": digest,
            "selected_for_semantic_runtime_sample": plan.synthetic_id in selected,
            "observation_rows_generated": 0,
            "story_variants_generated": 0,
        }
        for plan, blueprint, digest, agreements in built
    ]
    inventory_bytes = b"".join(line(row) for row in rows)
    if Counter(row["node_count"] for row in rows) != {5: 3, 6: 3, 7: 3} or len(selected) != 6:
        raise RuntimeError("pilot panel/sample balance failed")
    rate_budget = yaml.safe_load((ROOT / cfg["rate_budget"]["record"]).read_text(encoding="utf-8"))
    manifest = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_preflight_manifest.v1",
        "task": cfg["task"], "status": cfg["status"],
        "pilot_ids": [row["pilot_id"] for row in rows],
        "semantic_sample_ids": sorted(selected),
        "inventory_sha256": sha256_hex(inventory_bytes),
        "runner": cfg["runner"], "environment": cfg["environment"],
        "rate_budget": rate_budget, "schedule": cfg["schedule"],
        "preflight_gates": cfg["preflight_gates"],
        "evidence_boundary": cfg["evidence_boundary"],
        "authorization_after_freeze": cfg["authorization_after_freeze"],
    }
    manifest_bytes = line(manifest)
    report = f"""# P1-v3 runtime/cost pilot preflight freeze

The preflight pins nine exact synthetic-only identities (`SYNPILOT000`–`SYNPILOT008`) and deterministic blueprint hashes; six IDs are frozen for the 108-call semantic timing sample. No observation or story text was generated. The execution schedule remains 3 excluded BOSS warm-ups, 270 measured fits and 108 semantic calls.

The machine snapshot pins Windows 11, CPython 3.10.21 in `cau`, 10 physical/16 logical CPU cores, {env['machine']['total_visible_memory_bytes']} bytes visible memory and {env['machine']['workspace_drive_free_bytes_at_capture']} bytes free on drive D at capture. Java is not on PATH and JAVA_HOME is absent, so the runner must use the pinned Azul JVM 21.0.10 DLL. The Tetrad 7.6.11-SNAPSHOT jar hash is unchanged. Only API-key presence was recorded; no secret value was captured.

An offline conservative accounting ceiling of USD 0.75/M uncached input, 0.075/M cached input and 4.50/M output is pinned from an existing project record, with a dedicated USD 1.50 pilot cap. These values are not claimed to be current official GPT-5.4 Nano pricing. Official current pricing and remaining platform balance could not be verified offline and remain explicit live-execution blockers.

Therefore this preflight is frozen but not execution-ready. It authorizes only a separate execution-authorization checkpoint; pilot execution, observations, Bootstrap/BOSS, semantic API calls, successor generation and final-holdout access remain forbidden.
""".encode("utf-8")
    outputs = ((INVENTORY, inventory_bytes), (MANIFEST, manifest_bytes), (REPORT, report))
    audit = {
        "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_preflight_audit.v1",
        "task": cfg["task"],
        "dependencies": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p)} for p, _ in dependencies] + [{"path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha256(CONFIG)}],
        "implementation": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha256(Path(__file__))},
        "outputs": [{"path": p.relative_to(ROOT).as_posix(), "bytes": len(content), "sha256": sha256_hex(content)} for p, content in outputs],
        "counts": {"pilot_identities": 9, "blueprints_replayed": 9, "semantic_sample_ids": 6, "task_solver_agreements": sum(row[3] for row in built), "observation_rows": 0, "stories": 0, "boss_runs": 0, "api_calls": 0},
        "evidence_boundary": cfg["evidence_boundary"],
        "authorization": cfg["authorization_after_freeze"],
        "verdict": {"preflight_frozen": True, "identity_and_environment_pinned": True, "conservative_accounting_ceiling_pinned": True, "official_current_rate_verified": False, "remaining_platform_balance_verified": False, "execution_ready": False, "pilot_execution_authorized": False},
    }
    return inventory_bytes, manifest_bytes, line(audit), report


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    built = build(); paths = (INVENTORY, MANIFEST, AUDIT, REPORT)
    if args.check:
        for path, expected in zip(paths, built):
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"Mismatch: {path.relative_to(ROOT)}")
        print("P1-v3 runtime/cost pilot preflight reproduces byte-for-byte")
        return 0
    for path, content in zip(paths, built):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print("P1-v3 runtime/cost pilot preflight frozen; live execution remains forbidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
