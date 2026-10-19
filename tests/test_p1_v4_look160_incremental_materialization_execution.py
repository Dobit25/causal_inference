import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/manifests/p1_v4_look160_incremental_materialization_execution_audit.json"
INVENTORY = ROOT / "data/manifests/p1_v4_look160_incremental_materialization_artifact_inventory.jsonl"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_materialization_counts_and_variants_are_exact():
    audit = load(AUDIT)
    assert audit["status"] == "PASS_MATERIALIZATION_EXECUTION"
    assert audit["counts"] == {"scenes": 40, "observations": 40, "metadata": 40, "alias_maps": 40, "public_stories": 120, "files": 240, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_scoring_reads": 0}
    assert audit["variant_counts"] == {"full": 40, "partial": 40, "ambiguous": 40}


def test_all_execution_audit_checks_pass():
    assert all(load(AUDIT)["checks"].values())


def test_inventory_has_exact_byte_replay_and_public_leakage_pass():
    rows = [json.loads(line) for line in INVENTORY.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 240
    assert all(row["replay_match"] is True for row in rows)
    public = [row for row in rows if row["kind"] == "public_story"]
    assert len(public) == 120
    assert all(row["leakage_pass"] is True for row in public)


def test_execution_replay_is_idempotent_with_zero_new_writes():
    completed = subprocess.run(
        [sys.executable, "scripts/materialize_p1_v4_look160_increment.py", "--execute", "--authorization", "data/manifests/p1_v4_look160_incremental_live_materialization_authorization.json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["status"] == "PASS"
    assert result["writes"] == 0


def test_audit_replays_byte_exact():
    completed = subprocess.run(
        [sys.executable, "scripts/audit_p1_v4_look160_incremental_materialization.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"check": true' in completed.stdout.lower()
