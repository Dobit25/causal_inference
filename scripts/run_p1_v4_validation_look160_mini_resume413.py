"""Run exactly the explicitly authorized 413-call resume slice."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_p1_v4_independent_calibration_look120_mini_semantic as base
CONFIG=ROOT/'configs/p1_v4_validation_look160_mini_resume413.yaml'
if __name__=='__main__':
    result=base.run(True,CONFIG,413)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['status'] in {'PASS','AUTHORIZED_SLICE_COMPLETE'} else 1)
