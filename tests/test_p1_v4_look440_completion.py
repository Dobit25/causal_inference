import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))

def test_look440_execution_and_rescore_complete():
    stat=load(Path('data/manifests/p1_v4_look440_incremental_statistical_execution_audit.json'))
    sem=load(Path('data/manifests/p1_v4_look440_incremental_mini_semantic_execution_audit.json'))
    res=load(Path('data/manifests/p1_v4_look440_incremental_response_freeze_rescore_audit.json'))
    assert stat['status']=='PASS_STATISTICAL_EXECUTION'
    assert stat['planned_fits']==stat['complete_terminal_records']==8240
    assert sem['status']=='PASS' and sem['recorded_logical_calls']==sem['planned_logical_calls']==480
    assert res['status']=='PASS' and res['pair_records']==3144 and res['six_vote_groups']==524
    assert res['production_reference_disagreements']==0

def test_look440_terminal_oracle_decision():
    audit=load(Path('data/manifests/p1_v4_look440_cumulative_overlay_oracle_metric_audit.json'))
    result=load(Path('data/manifests/p1_v4_look440_cumulative_overlay_oracle_metric_results.json'))
    review=load(Path('data/manifests/p1_v4_look440_final_calibration_review.json'))
    assert audit['status']=='PASS_ORACLE_SCORING' and audit['oracle_scenes_accessed']==440
    assert audit['validation_access']==audit['holdout_access']==0
    assert result['status']=='STOP_FOR_FUTILITY'
    assert review['status']=='PASS_REVIEWED'
    assert review['calibration_outcome']=='NEGATIVE_OR_INCONCLUSIVE_CALIBRATION_STOP'
    assert review['gates']['full']['registered_gate_pass'] is True
    assert review['gates']['partial']['registered_gate_pass'] is False
    assert review['validation_authorized'] is False
