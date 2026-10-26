"""Look-440 wrapper around the frozen incremental statistical runner."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_p1_v4_look160_incremental_statistical as base
base.PLAN=ROOT/'data/manifests/p1_v4_look440_incremental_statistical_plan.json'
base.AUTH=ROOT/'data/manifests/p1_v4_look440_incremental_statistical_live_authorization.json'
base.MAT=ROOT/'data/manifests/p1_v4_look440_incremental_materialization.json'
base.OUT=ROOT/'results/raw/p1_v4_independent_calibration/look440_increment/statistical'
base.AUD=ROOT/'data/manifests/p1_v4_look440_incremental_statistical_execution_audit.json'
if __name__=='__main__': base.main()
