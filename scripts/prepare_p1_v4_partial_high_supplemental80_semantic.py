"""Freeze a shared Mini-medium semantic pool for the supplemental 80 scenes.

No provider call or Oracle access occurs in this planner.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "p1_v4_partial_high_supplemental80"
MANIFESTS = ROOT / "data/manifests"
GENERATED = ROOT / "data/generated" / PREFIX
NORMALIZED = ROOT / "results/raw" / PREFIX / "statistical/normalized"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_immutable(path: Path, value: object) -> None:
    body = canonical(value)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)


def main() -> None:
    stat_audit_path = MANIFESTS / f"{PREFIX}_statistical_execution_audit.json"
    stat = load(stat_audit_path)
    if stat.get("status") != "PASS_STATISTICAL_EXECUTION" or stat.get("complete_terminal_records") != 16480:
        raise RuntimeError("statistical execution has not passed")
    boundary = stat.get("execution_boundary", {})
    if any(boundary.get(key) for key in ("semantic_api_calls", "oracle_access", "holdout_access")):
        raise RuntimeError("statistical boundary violation")

    materialization = load(MANIFESTS / f"{PREFIX}_materialization.json")
    ids = [row["study_id"] for row in materialization["records"]]
    if len(ids) != 80 or len(set(ids)) != 80:
        raise RuntimeError("scene identity drift")
    public_path = MANIFESTS / f"{PREFIX}_public_inputs.json"
    public = load(public_path)
    stories = {(row["study_id"], row["variant"]): row for row in public["records"]}
    if len(public["records"]) != 240 or len(stories) != 240:
        raise RuntimeError("public story inventory drift")

    graphs: dict[tuple[str, str], dict] = {}
    for path in NORMALIZED.glob("*.json"):
        record = load(path)
        job = record["job"]
        algorithm = job["algorithm"]
        if algorithm in ("Constrained-BOSS", "Constrained-FGES"):
            if record.get("status") != "VALID":
                raise RuntimeError(f"invalid constrained parent: {job}")
            identity = (job["scene_id"], algorithm)
            if identity in graphs:
                raise RuntimeError(f"duplicate constrained parent: {identity}")
            graphs[identity] = record["graph"]
    if len(graphs) != 160:
        raise RuntimeError(f"expected 160 constrained parent graphs, got {len(graphs)}")

    pools: dict[str, dict] = {}
    calls: list[dict] = []
    for sid in ids:
        pair_set: set[tuple[str, str]] = set()
        for algorithm in ("Constrained-BOSS", "Constrained-FGES"):
            graph = graphs[(sid, algorithm)]
            pair_set.update(tuple(sorted(edge)) for edge in graph["directed"] + graph["undirected"])
        aliases = load(GENERATED / sid / "alias_map.json")["alias_map"]
        pairs = [
            {"pair_id": f"pair_{index:03d}", "node_a_canonical": a,
             "node_b_canonical": b, "node_a_alias": aliases[a], "node_b_alias": aliases[b]}
            for index, (a, b) in enumerate(sorted(pair_set), 1)
        ]
        if not 1 <= len(pairs) <= 21:
            raise RuntimeError(f"out-of-range pair count: {sid} {len(pairs)}")
        pool_sha = hashlib.sha256(canonical(pairs)).hexdigest().upper()
        pools[sid] = {"pairs": pairs, "pair_pool_sha256": pool_sha,
                      "source": "union_all_constrained_parent_adjacencies"}
        for variant in ("full", "partial"):
            story = stories[(sid, variant)]
            if sha(ROOT / story["artifact_path"]) != story["artifact_sha256"]:
                raise RuntimeError(f"public story artifact hash drift: {sid}/{variant}")
            for prompt in ("P1", "P2", "P3", "P4", "P5", "P6"):
                calls.append({
                    "logical_id": f"{sid}/{variant}/{prompt}", "study_id": sid,
                    "variant": variant, "prompt_id": prompt,
                    "model": "gpt-5.4-mini-2026-03-17", "reasoning_effort": "medium",
                    "story_artifact_path": story["artifact_path"],
                    "story_content_sha256": story["content_sha256"],
                    "pair_count": len(pairs), "pair_ids": [pair["pair_id"] for pair in pairs],
                    "pair_pool_sha256": pool_sha,
                    "conditions": ["constrained_boss", "constrained_fges"],
                })
    if len(calls) != 960 or len({item["logical_id"] for item in calls}) != 960:
        raise RuntimeError("semantic call identity drift")
    counts = [len(pool["pairs"]) for pool in pools.values()]
    plan = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_mini_semantic_plan.v1",
        "status": "FROZEN", "model": "gpt-5.4-mini-2026-03-17",
        "reasoning_effort": "medium", "logical_calls": calls, "pair_pools": pools,
        "story_variants": ["full", "partial"],
        "ambiguous_increment": "excluded_by_fixed_diagnostic_subset",
        "nonedge": "excluded", "primary_meek_closure": "forbidden",
    }
    plan_path = MANIFESTS / f"{PREFIX}_mini_semantic_plan.json"
    write_immutable(plan_path, plan)
    audit = {
        "status": "PASS", "scenes": 80, "logical_calls": 960,
        "scene_pair_records": sum(counts), "expected_pair_records": sum(counts) * 12,
        "expected_six_vote_groups": sum(counts) * 2,
        "min_pairs": min(counts), "max_pairs": max(counts),
        "plan_sha256": sha(plan_path), "statistical_audit_sha256": sha(stat_audit_path),
        "public_input_manifest_sha256": sha(public_path),
        "api_calls": 0, "oracle_access": 0, "holdout_access": 0,
    }
    write_immutable(MANIFESTS / f"{PREFIX}_mini_semantic_plan_audit.json", audit)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
