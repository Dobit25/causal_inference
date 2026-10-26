"""Freeze authorization and score the maximum registered P1V4 look 440."""
from __future__ import annotations
import hashlib
from pathlib import Path

SOURCE = Path(__file__).with_name("score_p1_v4_look320_cumulative_oracle.py")
EXPECTED_SOURCE_SHA256 = "530FD1BD769C9142046E48BA2CBAAC9A977169C7695FB375DF0EEF3093D83287"
if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper() != EXPECTED_SOURCE_SHA256:
    raise RuntimeError("look-320 parent scorer hash drift")
source = SOURCE.read_text(encoding="utf-8")
stages = """ 'look360':{'plan':'p1_v4_look360_incremental_statistical_plan.json','audit':'p1_v4_look360_incremental_statistical_execution_audit.json','groups':'p1_v4_look360_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look360_incremental_pair_records.jsonl','semantic':'p1_v4_look360_incremental_mini_semantic_plan.json','materialization':'p1_v4_look360_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look360_increment/statistical/normalized'},
 'look400':{'plan':'p1_v4_look400_incremental_statistical_plan.json','audit':'p1_v4_look400_incremental_statistical_execution_audit.json','groups':'p1_v4_look400_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look400_incremental_pair_records.jsonl','semantic':'p1_v4_look400_incremental_mini_semantic_plan.json','materialization':'p1_v4_look400_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look400_increment/statistical/normalized'},
 'look440':{'plan':'p1_v4_look440_incremental_statistical_plan.json','audit':'p1_v4_look440_incremental_statistical_execution_audit.json','groups':'p1_v4_look440_incremental_six_vote_groups.jsonl','pairs':'p1_v4_look440_incremental_pair_records.jsonl','semantic':'p1_v4_look440_incremental_mini_semantic_plan.json','materialization':'p1_v4_look440_incremental_materialization.json','root':'results/raw/p1_v4_independent_calibration/look440_increment/statistical/normalized'},
"""
needle = "}\ndef cb(x):"
if source.count(needle) != 1: raise RuntimeError("unable to append registered successor stages")
source = source.replace(needle, stages + "}\ndef cb(x):", 1)
replacements = {
    "PREFIX='p1_v4_look320_cumulative'": "PREFIX='p1_v4_look440_cumulative'",
    "if len(ids)!=320 or len(set(ids))!=320": "if len(ids)!=440 or len(set(ids))!=440",
    "if len(parents)!=640 or len({(x['scene_id'],x['condition']) for x in parents})!=640": "if len(parents)!=880 or len({(x['scene_id'],x['condition']) for x in parents})!=880",
    "'schema_version':'fourgraph.p1_v4_look320_oracle_checkpoint.v1'": "'schema_version':'fourgraph.p1_v4_look440_oracle_checkpoint.v1'",
    "'scope':{'scenes':320,'parents':640": "'scope':{'scenes':440,'parents':880",
    "'schema_version':'fourgraph.p1_v4_look320_oracle_execution.v1'": "'schema_version':'fourgraph.p1_v4_look440_oracle_execution.v1'",
    "'registered_look':320": "'registered_look':440",
    "'next_registered_look':360": "'next_registered_look':None",
    "'exact_oracle_scenes':320": "'exact_oracle_scenes':440",
    "cfg=ROOT/'configs/p1_v4_look320_cumulative_oracle_scoring.yaml'": "cfg=ROOT/'configs/p1_v4_look440_cumulative_oracle_scoring.yaml'",
    "AUTHORIZED_CALIBRATION_LOOK320_ORACLE_SCORING": "AUTHORIZED_CALIBRATION_LOOK440_ORACLE_SCORING",
    "'scenes':320,'parents':640": "'scenes':440,'parents':880",
    "cfgp=ROOT/'configs/p1_v4_look320_cumulative_oracle_scoring.yaml'": "cfgp=ROOT/'configs/p1_v4_look440_cumulative_oracle_scoring.yaml'",
    "valid=len(ovs)==320": "valid=len(ovs)==440",
    "'total':320": "'total':440",
    "remaining=440-320": "remaining=440-440",
    "CONTINUE_TO_LOOK_360": "STOP_FOR_FUTILITY",
    "'schema_version':'fourgraph.p1_v4_look320_cumulative_overlay_oracle_results.v1'": "'schema_version':'fourgraph.p1_v4_look440_cumulative_overlay_oracle_results.v1'",
    "'oracle_scope':'P1V4 calibration 320 only'": "'oracle_scope':'P1V4 calibration 440 only'",
    "'oracle_scenes_accessed':320": "'oracle_scenes_accessed':440",
    "# P1V4 cumulative calibration look 320": "# P1V4 cumulative calibration look 440",
    "Exactly 320 calibration Oracle commitments": "Exactly 440 calibration Oracle commitments",
}
for old,new in replacements.items():
    if old not in source: raise RuntimeError(f"registered successor replacement missing: {old}")
    source=source.replace(old,new)
namespace={"__name__":"p1_v4_look440_cumulative_runtime","__file__":str(Path(__file__).resolve())}
exec(compile(source,str(SOURCE),"exec"),namespace)
if __name__=="__main__": namespace["main"]()
