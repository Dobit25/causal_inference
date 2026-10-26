"""Freeze authorization and score registered cumulative P1V4 look 360.

This successor executes the already-audited look-320 scorer with only the
registered cumulative-look constants and one appended stage changed.  The
parent scorer is hash-pinned so any unregistered implementation drift fails
closed before Oracle access.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

SOURCE = Path(__file__).with_name("score_p1_v4_look320_cumulative_oracle.py")
EXPECTED_SOURCE_SHA256 = "530FD1BD769C9142046E48BA2CBAAC9A977169C7695FB375DF0EEF3093D83287"
if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper() != EXPECTED_SOURCE_SHA256:
    raise RuntimeError("look-320 parent scorer hash drift")

source = SOURCE.read_text(encoding="utf-8")
stage = """ 'look360':{'plan':'p1_v4_look360_incremental_statistical_plan.json','audit':'p1_v4_look360_incremental_statistical_execution_audit.json','groups':'p1_v4_look360_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look360_incremental_pair_records.jsonl','semantic':'p1_v4_look360_incremental_mini_semantic_plan.json','materialization':'p1_v4_look360_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look360_increment/statistical/normalized'},
"""
needle = "}\ndef cb(x):"
if source.count(needle) != 1:
    raise RuntimeError("unable to append registered look-360 stage")
source = source.replace(needle, stage + "}\ndef cb(x):", 1)

replacements = {
    "PREFIX='p1_v4_look320_cumulative'": "PREFIX='p1_v4_look360_cumulative'",
    "if len(ids)!=320 or len(set(ids))!=320": "if len(ids)!=360 or len(set(ids))!=360",
    "if len(parents)!=640 or len({(x['scene_id'],x['condition']) for x in parents})!=640": "if len(parents)!=720 or len({(x['scene_id'],x['condition']) for x in parents})!=720",
    "'schema_version':'fourgraph.p1_v4_look320_oracle_checkpoint.v1'": "'schema_version':'fourgraph.p1_v4_look360_oracle_checkpoint.v1'",
    "'scope':{'scenes':320,'parents':640": "'scope':{'scenes':360,'parents':720",
    "'schema_version':'fourgraph.p1_v4_look320_oracle_execution.v1'": "'schema_version':'fourgraph.p1_v4_look360_oracle_execution.v1'",
    "'registered_look':320": "'registered_look':360",
    "'next_registered_look':360": "'next_registered_look':400",
    "'exact_oracle_scenes':320": "'exact_oracle_scenes':360",
    "cfg=ROOT/'configs/p1_v4_look320_cumulative_oracle_scoring.yaml'": "cfg=ROOT/'configs/p1_v4_look360_cumulative_oracle_scoring.yaml'",
    "AUTHORIZED_CALIBRATION_LOOK320_ORACLE_SCORING": "AUTHORIZED_CALIBRATION_LOOK360_ORACLE_SCORING",
    "'scenes':320,'parents':640": "'scenes':360,'parents':720",
    "cfgp=ROOT/'configs/p1_v4_look320_cumulative_oracle_scoring.yaml'": "cfgp=ROOT/'configs/p1_v4_look360_cumulative_oracle_scoring.yaml'",
    "valid=len(ovs)==320": "valid=len(ovs)==360",
    "'total':320": "'total':360",
    "remaining=440-320": "remaining=440-360",
    "CONTINUE_TO_LOOK_360": "CONTINUE_TO_LOOK_400",
    "'schema_version':'fourgraph.p1_v4_look320_cumulative_overlay_oracle_results.v1'": "'schema_version':'fourgraph.p1_v4_look360_cumulative_overlay_oracle_results.v1'",
    "'oracle_scope':'P1V4 calibration 320 only'": "'oracle_scope':'P1V4 calibration 360 only'",
    "'oracle_scenes_accessed':320": "'oracle_scenes_accessed':360",
    "# P1V4 cumulative calibration look 320": "# P1V4 cumulative calibration look 360",
    "Exactly 320 calibration Oracle commitments": "Exactly 360 calibration Oracle commitments",
}
for old, new in replacements.items():
    if old not in source:
        raise RuntimeError(f"registered successor replacement missing: {old}")
    source = source.replace(old, new)

namespace = {"__name__": "p1_v4_look360_cumulative_runtime", "__file__": str(Path(__file__).resolve())}
exec(compile(source, str(SOURCE), "exec"), namespace)

if __name__ == "__main__":
    namespace["main"]()
