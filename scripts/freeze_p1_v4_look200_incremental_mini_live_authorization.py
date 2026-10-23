"""Freeze look-200 Mini authorization through the frozen look-160 implementation."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import freeze_p1_v4_look160_incremental_mini_live_authorization as base

base.CFG=ROOT/'configs/p1_v4_look200_incremental_mini_semantic_live.yaml'

if __name__=='__main__': base.main()
