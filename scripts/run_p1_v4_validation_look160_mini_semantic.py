"""Validation look-160 Mini runner; requires the scoped live artifact."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_p1_v4_independent_calibration_look120_mini_semantic as base
CONFIG=ROOT/'configs/p1_v4_validation_look160_mini_semantic_live.yaml'
if __name__=='__main__':
 import argparse,json
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--max-new-calls',type=int);a=p.parse_args()
 result=base.run(a.execute,CONFIG,a.max_new_calls);print(json.dumps(result,indent=2));raise SystemExit(0 if result['status'] in {'PASS','PASS_DRY_RUN','AUTHORIZED_SLICE_COMPLETE'} else 1)
