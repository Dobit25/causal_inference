"""Production wrapper for the explicitly authorized remaining 720 calls.

Kept as a file (rather than stdin) because the frozen watchdog uses Python's
spawn multiprocessing start method on Windows.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p1_v4_independent_calibration_look120_mini_semantic as base  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_remaining720.yaml"

if __name__ == "__main__":
    result = base.run(True, CONFIG, 720)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] in {"PASS", "AUTHORIZED_SLICE_COMPLETE"} else 1)
