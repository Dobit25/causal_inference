"""Run one synthetic Mini-medium preflight in the canonical cau environment."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p1_v4_independent_calibration_look120_mini_provider_preflight as base

base.CONFIG = ROOT / "configs/p1_v4_partial_high_supplemental80_mini_provider_preflight.yaml"

if __name__ == "__main__":
    raise SystemExit(base.main())
