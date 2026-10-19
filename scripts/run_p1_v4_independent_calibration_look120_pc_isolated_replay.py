"""One authorized PC forensic replay with raw graph capture before validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from adapters.tetrad_adapter import TetradAdapter  # noqa: E402
from fourgraph.causalds_scd import SceneData  # noqa: E402
from fourgraph.p1_generation import standardize  # noqa: E402
from fourgraph.partial_graph import PartialGraph, validate_cpdag  # noqa: E402

AUTH = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_isolated_replay_live_authorization.json"
MATERIALIZATION = ROOT / "data/manifests/p1_v4_independent_calibration_look120_materialization.json"
OUT = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/pc_incident_replay"
JAR = ROOT / "data/raw/t05/py-tetrad/pytetrad/resources/tetrad-current.jar"
JAR_HASH = "5A3BA56ADECE35DA8A209B39DB8B8BF29D4037FB79ED56C4B63F8D3B4C1A7051"
REPLAY_ID = "PC_INCIDENT_REPLAY_D823FF5FBE1D32979100E7E9185DEF94468A04F7569B8966F6A911FFB51B7DAC"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"artifact drift: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.dry_run == args.execute:
        raise SystemExit("choose exactly one mode")
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    if args.dry_run:
        print(json.dumps({"status": "PASS_DRY_RUN", "planned_fits": 1, "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0}))
        return
    if auth.get("status") != "PASS_ISOLATED_PC_REPLAY_LIVE_AUTHORIZATION":
        raise SystemExit("live replay is not authorized")
    os.environ["JAVA_HOME"] = str(Path(sys.prefix) / "Library/lib/jvm")
    os.environ["PATH"] = str(Path(sys.prefix) / "Library/bin") + os.pathsep + os.environ["PATH"]
    materialized = json.loads(MATERIALIZATION.read_text(encoding="utf-8"))["records"]
    record = next(row for row in materialized if row["study_id"] == "P1V4SC307")
    metadata = json.loads((ROOT / record["metadata_path"]).read_text(encoding="utf-8"))
    values = np.load(ROOT / record["observation_path"], allow_pickle=False)
    scene = SceneData("P1V4SC307", tuple(metadata["nodes"]), (False,) * len(metadata["nodes"]), standardize(values))
    adapter = TetradAdapter(JAR, JAR_HASH)
    started = time.perf_counter()
    graph, seconds = adapter.run(scene, "PC", {"alpha": 0.01, "depth": -1, "stable_fas": True})
    raw = {"replay_execution_id": REPLAY_ID, "scene_id": scene.scene_id, "algorithm": "PC", "graph": graph, "adapter_seconds": seconds, "input_sha256": metadata["observation_sha256"]}
    raw_bytes = canonical(raw)
    write_once(OUT / "prevalidation_raw.json", raw_bytes)
    try:
        validate_cpdag(PartialGraph.build(graph["nodes"], graph["directed"], graph["undirected"]))
        validation = {"status": "VALID_CPDAG", "error": None}
    except Exception as exc:  # preserve the graph before reporting the failure.
        validation = {"status": "INVALID_OR_ADAPTER_VALIDATOR_DISAGREEMENT", "error_type": type(exc).__name__, "error": str(exc)}
    result = {"replay_execution_id": REPLAY_ID, "raw_sha256": sha(raw_bytes), "validator": validation, "elapsed_seconds": time.perf_counter() - started, "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0}
    write_once(OUT / "validation_result.json", canonical(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
